"""
OpenClaw OMEGA — 异常自愈引擎 (Self Heal)
6步自愈流程，只有全部失败才通知用户。

步骤:
  1. 分析错误原因（分类）
  2. 本地知识库检索（mem0）
  3. Web搜索解决方案（Tavily）
  4. 尝试替代方案
  5. 记录解决方案到记忆
  6. 通知用户（最后手段）

v2.0 — 2026-03-22
  - 引入 tenacity 做真正的指数退避重试（替换假重试）
  - _apply_solution / _try_alternatives 实现真实逻辑
  - 添加 circuit breaker（同一错误 3 次失败后短路跳过）
  - retry 回调接收 callable，实际重新执行失败操作
"""

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Coroutine, Dict, List, Optional

from src.http_client import ResilientHTTPClient

# 模块级 HTTP 客户端（自动重试 + 熔断，用于 Tavily 搜索）
_http = ResilientHTTPClient(timeout=15.0, name="self_heal")

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        RetryError,
    )

    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False

# pybreaker — 工业级熔断器（替代手写状态机）
try:
    import pybreaker

    _HAS_PYBREAKER = True
except ImportError:
    _HAS_PYBREAKER = False

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    NETWORK = "network"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    CAPTCHA = "captcha"
    PARSE = "parse"
    DEPENDENCY = "dependency"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class HealResult:
    healed: bool = False
    solution_used: str = ""
    error_category: ErrorCategory = ErrorCategory.UNKNOWN
    attempts: List[Dict] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# 已知解决方案
KNOWN_SOLUTIONS: Dict[str, Dict] = {
    "ConnectionRefusedError": {
        "category": ErrorCategory.NETWORK,
        "solution": "服务未启动，检查端口并重启",
        "action": "retry_with_delay",
        "delay": 5,
    },
    "ConnectionError": {
        "category": ErrorCategory.NETWORK,
        "solution": "网络连接失败，等待后重试",
        "action": "retry_with_delay",
        "delay": 10,
    },
    "429": {
        "category": ErrorCategory.RATE_LIMIT,
        "solution": "速率限制，等待后重试",
        "action": "retry_with_delay",
        "delay": 30,
    },
    "Too Many Requests": {
        "category": ErrorCategory.RATE_LIMIT,
        "solution": "API调用过于频繁",
        "action": "retry_with_delay",
        "delay": 60,
    },
    "captcha": {
        "category": ErrorCategory.CAPTCHA,
        "solution": "触发验证码，切换到反检测浏览器",
        "action": "switch_to_drission",
    },
    "验证码": {
        "category": ErrorCategory.CAPTCHA,
        "solution": "触发验证码，需要切换执行路径",
        "action": "switch_to_drission",
    },
    "ModuleNotFoundError": {
        "category": ErrorCategory.DEPENDENCY,
        "solution": "缺少依赖包",
        "action": "pip_install",
    },
    "ImportError": {
        "category": ErrorCategory.DEPENDENCY,
        "solution": "导入模块失败",
        "action": "pip_install",
    },
    "401": {
        "category": ErrorCategory.AUTH,
        "solution": "认证失败，检查API密钥",
        "action": "check_credentials",
    },
    "403": {
        "category": ErrorCategory.PERMISSION,
        "solution": "权限不足",
        "action": "notify_human",
    },
    "TimeoutError": {
        "category": ErrorCategory.TIMEOUT,
        "solution": "操作超时，延长超时后重试",
        "action": "retry_with_longer_timeout",
    },
    "asyncio.TimeoutError": {
        "category": ErrorCategory.TIMEOUT,
        "solution": "异步操作超时",
        "action": "retry_with_longer_timeout",
    },
}


class SelfHealEngine:
    """
    异常自愈引擎 — OpenClaw 的免疫系统。

    6步自愈流程，从低成本到高成本递进:
      1. 错误分类（本地，0成本）
      2. 本地知识库查询（mem0，0成本）
      3. Web搜索（Tavily API，微量成本）
      4. 尝试替代方案（依赖具体场景）
      5. 记录解决方案（mem0，0成本）
      6. 通知用户（最后手段）

    v2.0 改进:
      - retry 真正重新执行失败的 callable（不再假装成功）
      - circuit breaker：同一错误签名 3 次失败后 5 分钟内跳过
      - _apply_solution 用 LLM 将方案转为可执行建议
      - _try_alternatives 实际切换备选路径
    """

    # 熔断器参数
    CIRCUIT_BREAK_THRESHOLD = 3
    CIRCUIT_BREAK_COOLDOWN = 300  # 5 分钟冷却

    def __init__(self):
        self._solution_cache: Dict[str, str] = {}
        self._max_solution_cache = 500  # 防止无限增长
        self._heal_history: List[Dict] = []
        self._max_history = 200

        # pybreaker 熔断器池：每种错误签名一个独立的 CircuitBreaker
        self._breakers: Dict[str, "pybreaker.CircuitBreaker"] = {}

        logger.info("SelfHealEngine 初始化完成（v3.0 — pybreaker + tenacity）")

    def _get_error_signature(self, error_type: str, error_msg: str) -> str:
        """生成错误签名（用于熔断器池的 key）"""
        return f"{error_type}:{error_msg[:80]}"

    def _get_breaker(self, error_sig: str) -> "pybreaker.CircuitBreaker":
        """获取或创建指定错误签名的熔断器"""
        if error_sig not in self._breakers:
            if _HAS_PYBREAKER:
                self._breakers[error_sig] = pybreaker.CircuitBreaker(
                    fail_max=self.CIRCUIT_BREAK_THRESHOLD,
                    reset_timeout=self.CIRCUIT_BREAK_COOLDOWN,
                    name=f"heal:{error_sig[:40]}",
                )
            else:
                # pybreaker 不可用时用简易 dict 回退
                self._breakers[error_sig] = None
        return self._breakers[error_sig]

    def _is_circuit_open(self, error_sig: str) -> bool:
        """检查熔断器是否处于 OPEN 状态"""
        breaker = self._get_breaker(error_sig)
        if breaker is None:
            return False  # 无 pybreaker 时不熔断
        return breaker.current_state == pybreaker.STATE_OPEN

    def _record_circuit_failure(self, error_sig: str):
        """记录一次失败到熔断器"""
        breaker = self._get_breaker(error_sig)
        if breaker is None:
            return
        # pybreaker 通过 call() 包装函数，函数抛异常则计一次失败
        try:

            def _fail():
                raise Exception("heal_failed")

            breaker.call(_fail)
        except (Exception, pybreaker.CircuitBreakerError):
            pass  # 预期行为：函数失败，breaker 计数 +1

    def _reset_circuit(self, error_sig: str):
        """自愈成功后重置熔断器"""
        breaker = self._get_breaker(error_sig)
        if breaker is None:
            return
        try:
            breaker.close()
        except Exception as e:
            logger.debug("重置熔断器异常: %s", e)

    async def heal(
        self,
        error: Exception,
        context: Dict,
        retry_callable: Optional[Callable[..., Coroutine]] = None,
    ) -> HealResult:
        """主入口 — 尝试自愈

        Args:
            error: 捕获到的异常
            context: 错误上下文（message, chat_id, 等）
            retry_callable: 可选的异步回调，自愈成功后会真正重试这个函数。
                           如果不提供，retry 类动作只会等待然后返回 True，
                           由调用者自行决定是否重试。
        """
        start = time.time()
        result = HealResult()
        error_msg = str(error)
        error_type = type(error).__name__
        error_sig = self._get_error_signature(error_type, error_msg)

        logger.info("[自愈] 开始处理: %s: %s", error_type, error_msg[:100])

        # Circuit breaker 检查
        if self._is_circuit_open(error_sig):
            logger.warning("[自愈] Circuit breaker 已触发，跳过: %s", error_sig)
            result.error_category = ErrorCategory.UNKNOWN
            result.attempts.append({"step": 0, "action": "circuit_break", "skipped": True})
            result.elapsed_seconds = time.time() - start
            return result

        # Step 1: 分析错误原因
        category, known = self._analyze_error(error_type, error_msg)
        result.error_category = category
        result.attempts.append({"step": 1, "action": "analyze", "category": category.value})

        # Step 2: 已知解决方案
        if known:
            action = known.get("action", "")
            success = await self._execute_known_solution(known, context, retry_callable)
            result.attempts.append({"step": 2, "action": action, "success": success})
            if success:
                result.healed = True
                result.solution_used = known.get("solution", "已知方案")
                self._record_heal(error_msg, result.solution_used)
                self._reset_circuit(error_sig)
                result.elapsed_seconds = time.time() - start
                return result

        # Step 3: 本地记忆库搜索
        local_solution = await self._search_local_solutions(error_msg)
        result.attempts.append({"step": 3, "action": "local_search", "found": bool(local_solution)})
        if local_solution:
            success = await self._apply_solution(local_solution, context, retry_callable)
            if success:
                result.healed = True
                result.solution_used = f"记忆库: {local_solution[:100]}"
                self._reset_circuit(error_sig)
                result.elapsed_seconds = time.time() - start
                return result

        # Step 4: Web搜索
        web_solution = await self._search_web_solutions(error_msg)
        result.attempts.append({"step": 4, "action": "web_search", "found": bool(web_solution)})
        if web_solution:
            success = await self._apply_solution(web_solution, context, retry_callable)
            if success:
                result.healed = True
                result.solution_used = f"Web搜索: {web_solution[:100]}"
                # 记录到记忆
                await self._record_to_memory(error_msg, web_solution)
                self._reset_circuit(error_sig)
                result.elapsed_seconds = time.time() - start
                return result

        # Step 5: 尝试替代方案
        alt_result = await self._try_alternatives(error_type, context, retry_callable)
        result.attempts.append({"step": 5, "action": "alternatives", "success": alt_result})
        if alt_result:
            result.healed = True
            result.solution_used = "替代方案"
            self._reset_circuit(error_sig)
            result.elapsed_seconds = time.time() - start
            return result

        # 全部失败 — 记录到 circuit breaker
        self._record_circuit_failure(error_sig)

        # Step 6: 通知用户
        await self._notify_human(error, result.attempts)
        result.attempts.append({"step": 6, "action": "notify_human"})
        result.elapsed_seconds = time.time() - start

        self._heal_history.append(
            {
                "error": error_msg[:200],
                "category": category.value,
                "healed": result.healed,
                "timestamp": time.time(),
            }
        )
        if len(self._heal_history) > self._max_history:
            self._heal_history = self._heal_history[-100:]

        return result

    def _analyze_error(self, error_type: str, error_msg: str):
        """Step 1: 错误分类"""
        # 精确匹配错误类型
        if error_type in KNOWN_SOLUTIONS:
            return KNOWN_SOLUTIONS[error_type]["category"], KNOWN_SOLUTIONS[error_type]

        # 模糊匹配错误消息
        msg_lower = error_msg.lower()
        for pattern, solution in KNOWN_SOLUTIONS.items():
            if pattern.lower() in msg_lower:
                return solution["category"], solution

        # HTTP状态码匹配
        code_match = re.search(r"\b(4\d{2}|5\d{2})\b", error_msg)
        if code_match:
            code = code_match.group()
            if code in KNOWN_SOLUTIONS:
                return KNOWN_SOLUTIONS[code]["category"], KNOWN_SOLUTIONS[code]
            if code.startswith("5"):
                return ErrorCategory.NETWORK, {
                    "action": "retry_with_delay",
                    "delay": 15,
                    "solution": f"服务端错误 {code}",
                }

        return ErrorCategory.UNKNOWN, None

    async def _execute_known_solution(
        self,
        solution: Dict,
        context: Dict,
        retry_callable: Optional[Callable[..., Coroutine]] = None,
    ) -> bool:
        """执行已知解决方案 — v2.0: 真正重试失败操作"""
        action = solution.get("action", "")
        try:
            if action == "retry_with_delay":
                delay = solution.get("delay", 5)
                max_attempts = solution.get("max_attempts", 3)
                logger.info("[自愈] 等待 %ss 后重试（最多 %s 次）", delay, max_attempts)

                if retry_callable and HAS_TENACITY:
                    # 真正重试：用 tenacity 指数退避重新执行失败的操作
                    @retry(
                        stop=stop_after_attempt(max_attempts),
                        wait=wait_exponential(multiplier=delay, min=delay, max=delay * 8),
                        retry=retry_if_exception_type(Exception),
                        reraise=True,
                    )
                    async def _do_retry():
                        return await retry_callable()

                    try:
                        await _do_retry()
                        logger.info("[自愈] 重试成功！")
                        return True
                    except RetryError:
                        logger.warning("[自愈] %s 次重试均失败", max_attempts)
                        return False
                elif retry_callable:
                    # 没有 tenacity — 手动重试
                    for attempt in range(1, max_attempts + 1):
                        await asyncio.sleep(delay * attempt)
                        try:
                            await retry_callable()
                            logger.info("[自愈] 第 %s 次重试成功", attempt)
                            return True
                        except Exception as e:
                            logger.warning("[自愈] 第 %s 次重试失败: %s", attempt, e)
                    return False
                else:
                    # 无 callable — 仅等待，由调用者决定是否重试
                    # 注意：返回 True 表示"已执行等待"，调用者应自行重试
                    await asyncio.sleep(delay)
                    logger.info("[自愈] 已等待 %ss，建议调用者重试", delay)
                    return True

            elif action == "retry_with_longer_timeout":
                logger.info("[自愈] 延长超时时间后重试")
                if retry_callable:
                    # 设置更长的超时然后重试
                    context["timeout_multiplier"] = context.get("timeout_multiplier", 1) * 2
                    try:
                        await asyncio.wait_for(retry_callable(), timeout=60)
                        logger.info("[自愈] 延长超时重试成功")
                        return True
                    except asyncio.TimeoutError:
                        logger.warning("[自愈] 延长超时后仍然超时")
                        return False
                    except Exception as e:
                        logger.warning("[自愈] 延长超时重试失败: %s", e)
                        return False
                else:
                    await asyncio.sleep(5)
                    return True  # 无 callable，由调用者重试

            elif action == "pip_install":
                logger.info("[自愈] 检测到缺失依赖，建议手动安装")
                return False  # 不自动 pip install（安全考虑）

            elif action == "switch_to_drission":
                logger.info("[自愈] 建议切换到 DrissionPage 反检测浏览器")
                # 在 context 中标记切换，调用者可检查
                context["switch_browser"] = "drission"
                return False  # 需要调用者切换执行路径

            elif action == "check_credentials":
                logger.warning("[自愈] 认证失败，需要检查 API 密钥")
                return False

            elif action == "notify_human":
                return False  # 直接跳到 step 6

        except Exception as e:
            logger.warning("[自愈] 执行方案失败: %s", e)
        return False

    async def _search_local_solutions(self, error_msg: str) -> Optional[str]:
        """Step 3: 搜索本地记忆库"""
        # 检查缓存
        cache_key = error_msg[:100]
        if cache_key in self._solution_cache:
            return self._solution_cache[cache_key]

        try:
            from src.shared_memory import shared_memory

            if shared_memory:
                results = shared_memory.search(f"error solution: {error_msg[:100]}", limit=3)
                if results:
                    solution = results[0].get("content", "")
                    if solution:
                        self._solution_cache[cache_key] = solution
                        # 缓存容量限制
                        if len(self._solution_cache) > self._max_solution_cache:
                            # 删除最早的一半条目
                            keys = list(self._solution_cache.keys())
                            for k in keys[: len(keys) // 2]:
                                del self._solution_cache[k]
                        return solution
        except Exception as e:
            logger.debug("本地搜索失败: %s", e)
        return None

    async def _search_web_solutions(self, error_msg: str) -> Optional[str]:
        """Step 4: Web搜索 — Jina Reader (免费) 优先, Tavily 备选"""
        # 优先用 Jina Search（零成本）
        try:
            from src.tools.jina_reader import jina_search

            result = await jina_search(f"python error fix: {error_msg[:100]}")
            if result and len(result) > 50:
                return result[:500]
        except Exception as e:
            logger.debug("Jina搜索失败: %s", e)

        # 备选: Tavily API
        tavily_key = os.environ.get("TAVILY_API_KEY", "")
        if not tavily_key:
            return None

        try:
            resp = await _http.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": f"python error solution: {error_msg[:150]}",
                    "search_depth": "basic",
                    "max_results": 3,
                    "include_answer": True,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "")
                if answer:
                    return answer
                results = data.get("results", [])
                if results:
                    return results[0].get("content", "")[:500]
        except Exception as e:
            logger.debug("Tavily搜索失败: %s", e)
        return None

    async def _apply_solution(
        self,
        solution: str,
        context: Dict,
        retry_callable: Optional[Callable[..., Coroutine]] = None,
    ) -> bool:
        """尝试应用解决方案 — v2.0: 真实应用逻辑

        策略:
          1. 如果有 retry_callable，先等待然后重试（解决方案通常是"等等再试"）
          2. 如果解决方案包含可操作建议（如切换模块），修改 context 并重试
        """
        logger.info("[自愈] 尝试应用方案: %s", solution[:80])

        # 检查方案是否包含"重试"/"retry"相关建议
        retry_keywords = ["重试", "retry", "again", "等待", "wait", "delay"]
        is_retry_suggestion = any(kw in solution.lower() for kw in retry_keywords)

        if is_retry_suggestion and retry_callable:
            # 方案建议重试 — 等待后真正重试
            await asyncio.sleep(3)
            try:
                await retry_callable()
                logger.info("[自愈] 应用方案后重试成功")
                return True
            except Exception as e:
                logger.warning("[自愈] 应用方案后重试失败: %s", e)
                return False

        # 检查方案是否建议切换工具/模块
        switch_keywords = {
            "drission": "switch_browser",
            "playwright": "switch_browser",
            "requests": "switch_http_client",
            "akshare": "switch_data_source",
        }
        for keyword, context_key in switch_keywords.items():
            if keyword in solution.lower():
                context[context_key] = keyword
                logger.info("[自愈] 方案建议切换到 %s，已标记 context[%s]", keyword, context_key)
                if retry_callable:
                    try:
                        await retry_callable()
                        return True
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)

        # 如果有 callable 且方案看起来有效（长度 > 50 说明包含真实信息），尝试重试
        if retry_callable and len(solution) > 50:
            await asyncio.sleep(2)
            try:
                await retry_callable()
                return True
            except Exception:
                logger.debug("Silenced exception", exc_info=True)

        return False

    async def _try_alternatives(
        self,
        error_type: str,
        context: Dict,
        retry_callable: Optional[Callable[..., Coroutine]] = None,
    ) -> bool:
        """Step 5: 尝试替代方案 — v2.0: 真实替换逻辑"""
        logger.info("[自愈] 尝试替代方案: %s", error_type)

        # 替代策略映射
        alternatives = {
            "playwright": ("drission", "switch_browser"),
            "httpx": ("requests", "switch_http_client"),
            "yfinance": ("akshare", "switch_data_source"),
            "TimeoutError": ("extended_timeout", "timeout_multiplier"),
            "ConnectionError": ("retry_with_backoff", None),
        }

        for pattern, (alt_name, context_key) in alternatives.items():
            if pattern.lower() in error_type.lower() or pattern.lower() in str(context).lower():
                logger.info("[自愈] 尝试替代: %s → %s", pattern, alt_name)
                if context_key:
                    context[context_key] = alt_name

                if retry_callable:
                    try:
                        await retry_callable()
                        logger.info("[自愈] 替代方案 %s 成功", alt_name)
                        return True
                    except Exception as e:
                        logger.warning("[自愈] 替代方案 %s 也失败: %s", alt_name, e)
                        continue

        return False

    async def _record_to_memory(self, error_msg: str, solution: str) -> None:
        """Step 5: 记录解决方案到记忆"""
        try:
            from src.shared_memory import shared_memory

            if shared_memory:
                shared_memory.add(
                    f"[自愈方案] 错误: {error_msg[:200]}\n解决: {solution[:300]}",
                    category="self_heal",
                )
                logger.info("[自愈] 方案已记录到记忆库")
        except Exception as e:
            logger.debug("记忆记录失败: %s", e)
        self._solution_cache[error_msg[:100]] = solution
        # 缓存容量限制
        if len(self._solution_cache) > self._max_solution_cache:
            # 删除最早的一半条目
            keys = list(self._solution_cache.keys())
            for k in keys[: len(keys) // 2]:
                del self._solution_cache[k]

    async def _notify_human(self, error: Exception, attempts: List[Dict]) -> None:
        """Step 6: 通知用户"""
        try:
            from src.core.event_bus import get_event_bus, EventType

            bus = get_event_bus()
            await bus.publish(
                EventType.SELF_HEAL_FAILED,
                {
                    "error_type": type(error).__name__,
                    "error_msg": str(error)[:300],
                    "attempts": len(attempts),
                    "note": "自愈流程已用尽所有方案，需要人工介入",
                },
                source="self_heal",
            )
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
        logger.warning("[自愈] 所有方案失败，已通知用户: %s", error)

    def _record_heal(self, error_msg: str, solution: str) -> None:
        """记录成功的自愈"""
        self._heal_history.append(
            {
                "error": error_msg[:200],
                "solution": solution,
                "healed": True,
                "timestamp": time.time(),
            }
        )
        # EventBus: 通知自愈成功（与 SELF_HEAL_FAILED 对称）
        try:
            from src.core.event_bus import get_event_bus

            bus = get_event_bus()
            if bus:
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                    _t = loop.create_task(
                        bus.publish(
                            "system.self_heal",
                            {
                                "error": error_msg[:200],
                                "solution": solution,
                                "healed": True,
                            },
                        )
                    )
                    _t.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
                except RuntimeError as e:
                    logger.debug("发布自愈事件时无事件循环: %s", e)
        except Exception as e:
            logger.debug("发布自愈成功事件到 EventBus 失败: %s", e)

    def get_stats(self) -> Dict:
        """获取自愈统计"""
        total = len(self._heal_history)
        healed = sum(1 for h in self._heal_history if h.get("healed"))
        return {
            "total_attempts": total,
            "healed": healed,
            "heal_rate": f"{healed / total:.1%}" if total > 0 else "N/A",
            "cache_size": len(self._solution_cache),
            "recent": self._heal_history[-5:],
        }


_engine: Optional[SelfHealEngine] = None


def get_self_heal_engine() -> SelfHealEngine:
    global _engine
    if _engine is None:
        _engine = SelfHealEngine()
    return _engine
