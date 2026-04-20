"""
LiteLLM 统一路由层 — 替代自研 free_api_pool.py (935行 → ~450行)

核心升级:
- LiteLLM Router: 100+ provider、自动 fallback、cooldown、cost tracking
- 保持旧接口兼容: free_pool.get_best_source() / get_stats() 等
- 零额外进程: 嵌入现有 Python 进程

对标: LiteLLM (39.6k⭐), Portkey Gateway (11k⭐)
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import litellm
from litellm.router import Router

from src.perf_metrics import perf_timer

logger = logging.getLogger(__name__)


def _log_task_exception(task: asyncio.Task) -> None:
    """记录后台任务异常，避免幽灵任务"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("后台任务异常: %s", exc, exc_info=exc)


# ============ LLM 超时常量（秒） ============
# Provider 级别超时 — 根据各平台推理速度和稳定性设定
LLM_TIMEOUT_SILICONFLOW = 45  # SiliconFlow 大模型请求超时
LLM_STREAM_TIMEOUT_SILICONFLOW = 60  # SiliconFlow 流式超时
LLM_TIMEOUT_GROQ = 8  # Groq 极速推理（通常 <3s 完成）
LLM_STREAM_TIMEOUT_GROQ = 15  # Groq 流式超时
LLM_TIMEOUT_REASONING = 90  # 推理模型 (DeepSeek-R1 等) 请求超时
LLM_STREAM_TIMEOUT_REASONING = 120  # 推理模型流式超时
# Router 全局默认
LLM_TIMEOUT_DEFAULT = 15  # 全局默认请求超时
LLM_STREAM_TIMEOUT_DEFAULT = 30  # 全局默认流式超时
LLM_COOLDOWN_TIME = 30  # 模型失败后冷却时间（暂停调度）
LLM_RETRY_AFTER = 5  # 重试前等待时间


def _scrub_secrets(msg: str) -> str:
    """从错误消息中移除 API Key 和敏感 URL — 代理到 utils.scrub_secrets"""
    from src.utils import scrub_secrets

    return scrub_secrets(msg)


# ---- LLM 缓存层 (diskcache, graceful degradation) ----
try:
    from src.llm_cache import _make_cache_key, _get_cache

    _HAS_LLM_CACHE = True

    def _llm_cache_get(key: str):
        cache = _get_cache()
        if cache is None:
            return None
        from src.llm_cache import _stats

        val = cache.get(key)
        if val is not None:
            _stats["hits"] += 1
        else:
            _stats["misses"] += 1
        return val

    def _llm_cache_set(key: str, value, ttl: int):
        cache = _get_cache()
        if cache is not None:
            cache.set(key, value, expire=ttl)

except ImportError:
    _HAS_LLM_CACHE = False
    # llm_cache 模块不可用时，尝试直接使用 diskcache 作为降级方案
    _fallback_cache = None
    try:
        import diskcache as _dc
        from pathlib import Path as _Path
        import hashlib as _hashlib
        import json as _json_cache

        _fallback_cache_dir = _Path(__file__).resolve().parent.parent / "data" / "llm_cache"
        _fallback_cache_dir.mkdir(parents=True, exist_ok=True)
        _fallback_cache = _dc.Cache(
            str(_fallback_cache_dir),
            size_limit=512 * 1024 * 1024,
            eviction_policy="least-recently-used",
        )
        _HAS_LLM_CACHE = True  # diskcache 可用，启用缓存
        logger.info("[LLM Cache] llm_cache 模块不可用，已降级为 diskcache 直连")
    except ImportError:
        logger.info("[LLM Cache] diskcache 未安装，缓存功能禁用")

    def _llm_cache_get(key: str):  # type: ignore[misc]
        # 从降级的 diskcache 中读取缓存
        if _fallback_cache is None:
            return None
        try:
            return _fallback_cache.get(key)
        except Exception:
            return None

    def _llm_cache_set(key: str, value, ttl: int):  # type: ignore[misc]
        # 写入降级的 diskcache 缓存
        if _fallback_cache is None:
            return
        try:
            _fallback_cache.set(key, value, expire=ttl)
        except Exception as e:
            logger.debug("[LLM Cache] 降级缓存写入失败: %s", e)

    def _make_cache_key(*args, **kwargs) -> str:  # type: ignore[misc]
        # 降级版缓存 key 生成：对参数做 SHA-256 哈希
        try:
            raw = _json_cache.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
            return "llm:" + _hashlib.sha256(raw.encode("utf-8")).hexdigest()
        except Exception:
            return ""


# 静默 LiteLLM 内部日志
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("LiteLLM Router").setLevel(logging.WARNING)
logging.getLogger("LiteLLM Proxy").setLevel(logging.WARNING)
litellm.suppress_debug_info = True

# ---- Langfuse 自动集成 ----
# LiteLLM 原生支持 langfuse callback，只需设置 success_callback
# 当 LANGFUSE_SECRET_KEY 存在时自动启用
if os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY"):
    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]
    logger.info("[LiteLLM] Langfuse callback 已启用")

# ---- 路由策略常量 ----
ROUTE_BALANCED = "balanced"

# ---- 模型强度分级 ----
TIER_S, TIER_A, TIER_B, TIER_C = "S", "A", "B", "C"
_TIER_ORDER = {TIER_S: 0, TIER_A: 1, TIER_B: 2, TIER_C: 3}


@dataclass
class FreeAPISource:
    """兼容层: 保持旧接口，内部映射到 LiteLLM deployment"""

    provider: str
    base_url: str
    api_key: str
    model: str
    tier: str = TIER_B
    daily_limit: int = 0
    rpm_limit: int = 0
    used_today: int = 0
    last_used: float = 0
    consecutive_errors: int = 0
    disabled: bool = False
    note: str = ""
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    tpm_limit: int = 0
    max_concurrent: int = 0
    _deployment_id: str = ""

    def can_accept_request(self) -> bool:
        if self.disabled or self.consecutive_errors >= 5:
            return False
        if self.daily_limit > 0 and self.used_today >= self.daily_limit:
            return False
        return True


# ---- 模型强度排名 — T5-3: 优先从 JSON 加载，fallback 到硬编码默认值 ----
_MODEL_RANKING_DEFAULT = {
    "gemini-2.5-pro": 98,
    "gemini-2.5-flash": 97,
    "claude-sonnet-4": 95,
    "gemini-3-flash-preview": 95,
    "moonshotai/kimi-k2-instruct": 94,
    "moonshotai/kimi-k2-instruct:free": 94,
    "deepseek/deepseek-r1-0528:free": 93,
    "DeepSeek-R1": 93,
    "deepseek-r1": 93,
    "o4-mini": 92,
    "Qwen/Qwen3-235B-A22B": 92,
    "qwen/qwen3-235b-a22b:free": 92,
    "qwen3-235b-a22b-instruct": 92,
    "nousresearch/hermes-3-llama-3.1-405b:free": 90,
    "deepseek-ai/DeepSeek-V3-0324": 90,
    "deepseek-v3.2": 90,
    "deepseek-v3": 88,
    "command-a-reasoning-08-2025": 89,
    "command-a-vision-07-2025": 87,
    "command-a-03-2025": 87,
    "gpt-4.1-mini": 86,
    "codestral-latest": 85,
    "kimi-k2": 94,
    "qwen3-max": 91,
    "qwen3-coder-plus": 90,
    "llama-3.3-70b-versatile": 83,
    "llama-3.3-70b": 83,
    "meta-llama/llama-3.3-70b-instruct:free": 83,
    "meta/llama-3.3-70b-instruct": 83,
    "deepseek-r1-distill-llama-70b": 82,
    "openai/gpt-oss-120b:free": 82,
    "compound-ai/compound-beta": 82,
    "qwen/qwen3-coder:free": 82,
    "gemini-2.5-flash-lite": 80,
    "THUDM/GLM-4-32B-0414": 80,
    "qwen/qwen3-32b": 77,
    "qwen3-32b": 77,
    "microsoft/phi-4-reasoning-plus:free": 76,
    "mistral-small-latest": 74,
    "mistralai/mistral-small-3.1-24b-instruct:free": 74,
    "gemma-3-27b-it": 74,
    "google/gemma-3-27b-it:free": 74,
    "meta-llama/llama-4-scout-17b-16e-instruct": 72,
    "llama-4-scout-17b-16e-instruct": 72,
    "nvidia/nemotron-3-super-120b-a12b:free": 90,
    "minimax/minimax-m2.5:free": 88,
    "qwen/qwen3-next-80b-a3b-instruct:free": 85,
    "qwen/qwen3.5-397b-a17b": 93,
    "qwen/qwen3-coder-480b-a35b-instruct": 91,
    "deepseek-ai/deepseek-v3.2": 91,
    "doubao-seed-2-0-pro-260215": 91,
    "doubao-seed-1-6-flash-250828": 85,
    "gpt-4o": 88,
    "gpt-4o-mini": 78,
    "auto": 65,
}


def _load_model_ranking() -> dict:
    """从 JSON 配置加载模型评分，加载失败时回退到硬编码默认值"""
    try:
        from src.llm_routing_config import load_routing_config
        config = load_routing_config()
        if config and config.get("model_ranking"):
            ranking = config["model_ranking"]
            # 过滤掉 _comment 等元数据字段，只保留数值评分
            result = {k: v for k, v in ranking.items() if not k.startswith("_") and isinstance(v, (int, float))}
            if result:
                return result
    except Exception as e:
        logger.debug("[ModelRanking] JSON 加载失败，使用默认值: %s", e)
    return _MODEL_RANKING_DEFAULT.copy()


MODEL_RANKING = _load_model_ranking()


# 构建大小写不敏感的查找表，防止因大小写差异导致模型评分失效 (HI-382 根因)
_MODEL_RANKING_LOWER = {k.lower(): v for k, v in MODEL_RANKING.items()}


def get_model_score(model_id: str) -> float:
    """获取模型强度评分 — 先精确匹配，再大小写不敏感匹配，最后默认 50 分"""
    if model_id in MODEL_RANKING:
        return MODEL_RANKING[model_id]
    return _MODEL_RANKING_LOWER.get(model_id.lower(), 50.0)


# Bot 与 LLM 模型族的映射关系 — 优先从 JSON config 加载，fallback 到硬编码默认值
# T5-2: JSON 为单一真相源，修改 config/llm_routing.json 的 bot_model_family 即可调整
_BOT_MODEL_FAMILY_DEFAULT = {
    "qwen235b": "qwen",
    "gptoss": "gpt-oss",
    "claude_sonnet": "claude",
    "claude_haiku": "qwen",
    "deepseek_v3": "deepseek",
    "claude_opus": "deepseek",
    "free_llm": None,
}


def _load_bot_model_family() -> dict:
    """从 JSON 配置加载 Bot→模型族映射，加载失败时回退到硬编码默认值"""
    try:
        from src.llm_routing_config import load_routing_config
        config = load_routing_config()
        if config and config.get("bot_model_family"):
            mapping = config["bot_model_family"]
            # 过滤掉 _comment 等元数据字段
            result = {k: v for k, v in mapping.items() if not k.startswith("_")}
            if result:
                return result
    except Exception as e:
        logger.debug("[BotModelFamily] JSON 加载失败，使用默认值: %s", e)
    return _BOT_MODEL_FAMILY_DEFAULT.copy()


# 模块加载时初始化（兼容所有 23 个导入点）
BOT_MODEL_FAMILY = _load_bot_model_family()


# ---- iflow Key 有效期监控 ----
# iflow Key 仅有 7 天有效期，这里用本地文件记录首次使用时间，
# 每次初始化时检查是否超过 6 天（给 1 天缓冲），超过则告警并跳过

_IFLOW_TIMESTAMP_FILE = Path.home() / ".openclaw" / "iflow_key_timestamp.json"
_IFLOW_WARN_DAYS = 6  # 超过 6 天发出告警（7天有效期 - 1天缓冲）


def _check_iflow_key_expiry() -> bool:
    """检查 iflow key 是否可能已过期

    读取 ~/.openclaw/iflow_key_timestamp.json 中记录的首次使用时间，
    如果距今超过 6 天则返回 True（表示可能过期）。
    文件不存在或读取失败返回 False（首次使用，视为有效）。
    """
    try:
        if not _IFLOW_TIMESTAMP_FILE.exists():
            return False
        data = json.loads(_IFLOW_TIMESTAMP_FILE.read_text(encoding="utf-8"))
        first_used = data.get("first_used_ts", 0)
        if not first_used:
            return False
        elapsed_days = (time.time() - first_used) / 86400
        if elapsed_days > _IFLOW_WARN_DAYS:
            logger.warning(
                "[iflow] Key 已使用 %.1f 天（阈值 %d 天），可能即将过期",
                elapsed_days,
                _IFLOW_WARN_DAYS,
            )
            return True
        logger.info("[iflow] Key 已使用 %.1f 天，剩余约 %.1f 天", elapsed_days, 7 - elapsed_days)
        return False
    except Exception as e:
        logger.debug("[iflow] 读取 key 时间戳文件失败（视为有效）: %s", e)
        return False


def _record_iflow_key_usage() -> None:
    """记录 iflow key 首次使用时间到本地文件

    仅在文件不存在或 key 值变化时写入。后续调用不会覆盖已有记录。
    """
    try:
        _IFLOW_TIMESTAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
        current_key = os.getenv("SILICONFLOW_UNLIMITED_KEY", "")
        # 用 key 的 SHA256 前8位做指纹（不存明文前缀，防止缩小暴力搜索范围）
        import hashlib
        key_fingerprint = hashlib.sha256(current_key.encode()).hexdigest()[:8] if current_key else ""

        if _IFLOW_TIMESTAMP_FILE.exists():
            data = json.loads(_IFLOW_TIMESTAMP_FILE.read_text(encoding="utf-8"))
            # key 没变就不更新时间戳
            if data.get("key_fingerprint") == key_fingerprint:
                return
            # key 变了 → 用户换了新 key，重置时间戳
            logger.info("[iflow] 检测到 key 变更，重置有效期计时")

        data = {
            "first_used_ts": time.time(),
            "key_fingerprint": key_fingerprint,
            "note": "iflow key 7天有效期，超过6天自动告警",
        }
        _IFLOW_TIMESTAMP_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("[iflow] 已记录 key 首次使用时间")
    except Exception as e:
        logger.debug("[iflow] 记录 key 时间戳失败（不影响功能）: %s", e)


# ============================================================
# LiteLLMPool
# ============================================================


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_list(key: str) -> List[str]:
    return [k.strip() for k in _env(key).split(",") if k.strip()]


class LiteLLMPool:
    """LiteLLM Router 封装，对外保持 FreeAPIPool 兼容接口。"""

    def __init__(self):
        self._router: Optional[Router] = None
        self._sources: Dict[str, List[FreeAPISource]] = {}
        self.default_routing: str = ROUTE_BALANCED
        self._call_count = 0
        self._error_count = 0
        self._total_latency = 0.0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0
        # 并发统计锁 — 多个 Bot 同时调用 LLM 时保护计数器原子更新
        self._stats_lock = asyncio.Lock()

        # Phoenix OTEL — 与 Langfuse 并行运行，OpenTelemetry 标准协议
        try:
            from src.observability import init_phoenix

            init_phoenix()
        except ImportError:
            pass

    @property
    def sources(self) -> Dict[str, List[FreeAPISource]]:
        return self._sources

    def _reg(self, family: str, src: FreeAPISource):
        self._sources.setdefault(family, []).append(src)

    def _dep(
        self,
        name: str,
        model: str,
        key: str,
        base: str = "",
        rpm: int = 0,
        tier: str = TIER_B,
        family: str = "",
        note: str = "",
        timeout: int = 0,
        stream_timeout: int = 0,
    ) -> Dict:
        """创建一个 LiteLLM deployment + 注册 FreeAPISource。

        timeout/stream_timeout: per-model 超时配置（秒）。0 表示使用 Router 全局默认值。
        不同模型应设置差异化超时: Groq(快速推理)→8s, 大模型→30s, Reasoning模型→90s。
        """
        dep_id = f"{name}/{model}"
        params: Dict[str, Any] = {"model": model, "api_key": key}
        if base:
            params["api_base"] = base
        if rpm:
            params["rpm"] = rpm
        # per-model 超时覆盖 Router 全局配置
        if timeout:
            params["timeout"] = timeout
        if stream_timeout:
            params["stream_timeout"] = stream_timeout
        fam = family or name
        self._reg(
            fam,
            FreeAPISource(
                provider=name,
                base_url=base or "",
                api_key=key,
                model=model.split("/", 1)[-1] if "/" in model else model,
                tier=tier,
                rpm_limit=rpm,
                note=note,
                _deployment_id=dep_id,
            ),
        )
        return {"model_name": fam, "litellm_params": params, "model_info": {"id": dep_id, "tier": "free"}}

    def _build_all_deployments(self) -> List[Dict]:
        deps: List[Dict] = []

        # SiliconFlow
        sf_base = "https://api.siliconflow.cn/v1"
        for i, key in enumerate(_env_list("SILICONFLOW_KEYS")):
            if not key:
                continue
            prov = f"siliconflow_{i}"
            for m, fam, t in [
                ("Qwen/Qwen3-235B-A22B-Instruct-2507", "qwen", TIER_S),  # 2026-07 更名
                ("deepseek-ai/DeepSeek-V3.2", "deepseek", TIER_S),  # V3-0324 已下线
                ("Qwen/Qwen3.5-397B-A17B", "qwen", TIER_S),  # 新增最强模型
                ("Qwen/Qwen3-32B", "qwen", TIER_A),  # 备用中等模型
            ]:
                deps.append(
                    self._dep(
                        prov,
                        f"openai/{m}",
                        key,
                        sf_base,
                        tier=t,
                        family=fam,
                        note="SiliconFlow free",
                        timeout=LLM_TIMEOUT_SILICONFLOW,
                        stream_timeout=LLM_STREAM_TIMEOUT_SILICONFLOW,
                    )
                )  # 大模型需要更长超时

        # Groq — 极速推理, 1000RPD (基于官方文档 2026.3)
        gk = _env("GROQ_API_KEY")
        if gk:
            for m, fam, t, r in [
                ("llama-3.3-70b-versatile", "llama", TIER_A, 30),  # 30RPM, 1000RPD, 12K TPM
                ("moonshotai/kimi-k2-instruct", "kimi", TIER_S, 60),  # 60RPM, 1000RPD
                ("openai/gpt-oss-120b", "gpt-oss", TIER_A, 30),  # 30RPM, 1000RPD
                ("qwen/qwen3-32b", "qwen", TIER_B, 60),  # 60RPM, 1000RPD
                ("meta-llama/llama-4-scout-17b-16e-instruct", "llama", TIER_B, 30),
                ("llama-3.1-8b-instant", "llama", TIER_C, 30),  # 30RPM, 14400RPD
                ("llama-3.1-8b-instant", "fast", TIER_A, 30),  # "fast" family 快速推理专用
            ]:
                deps.append(
                    self._dep(
                        "groq",
                        f"groq/{m}",
                        gk,
                        rpm=r,
                        tier=t,
                        family=fam,
                        note=f"Groq free {r}RPM",
                        timeout=LLM_TIMEOUT_GROQ,
                        stream_timeout=LLM_STREAM_TIMEOUT_GROQ,
                    )
                )  # Groq 极速推理，短超时

        # Cerebras — 免费高速推理，优先接入官方当前公开模型
        ck = _env("CEREBRAS_API_KEY")
        if ck:
            for m, fam, t in [
                ("gpt-oss-120b", "gpt-oss", TIER_A),
                ("llama3.1-8b", "llama", TIER_C),
            ]:
                deps.append(
                    self._dep("cerebras", f"cerebras/{m}", ck, rpm=30, tier=t, family=fam, note="Cerebras free 30RPM")
                )

        # Gemini — 2.5/3.x 系，移除已废弃的 2.0 系
        gk2 = _env("GEMINI_API_KEY")
        if gk2:
            for m, t, r in [
                ("gemini-2.5-flash", TIER_S, 5),
                ("gemini-2.5-flash-lite", TIER_A, 10),
                ("gemini-3-flash-preview", TIER_A, 5),
            ]:
                deps.append(
                    self._dep("google", f"gemini/{m}", gk2, rpm=r, tier=t, family="gemini", note="Google AI Studio")
                )

        # OpenRouter — 免费模型, ~20RPM 动态限制
        ork = _env("OPENROUTER_API_KEY")
        if ork:
            for m, fam, t in [
                ("nousresearch/hermes-3-llama-3.1-405b:free", "llama", TIER_S),
                ("nvidia/nemotron-3-super-120b-a12b:free", "llama", TIER_S),
                ("minimax/minimax-m2.5:free", "minimax", TIER_S),
                ("openai/gpt-oss-120b:free", "gpt-oss", TIER_A),
                ("qwen/qwen3-coder:free", "qwen", TIER_A),
                ("qwen/qwen3-next-80b-a3b-instruct:free", "qwen", TIER_A),
                ("meta-llama/llama-3.3-70b-instruct:free", "llama", TIER_A),
                ("mistralai/mistral-small-3.1-24b-instruct:free", "mistral", TIER_B),
                ("google/gemma-3-27b-it:free", "gemma", TIER_B),
                ("stepfun/step-3.5-flash:free", "stepfun", TIER_B),
            ]:
                deps.append(
                    self._dep("openrouter", f"openrouter/{m}", ork, rpm=20, tier=t, family=fam, note="OpenRouter free")
                )

        # Mistral — 免费层限制严格，仅作中后位兜底
        mk = _env("MISTRAL_API_KEY")
        if mk:
            deps.append(
                self._dep(
                    "mistral",
                    "mistral/mistral-small-latest",
                    mk,
                    rpm=1,
                    tier=TIER_B,
                    family="mistral",
                    note="Mistral free 1RPM",
                )
            )
            deps.append(
                self._dep(
                    "mistral",
                    "mistral/mistral-large-latest",
                    mk,
                    rpm=1,
                    tier=TIER_A,
                    family="mistral",
                    note="Mistral free 1RPM",
                )
            )
            deps.append(
                self._dep(
                    "mistral",
                    "mistral/codestral-latest",
                    mk,
                    rpm=30,
                    tier=TIER_A,
                    family="mistral",
                    note="Mistral Codestral 30RPM",
                )
            )

        # Cohere — 20RPM / 1000次月额度，不做主链最前排
        cok = _env("COHERE_API_KEY")
        if cok:
            for m, t in [("command-a-reasoning-08-2025", TIER_A), ("command-a-vision-07-2025", TIER_B)]:
                deps.append(self._dep("cohere", f"cohere/{m}", cok, rpm=20, tier=t, family="cohere", note="Cohere"))

        # GitHub Models (免费, 限制严格但模型丰富)
        ght = _env("GITHUB_MODELS_TOKEN")
        if ght:
            ghb = "https://models.github.ai/inference"
            for m, fam, t in [
                ("gpt-4.1-mini", "gpt", TIER_A),
                ("o4-mini", "gpt", TIER_S),
                ("DeepSeek-R1", "deepseek", TIER_S),
                ("DeepSeek-V3-0324", "deepseek", TIER_A),
                ("Llama-3.3-70B-Instruct", "llama", TIER_A),
                ("Mistral-Small-3.1", "mistral", TIER_B),
            ]:
                deps.append(
                    self._dep("github", f"openai/{m}", ght, ghb, rpm=15, tier=t, family=fam, note="GitHub Models")
                )

        # Kiro Gateway
        kk = _env("KIRO_API_KEY")
        kb = _env("KIRO_BASE_URL", "http://127.0.0.1:18793/v1")
        if kk:
            deps.append(
                self._dep(
                    "kiro",
                    "openai/claude-sonnet-4",
                    kk,
                    kb,
                    rpm=5,
                    tier=TIER_S,
                    family="claude",
                    timeout=45,  # 显式超时（Claude 处理金融分析 prompt 需要 30s+）
                    stream_timeout=60,
                    note="Kiro Gateway",
                )
            )

        # NVIDIA NIM (信用额度制, ~60RPM, 试用额度用完需购买AI Enterprise)
        # 2026-04 更新: deepseek-r1 已下线→deepseek-v3.2, qwen3-235b 不存在→qwen3.5-397b
        nk = _env("NVIDIA_NIM_API_KEY")
        if nk:
            for m, fam, t in [
                ("meta/llama-3.3-70b-instruct", "llama", TIER_A),
                ("deepseek-ai/deepseek-v3.2", "deepseek", TIER_S),  # deepseek-r1 已下线
                ("qwen/qwen3.5-397b-a17b", "qwen", TIER_S),  # qwen3-235b-a22b-instruct 不存在
                ("qwen/qwen3-coder-480b-a35b-instruct", "qwen", TIER_S),  # 新增 coder 模型
            ]:
                deps.append(self._dep("nvidia", f"nvidia_nim/{m}", nk, rpm=60, tier=t, family=fam, note="NVIDIA NIM"))

        # Sambanova (免费 $5 额度, 推理极快)
        sk = _env("SAMBANOVA_API_KEY")
        if sk:
            sb = "https://api.sambanova.ai/v1"
            for m, fam, t, to in [
                ("DeepSeek-R1", "deepseek", TIER_S, LLM_TIMEOUT_REASONING),
                ("DeepSeek-V3.2", "deepseek", TIER_A, LLM_TIMEOUT_DEFAULT),
                ("Meta-Llama-3.3-70B-Instruct", "llama", TIER_A, LLM_TIMEOUT_DEFAULT),
                ("Qwen/Qwen3-235B", "qwen", TIER_S, LLM_TIMEOUT_DEFAULT),
            ]:
                deps.append(
                    self._dep(
                        "sambanova", f"openai/{m}", sk, sb,
                        rpm=10, tier=t, family=fam,
                        timeout=to, stream_timeout=to + 30,
                        note="Sambanova Cloud",
                    )
                )

        # iflow 无限 API（硅基流分配，14个顶级模型，无限使用）
        # Fireworks AI (免费 $1 额度, 推理快, Llama-4 系列)
        fwk = _env("FIREWORKS_API_KEY")
        if fwk:
            fwb = "https://api.fireworks.ai/inference/v1"
            for m, fam, t in [
                ("accounts/fireworks/models/llama4-scout-instruct-basic", "llama", TIER_A),
                ("accounts/fireworks/models/llama-v3p3-70b-instruct", "llama", TIER_A),
                ("accounts/fireworks/models/deepseek-v3", "deepseek", TIER_A),
            ]:
                deps.append(
                    self._dep("fireworks", f"openai/{m}", fwk, fwb, rpm=10, tier=t, family=fam, note="Fireworks AI")
                )

        # Cloudflare Workers AI (永久免费 10000 neurons/天)
        cfk = _env("CLOUDFLARE_API_TOKEN")
        cf_acct = _env("CLOUDFLARE_ACCOUNT_ID")
        if cfk and cf_acct:
            cfb = f"https://api.cloudflare.com/client/v4/accounts/{cf_acct}/ai/v1"
            for m, fam, t in [
                ("@cf/openai/gpt-oss-120b", "gpt", TIER_S),
                ("@cf/qwen/qwen3-30b-a3b-fp8", "qwen", TIER_B),
                ("@cf/meta/llama-3.3-70b-instruct-fp8-fast", "llama", TIER_A),
            ]:
                deps.append(
                    self._dep("cloudflare", f"openai/{m}", cfk, cfb, rpm=30, tier=t, family=fam, note="Cloudflare Workers AI")
                )

        # ⚠️ iflow Token 有效期仅 7 天，过期需去 https://platform.iflow.cn/docs/api-key-management 重置
        iflow_key = _env("SILICONFLOW_UNLIMITED_KEY")
        iflow_base = _env("SILICONFLOW_UNLIMITED_URL", "https://apis.iflow.cn/v1")
        if iflow_key:
            logger.warning("iFlow 无限 key 有效期仅 7 天，请注意定期续期")
            # 检查 iflow key 是否可能已过期（7天有效期，给1天缓冲，超6天告警）
            iflow_expired = _check_iflow_key_expiry()
            if iflow_expired:
                logger.warning(
                    "⚠️⚠️⚠️ [iflow] Key 已使用超过 6 天，可能即将或已经过期！"
                    "请尽快去 https://platform.iflow.cn/docs/api-key-management 重置。"
                    "本次启动将跳过 iflow deployments。"
                )
            else:
                # Key 未过期，正常注册 iflow deployments
                # 记录本次使用时间（首次使用时创建记录）
                _record_iflow_key_usage()
                # 去掉 /chat/completions 后缀（LiteLLM 会自动加）
                iflow_base = iflow_base.replace("/chat/completions", "")
                for m, fam, t in [
                    # instruct/非thinking版优先（速度快、有内容输出）
                    ("qwen3-235b-a22b-instruct", "qwen", TIER_S),
                    ("deepseek-v3.2", "deepseek", TIER_S),
                    ("kimi-k2", "kimi", TIER_S),
                    ("qwen3-max", "qwen", TIER_S),
                    ("qwen3-coder-plus", "qwen", TIER_S),
                    ("deepseek-r1", "deepseek", TIER_S),  # reasoning model
                    ("deepseek-v3", "deepseek", TIER_A),
                    ("qwen3-vl-plus", "qwen", TIER_A),  # vision model
                    ("qwen3-32b", "qwen", TIER_A),
                    ("qwen3-235b", "qwen", TIER_B),  # thinking model（慢，备用）
                ]:
                    deps.append(
                        self._dep(
                            "iflow",
                            f"openai/{m}",
                            iflow_key,
                            iflow_base,
                            rpm=500,
                            tier=t,
                            family=fam,
                            note="iflow unlimited",
                        )
                    )

        # 硅基流动付费Key池 (10条, 14元/条, 未实名, ⚠️禁止Pro模型)
        # v3.0: 免费模型保持原 family; 实际扣费模型隔离到 _paid family
        # 用户说"用付费模型"时才会路由到 _paid family
        sf_paid_keys = _env_list("SILICONFLOW_PAID_KEYS")
        sf_paid_base = _env("SILICONFLOW_PAID_BASE_URL", "https://api.siliconflow.cn/v1")
        if sf_paid_keys:
            for i, key in enumerate(sf_paid_keys):
                prov = f"sf_paid_{i}"
                # 免费模型 (不扣余额) → 保持原 family, 增加免费Key容量
                for m, fam, t in [
                    ("Qwen/Qwen3-235B-A22B-Instruct-2507", "qwen", TIER_S),  # 2026-07 更名
                    ("deepseek-ai/DeepSeek-V3.2", "deepseek", TIER_S),
                    ("Qwen/Qwen3.5-397B-A17B", "qwen", TIER_S),
                    ("Qwen/Qwen3-32B", "qwen", TIER_A),
                ]:
                    deps.append(
                        self._dep(
                            prov,
                            f"openai/{m}",
                            key,
                            sf_paid_base,
                            tier=t,
                            family=fam,
                            note=f"SiliconFlow paid #{i} (free model)",
                        )
                    )
                # 扣费模型 → 隔离到 _paid family, 不会被默认路由命中
                for m, fam, t in [
                    ("deepseek-ai/DeepSeek-R1", "deepseek_paid", TIER_S),
                    ("deepseek-ai/DeepSeek-V3", "deepseek_paid", TIER_A),
                ]:
                    deps.append(
                        self._dep(
                            prov,
                            f"openai/{m}",
                            key,
                            sf_paid_base,
                            tier=t,
                            family=fam,
                            note=f"SiliconFlow paid #{i} (PAID, gated)",
                        )
                    )

        # Volcengine 火山引擎
        # 2026-04: doubao-pro-256k 已下线(Shutdown)，需在 Ark Console 激活新模型后再启用
        # 可用候选: doubao-seed-2-0-pro-260215, doubao-seed-1-6-251015, deepseek-v3-2-251201
        # ⚠️ 当前账号未激活任何新模型，暂时配置最新可用版本，用户需去 Ark Console 激活
        vk = _env("VOLCENGINE_API_KEY")
        vb = _env("VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        if vk:
            for m, fam, t in [
                ("doubao-seed-2-0-pro-260215", "doubao", TIER_S),  # 最新旗舰
                ("doubao-seed-1-6-flash-250828", "doubao", TIER_A),  # 快速版
            ]:
                deps.append(
                    self._dep(
                        "volcengine",
                        f"openai/{m}",
                        vk,
                        vb,
                        rpm=10,
                        tier=t,
                        family=fam,
                        note="Volcengine (需 Ark Console 激活)",
                    )
                )

        # GPT_API_Free (免费: gpt-5/4o系5次/天, deepseek系30次/天, mini系200次/天)
        gpk = _env("GPT_API_FREE_KEY")
        gpb = _env("GPT_API_FREE_BASE_URL", "https://api.gpt.ge/v1")
        if gpk:
            for m, fam, t, r in [
                ("gpt-4o", "gpt", TIER_S, 2),  # 5/day
                ("gpt-4o-mini", "gpt", TIER_A, 5),  # 200/day
                ("deepseek-r1", "deepseek", TIER_S, 2),  # 30/day
                ("deepseek-v3", "deepseek", TIER_A, 2),  # 30/day
            ]:
                deps.append(
                    self._dep("gpt_free", f"openai/{m}", gpk, gpb, rpm=r, tier=t, family=fam, note="GPT_API_Free")
                )

        # g4f 兜底（降级为 TIER_C，仅作最后手段）
        # 2026-04: g4f 响应较慢(30-90s)，超时设为 90s 防止误判不可用
        # 2026-04-13: g4f 服务端现在要求 API Key 认证，从环境变量读取
        g4f_base = _env("G4F_BASE_URL", "http://127.0.0.1:18891/v1")
        g4f_key = _env("G4F_API_KEY", "dummy")
        deps.append(
            self._dep(
                "g4f",
                "openai/auto",
                g4f_key,
                g4f_base,
                tier=TIER_C,
                family="g4f",
                note="g4f fallback (TIER_C)",
                timeout=LLM_TIMEOUT_REASONING,
                stream_timeout=LLM_STREAM_TIMEOUT_REASONING,
            )
        )

        return deps

    # ---- 初始化 ----

    def initialize(self):
        """构建 deployments 并初始化 LiteLLM Router

        优先从 config/llm_routing.json 加载配置（P2-1 JSON Config 驱动），
        JSON 不存在或为空时回退到硬编码的 _build_all_deployments()。
        """
        # 尝试从 JSON 配置加载（借鉴 Portkey AI Gateway 的 Config 驱动模式）
        deps = []
        fallbacks = []
        try:
            from src.llm_routing_config import (
                load_routing_config,
                build_deployments_from_config,
                build_fallbacks_from_config,
                get_router_config,
            )

            self._routing_config = load_routing_config()
            if self._routing_config and self._routing_config.get("providers"):
                deps = build_deployments_from_config(self._routing_config, self._dep)
                if deps:
                    families = set(d["model_name"] for d in deps)
                    fallbacks = build_fallbacks_from_config(self._routing_config, families)
                    logger.info(f"[LiteLLMPool] JSON Config 加载成功: {len(deps)} deployments")
        except Exception as e:
            logger.warning(f"[LiteLLMPool] JSON Config 加载失败，回退到硬编码: {e}")
            deps = []

        # 回退: 硬编码的 _build_all_deployments()
        if not deps:
            deps = self._build_all_deployments()
            if not deps:
                logger.warning("[LiteLLMPool] 无可用 deployment")
                return
            families = set(d["model_name"] for d in deps)
            # 硬编码 fallback 链
            fallbacks = []
            for f in families:
                if f == "g4f":
                    continue
                chain = []
                if f != "qwen" and "qwen" in families:
                    chain.append("qwen")
                if f != "deepseek" and "deepseek" in families:
                    chain.append("deepseek")
                chain.append("g4f")
                fallbacks.append({f: chain})

        families = set(d["model_name"] for d in deps)

        try:
            # 从 JSON router_config 读取参数（T5-2: 消除硬编码，JSON 为单一真相源）
            from litellm.router import RetryPolicy

            rc = {}
            if hasattr(self, "_routing_config") and self._routing_config:
                rc = get_router_config(self._routing_config)

            self._router = Router(
                model_list=deps,
                fallbacks=fallbacks,
                num_retries=rc.get("num_retries", 3),
                timeout=rc.get("timeout", LLM_TIMEOUT_DEFAULT),
                stream_timeout=rc.get("stream_timeout", LLM_STREAM_TIMEOUT_DEFAULT),
                allowed_fails=rc.get("allowed_fails", 3),
                cooldown_time=rc.get("cooldown_time", LLM_COOLDOWN_TIME),
                retry_after=rc.get("retry_after", LLM_RETRY_AFTER),
                routing_strategy=rc.get("routing_strategy", "simple-shuffle"),
                # 按错误类型区分重试策略（官方推荐）
                retry_policy=RetryPolicy(
                    RateLimitErrorRetries=3,  # 429 限速适当重试
                    TimeoutErrorRetries=2,  # 超时少量重试（已有 fallback 兜底）
                    ContentPolicyViolationErrorRetries=0,  # 内容违规不重试
                    AuthenticationErrorRetries=0,  # 认证错误不重试
                    InternalServerErrorRetries=2,  # 服务器错误少量重试
                ),
            )
            logger.info(f"[LiteLLMPool] Router OK: {len(deps)} deployments, {len(families)} groups")
            # 标记待发送启动健康摘要（等第一次 async 调用时发送）
            self._startup_summary_pending = True
        except Exception as e:
            logger.error(f"[LiteLLMPool] Router init failed: {_scrub_secrets(str(e))}")
            self._router = None

    # ---- 核心调用 ----

    @perf_timer("llm.acompletion")
    async def acompletion(
        self,
        model_family: Optional[str],
        messages: List[Dict],
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        cache_ttl: int = 3600,
        no_cache: bool = False,
        **kwargs,
    ):
        """统一 LLM 调用入口，替代 api_mixin 中所有手写 HTTP 调用

        Args:
            cache_ttl: Cache TTL in seconds (default 3600). 0 disables cache.
            no_cache: Force bypass cache for this request.
        """
        if not self._router:
            raise RuntimeError("LiteLLMPool 未初始化")

        # 首次被调用时，在后台发送启动健康摘要（不阻塞当前请求）
        if getattr(self, "_startup_summary_pending", False):
            self._startup_summary_pending = False
            import asyncio

            _task = asyncio.create_task(self.send_startup_health_summary())
            _task.add_done_callback(_log_task_exception)

        # ── 智能路由: 根据查询复杂度 + 预算状态自动选模型 ──
        # 调用方传了 model_family 则尊重（如 FAMILY_CLAUDE 显式请求）
        # 未传时，按消息复杂度+预算余量自动选择，避免简单查询浪费贵模型
        if model_family:
            model = model_family
        else:
            complexity = self._estimate_complexity(messages, max_tokens)
            model = self._smart_route(complexity)

        all_msgs = ([{"role": "system", "content": system_prompt}] + messages) if system_prompt else messages

        # ---- Cache layer (non-streaming only) ----
        use_cache = not stream and not no_cache and cache_ttl > 0 and _HAS_LLM_CACHE

        if use_cache:
            cache_key = _make_cache_key(all_msgs, model, temperature)
            try:
                cached = _llm_cache_get(cache_key)
                if cached is not None:
                    logger.debug(f"[LiteLLMPool] cache HIT key={cache_key[:16]}… model={model}")
                    return cached
            except Exception:
                logger.debug("Silenced exception", exc_info=True)  # Cache read error → fall through to LLM

        start = time.time()
        try:
            # 流式请求需要 stream_options 才能获取 final chunk 中的 usage 信息
            if stream:
                kwargs.setdefault("stream_options", {"include_usage": True})

            response = await self._router.acompletion(
                model=model,
                messages=all_msgs,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                **kwargs,
            )

            if stream:
                # Streaming: wrap to capture token usage from final chunk
                return self._wrap_streaming(response, model, start)

            latency = (time.time() - start) * 1000
            async with self._stats_lock:
                self._call_count += 1
                self._total_latency += latency
                if hasattr(response, "usage") and response.usage:
                    self._total_input_tokens += getattr(response.usage, "prompt_tokens", 0)
                    self._total_output_tokens += getattr(response.usage, "completion_tokens", 0)
                    # Calculate cost from LiteLLM response
                    try:
                        cost = litellm.completion_cost(completion_response=response)
                        self._total_cost += cost
                    except Exception:
                        logger.debug("Silenced exception", exc_info=True)  # Free models have no cost data

            # ---- Store to cache ----
            if use_cache:
                try:
                    _llm_cache_set(cache_key, response, cache_ttl)
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)  # Cache write error → ignore

            return response
        except Exception as e:
            async with self._stats_lock:
                self._error_count += 1
            scrubbed = _scrub_secrets(str(e))
            logger.error(f"[LiteLLMPool] acompletion failed (model={model}): {scrubbed}")
            # 全链路降级到 g4f 时通知管理员（意味着所有优质 provider 都挂了）
            if model == "g4f" or "g4f" in str(e).lower():
                try:
                    from src.core.event_bus import get_event_bus, EventType

                    await get_event_bus().publish(
                        EventType.SYSTEM_ALERT,
                        {"level": "warning", "message": f"LLM 全链路降级到 g4f 兜底: {scrubbed[:100]}"},
                        source="litellm_router",
                    )
                except Exception as e:
                    logger.debug("发布LLM降级告警事件失败(可忽略): %s", e)
            raise

    # ── 智能路由（RouteLLM 风格，零额外依赖）──────────────

    def _estimate_complexity(self, messages: list, max_tokens: int) -> str:
        """根据消息特征估算查询复杂度（零 LLM 成本，纯规则）

        返回: "simple" / "moderate" / "complex" / "critical"
        """
        if not messages:
            return "simple"

        # 最后一条用户消息
        last_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_msg = m.get("content", "")
                break

        msg_len = len(last_msg)
        msg_count = len(messages)

        # 简单查询：短消息 + 少量上下文
        if msg_len < 50 and msg_count <= 3:
            return "simple"

        # 关键任务：包含交易/投资决策关键词
        critical_kw = {"买入", "卖出", "下单", "交易", "ibuy", "isell", "execute", "confirm"}
        if any(kw in last_msg.lower() for kw in critical_kw):
            return "critical"

        # 复杂查询：长消息 或 多轮上下文 或 需要大量输出
        if msg_len > 500 or msg_count > 15 or max_tokens > 8000:
            return "complex"

        # 中等复杂度
        return "moderate"

    def _smart_route(self, complexity: str) -> str:
        """根据复杂度 + 预算状态选择最优模型族

        利用 cost_control.py 已有的 COMPLEXITY_TO_MODEL 映射 + suggest_model()
        T5-4: model_to_family 映射从 JSON 配置加载
        """
        try:
            from src.core.cost_control import get_cost_controller

            cc = get_cost_controller()
            # suggest_model 已内置预算降级逻辑（>70%用免费，>90%强制免费）
            suggested = cc.suggest_model(complexity)
            # 从 JSON 配置加载 model→family 映射，fallback 到硬编码默认值
            model_to_family = self._get_smart_route_mapping()
            family = model_to_family.get(suggested, "qwen")
            logger.debug("[SmartRoute] 复杂度=%s → 建议=%s → family=%s", complexity, suggested, family)
            return family
        except Exception as e:
            logger.debug("[SmartRoute] 降级到 _pick_strongest_family: %s", e)
            return self._pick_strongest_family()

    def _get_smart_route_mapping(self) -> dict:
        """获取 smart_route 的 model→family 映射 — 优先从 JSON 加载"""
        _default = {
            "qwen3-235b": "qwen",
            "claude-haiku-3.5": "claude",
            "claude-sonnet-4": "claude",
            "claude-opus-4": "claude",
            "deepseek-v3": "deepseek",
            "gemini-2.5-flash": "gemini",
        }
        try:
            if hasattr(self, "_routing_config") and self._routing_config:
                mapping = self._routing_config.get("smart_route_model_to_family", {})
                result = {k: v for k, v in mapping.items() if not k.startswith("_")}
                if result:
                    return result
        except Exception as e:
            logger.warning("[Router] 模型路由映射解析失败: %s", e)
        return _default

    def _pick_strongest_family(self) -> str:
        best_fam, best_score = "g4f", 0
        for fam, sources in self._sources.items():
            for src in sources:
                if src.can_accept_request():
                    score = get_model_score(src.model)
                    if score > best_score:
                        best_score = score
                        best_fam = fam
        return best_fam

    async def _wrap_streaming(self, response, model: str, start_time: float):
        """Wrap streaming response to capture token usage from the final chunk.

        LiteLLM streaming responses carry usage info in the last chunk
        (when stream_options={"include_usage": True} or provider supports it).
        This wrapper tallies tokens and records cost after the stream completes.
        """
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        async for chunk in response:
            # Many providers include usage in the final chunk
            if hasattr(chunk, "usage") and chunk.usage:
                prompt_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
                total_tokens = getattr(chunk.usage, "total_tokens", 0) or 0
            yield chunk

        # After stream completes, record metrics（加锁保护统计计数器）
        latency = (time.time() - start_time) * 1000
        async with self._stats_lock:
            self._call_count += 1
            self._total_latency += latency

            if total_tokens > 0 or (prompt_tokens + completion_tokens) > 0:
                self._total_input_tokens += prompt_tokens
                self._total_output_tokens += completion_tokens
                try:
                    cost = litellm.completion_cost(
                        model=model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
                    self._total_cost += cost
                except Exception:
                    logger.debug("Silenced exception", exc_info=True)

    # ---- 兼容旧接口 ----

    def get_best_source(
        self, model_family: str, min_tier: str = TIER_C, routing: Optional[str] = None
    ) -> Optional[FreeAPISource]:
        min_val = _TIER_ORDER.get(min_tier, 3)
        avail = [
            s
            for s in self._sources.get(model_family, [])
            if s.can_accept_request() and _TIER_ORDER.get(s.tier, 9) <= min_val
        ]
        if not avail:
            return None
        avail.sort(key=lambda s: -get_model_score(s.model))
        return avail[0]

    def get_any_source(
        self, min_tier: str = TIER_C, routing: Optional[str] = None
    ) -> Optional[Tuple[str, FreeAPISource]]:
        min_val = _TIER_ORDER.get(min_tier, 3)
        best, best_score, best_fam = None, -1, ""
        for fam, sources in self._sources.items():
            for s in sources:
                if s.can_accept_request() and _TIER_ORDER.get(s.tier, 9) <= min_val:
                    score = get_model_score(s.model)
                    if score > best_score:
                        best, best_score, best_fam = s, score, fam
        return (best_fam, best) if best else None

    def add_source(self, model_family: str, source: FreeAPISource):
        self._reg(model_family, source)

    def reset_daily_counters(self):
        for sources in self._sources.values():
            for src in sources:
                src.used_today = 0
                src.consecutive_errors = 0
                src.disabled = False

    # REMOVED: remove_exhausted() - 已废弃，无调用者（LiteLLM Router 内置 cooldown 机制）

    def get_stats(self) -> Dict:
        total = sum(len(v) for v in self._sources.values())
        active = sum(1 for v in self._sources.values() for s in v if s.can_accept_request())
        avg_lat = self._total_latency / max(self._call_count, 1)
        return {
            "total_sources": total,
            "active_sources": active,
            "model_families": len(self._sources),
            "routing_strategy": "litellm-router",
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
            "total_cost_usd": round(self._total_cost, 6),
            "avg_latency_ms": round(avg_lat, 1),
            "total_calls": self._call_count,
            "total_errors": self._error_count,
            "success_rate": round((self._call_count - self._error_count) / max(self._call_count, 1), 3),
            "families": {
                k: {
                    "total": len(v),
                    "active": sum(1 for s in v if s.can_accept_request()),
                    "total_requests": sum(s.used_today for s in v),
                }
                for k, v in self._sources.items()
            },
            "by_provider": self._stats_by_provider(),
            "engine": "litellm",
        }

    def _stats_by_provider(self) -> Dict:
        provs: Dict[str, Dict] = {}
        for sources in self._sources.values():
            for s in sources:
                p = s.provider
                if p not in provs:
                    provs[p] = {"models": 0, "active": 0, "requests_today": 0, "errors": 0}
                provs[p]["models"] += 1
                provs[p]["active"] += 1 if s.can_accept_request() else 0
                provs[p]["requests_today"] += s.used_today
                provs[p]["errors"] += s.consecutive_errors
        return provs

    async def send_startup_health_summary(self) -> None:
        """启动完成后向管理员推送 AI 引擎健康摘要"""
        try:
            stats = self.get_stats()
            total = stats["total_sources"]
            active = stats["active_sources"]
            families_count = stats["model_families"]
            families = stats.get("families", {})

            # 按在线/离线分组
            online_parts = []
            offline_parts = []
            for fam_name, fam_info in families.items():
                fam_active = fam_info.get("active", 0)
                if fam_active > 0:
                    online_parts.append(f"{fam_name}({fam_active})")
                else:
                    offline_parts.append(f"{fam_name}(0)")

            # 拼接摘要消息
            lines = [
                "🤖 AI 引擎启动完成",
                "",
                f"📊 {active}/{total} 个模型在线，覆盖 {families_count} 个模型族",
                "",
            ]
            if online_parts:
                lines.append(f"✅ 在线: {' '.join(online_parts)}")
            if offline_parts:
                lines.append(f"❌ 离线: {' '.join(offline_parts)}")
            lines.append("")
            lines.append("💡 说「模型」查看详细状态")
            summary = "\n".join(lines)

            # 通过 Telegram Bot 发送给所有管理员
            from src.bot.globals import bot_registry, ALLOWED_USER_IDS

            bot = next(iter(bot_registry.values()), None)
            if bot and hasattr(bot, "application"):
                for uid in ALLOWED_USER_IDS:
                    try:
                        await bot.application.bot.send_message(chat_id=int(uid), text=summary)
                    except Exception as e:
                        logger.debug("向管理员 %s 发送启动摘要失败: %s", uid, e)
            else:
                logger.debug("Bot 尚未就绪，跳过启动健康摘要推送")
        except Exception as e:
            logger.debug("发送启动健康摘要失败(不影响正常运行): %s", e)

    async def health_check(self, timeout: float = 10.0) -> Dict:
        """启动时健康检查 — 快速 ping 每个 provider，禁用不可用的。

        Returns:
            {"checked": N, "healthy": N, "disabled": [...], "elapsed_s": float}
        """
        import asyncio

        start = time.time()
        checked = 0
        healthy = 0
        disabled_providers = []

        # Group sources by provider to avoid redundant checks
        providers_seen: Dict[str, bool] = {}

        for family, sources in self._sources.items():
            for src in sources:
                if src.provider in providers_seen:
                    # Apply same result
                    if not providers_seen[src.provider]:
                        src.disabled = True
                    continue

                checked += 1
                try:
                    # Minimal ping: 1-token completion with short timeout
                    await asyncio.wait_for(
                        self.acompletion(
                            model_family=family,
                            messages=[{"role": "user", "content": "hi"}],
                            max_tokens=1,
                            temperature=0,
                        ),
                        timeout=timeout,
                    )
                    providers_seen[src.provider] = True
                    healthy += 1
                except Exception as e:
                    logger.warning(f"[健康检查] {src.provider}/{src.model} 不可用: {_scrub_secrets(str(e))}")
                    providers_seen[src.provider] = False
                    src.disabled = True
                    disabled_providers.append(f"{src.provider}/{src.model}")

        # Mark all sources of failed providers as disabled
        for family, sources in self._sources.items():
            for src in sources:
                if src.provider in providers_seen and not providers_seen[src.provider]:
                    src.disabled = True

        elapsed = time.time() - start
        result = {
            "checked": checked,
            "healthy": healthy,
            "disabled": disabled_providers,
            "elapsed_s": round(elapsed, 2),
        }
        logger.info(
            f"[健康检查] {healthy}/{checked} providers 可用, 禁用 {len(disabled_providers)} 个, 耗时 {elapsed:.1f}s"
        )
        return result

    # ---- API Key 验证 (按 provider 逐 key 检测) ----

    _MULTI_KEY_PREFIXES = {
        "siliconflow_": "siliconflow_free",
        "sf_paid_": "siliconflow_paid",
    }

    def _group_providers(self) -> Dict[str, Dict]:
        """将 deployments 按逻辑 provider 分组，返回 {display_name: {keys: {raw_provider: src}}}"""
        groups: Dict[str, Dict[str, FreeAPISource]] = {}
        seen_providers: set = set()

        for _family, sources in self._sources.items():
            for src in sources:
                if src.provider in seen_providers:
                    continue
                seen_providers.add(src.provider)

                display = src.provider
                for prefix, group_name in self._MULTI_KEY_PREFIXES.items():
                    if src.provider.startswith(prefix):
                        display = group_name
                        break

                groups.setdefault(display, {})[src.provider] = src

        return groups

    async def _test_single_key(self, src: FreeAPISource, timeout: float = 10.0) -> Dict:
        """测试单个 key — 返回 {status, error?}"""
        import asyncio
        import re

        # 使用 litellm 直接调用 (绕过 Router fallback)
        model_id = src._deployment_id.split("/", 1)[-1] if "/" in src._deployment_id else src.model
        # 为 litellm 构建正确的 model 格式
        params: Dict[str, Any] = {
            "model": f"openai/{model_id}" if src.base_url else model_id,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
            "temperature": 0,
            "api_key": src.api_key,
        }
        if src.base_url:
            params["api_base"] = src.base_url

        try:
            await asyncio.wait_for(
                litellm.acompletion(**params),
                timeout=timeout,
            )
            return {"status": "ok"}
        except asyncio.TimeoutError as e:  # noqa: F841
            return {"status": "unreachable", "error": f"Timeout ({timeout}s)"}
        except Exception as e:
            err_str = _scrub_secrets(str(e))
            # 提取 HTTP 状态码
            status_code = None
            code_match = re.search(r"Status(?:Code)?[:\s]*(\d{3})", err_str, re.IGNORECASE)
            if code_match:
                status_code = int(code_match.group(1))
            elif hasattr(e, "status_code"):
                status_code = e.status_code

            if status_code in (401, 403):
                return {"status": "auth_error", "error": f"{status_code} {err_str[:120]}"}
            elif status_code == 429:
                return {"status": "quota_exhausted", "error": f"429 {err_str[:120]}"}
            elif status_code is not None and status_code >= 500:
                return {"status": "unreachable", "error": f"{status_code} {err_str[:120]}"}
            elif "connect" in err_str.lower() or "unreachable" in err_str.lower():
                return {"status": "unreachable", "error": err_str[:120]}
            else:
                return {"status": "unknown_error", "error": err_str[:200]}

    async def validate_keys(self, timeout: float = 10.0) -> Dict:
        """验证所有 API Key 健康状态 — 按 provider 分组、逐 key 测试。

        Returns:
            {
                "timestamp": "...",
                "total_providers": N,
                "healthy": N,
                "unhealthy": N,
                "providers": {
                    "siliconflow_free": {"status": "ok", "keys_tested": 4, ...},
                    ...
                },
                "elapsed_s": float,
            }
        """
        import asyncio
        from datetime import datetime, timezone

        start = time.time()
        groups = self._group_providers()

        async def _test_group(display: str, key_map: Dict[str, FreeAPISource]) -> tuple:
            """测试一个 provider 组, 返回 (display, result_dict)"""
            if len(key_map) == 1:
                # 单 key provider — 测一次
                raw_prov, src = next(iter(key_map.items()))
                result = await self._test_single_key(src, timeout)
                if result["status"] == "auth_error":
                    src.disabled = True
                    logger.warning("[validate_keys] 禁用 auth_error key: %s/%s", src.provider, src.model)
                return (
                    display,
                    {
                        "status": result["status"],
                        **({} if result["status"] == "ok" else {"error": result.get("error", "")}),
                    },
                )
            else:
                # 多 key provider — 逐 key 测
                keys_tested = 0
                keys_ok = 0
                dead_indices: List[int] = []
                errors: List[str] = []

                # 按 provider 名排序以保持稳定索引
                sorted_items = sorted(key_map.items(), key=lambda x: x[0])

                tasks = []
                for _raw_prov, src in sorted_items:
                    tasks.append(self._test_single_key(src, timeout))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                for idx, res in enumerate(results):
                    keys_tested += 1
                    _raw_prov, src_ref = sorted_items[idx]
                    if isinstance(res, Exception):
                        dead_indices.append(idx)
                        errors.append(str(res)[:80])
                        src_ref.disabled = True
                    elif res["status"] == "ok":
                        keys_ok += 1
                    else:
                        dead_indices.append(idx)
                        errors.append(res.get("error", res["status"]))
                        if res["status"] == "auth_error":
                            src_ref.disabled = True
                            logger.warning(
                                "[validate_keys] 禁用 auth_error key: %s/%s", src_ref.provider, src_ref.model
                            )

                overall = "ok" if keys_ok == keys_tested else ("auth_error" if keys_ok == 0 else "partial")

                info: Dict[str, Any] = {
                    "status": overall,
                    "keys_tested": keys_tested,
                    "keys_ok": keys_ok,
                    "keys_dead": len(dead_indices),
                }
                if dead_indices:
                    info["dead_indices"] = dead_indices
                if errors:
                    info["errors"] = errors[:5]  # 最多 5 条
                return (display, info)

        # 并行测试所有 provider 组
        group_tasks = [_test_group(d, km) for d, km in groups.items()]
        group_results = await asyncio.gather(*group_tasks, return_exceptions=True)

        providers_report: Dict[str, Dict] = {}
        healthy_count = 0
        unhealthy_count = 0

        for res in group_results:
            if isinstance(res, Exception):
                continue
            display, info = res
            providers_report[display] = info
            if info["status"] == "ok":
                healthy_count += 1
            elif info["status"] == "partial":
                healthy_count += 1  # 部分可用也算健康
            else:
                unhealthy_count += 1

        elapsed = time.time() - start
        report = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "total_providers": len(providers_report),
            "healthy": healthy_count,
            "unhealthy": unhealthy_count,
            "providers": providers_report,
            "elapsed_s": round(elapsed, 2),
        }

        logger.info(
            f"[Key验证] {healthy_count}/{len(providers_report)} providers 健康, "
            f"{unhealthy_count} 异常, 耗时 {elapsed:.1f}s"
        )
        return report


# ============================================================
# 全局单例 + 初始化
# ============================================================

free_pool = LiteLLMPool()


def init_free_pool():
    free_pool.initialize()
    stats = free_pool.get_stats()
    logger.info(f"[LiteLLMPool] {stats['total_sources']} sources, {stats['active_sources']} active, engine=litellm")


# REMOVED: init_adaptive_router() - 已废弃，LiteLLM Router 内置自适应路由，无需单独初始化

adaptive_router = None  # 兼容旧 import
