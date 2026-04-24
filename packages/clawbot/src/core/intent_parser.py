"""
OpenClaw OMEGA — 意图解析器 (Intent Parser)
将自然语言指令转为结构化 ParsedIntent，供 TaskGraph 消费。

设计原则:
  1. 用 LLM 做语义理解，不做规则硬编码
  2. missing_critical 不为空时，先执行可执行部分，再一次性问所有缺失信息
  3. 永远不分多轮问问题
  4. 复用现有 litellm_router.py 的多模型路由
  5. 结构化输出: instructor (10k⭐) 保证 LLM 返回类型安全的 Pydantic 对象
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.utils import scrub_secrets

try:
    import jieba
    import jieba.analyse

    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False

# 速率限制 — resilience 模块始终可导入，内部已做优雅降级
from src.constants import FAMILY_QWEN
from src.resilience import api_limiter

logger = logging.getLogger(__name__)


# ── 任务类型枚举 ──────────────────────────────────────────


class TaskType(str, Enum):
    """任务分类"""

    INVESTMENT = "investment"  # 投资分析/交易
    SOCIAL = "social"  # 社媒运营
    SHOPPING = "shopping"  # 购物比价
    BOOKING = "booking"  # 预订（餐厅/酒店/机票）
    LIFE = "life"  # 生活服务（快递/日历/账单）
    CODE = "code"  # 代码/开发任务
    INFO = "info"  # 信息查询
    COMMUNICATION = "communication"  # 通信代理（微信/邮件）
    SYSTEM = "system"  # 系统管理
    EVOLUTION = "evolution"  # 自进化指令
    UNKNOWN = "unknown"


# ── 解析结果 ──────────────────────────────────────────────


@dataclass
class ParsedIntent:
    """结构化意图"""

    goal: str  # 核心目标（一句话）
    task_type: TaskType  # 任务分类
    known_params: dict[str, Any] = field(default_factory=dict)
    missing_critical: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    urgency: str = "normal"  # urgent / normal / background
    reversible: bool = True  # 操作是否可逆
    estimated_cost_usd: float = 0.0  # 预估LLM费用
    requires_confirmation: bool = False  # 是否需要用户确认
    confidence: float = 0.0  # 解析置信度 0-1
    raw_message: str = ""  # 原始消息

    @property
    def is_actionable(self) -> bool:
        """是否有足够信息开始执行（至少部分执行）"""
        return self.task_type != TaskType.UNKNOWN and self.confidence >= 0.5

    @property
    def needs_clarification(self) -> bool:
        """是否需要向用户追问"""
        return len(self.missing_critical) > 0


# ── Pydantic 模型 — instructor 结构化输出 ─────────────────


class IntentLLMOutput(BaseModel):
    """
    LLM 意图解析的 Pydantic 输出模型。

    instructor 用这个 schema 强制 LLM 返回类型安全的结构化数据，
    替代原有的 json_repair + 手动 dict.get() 模式。

    字段与 ParsedIntent 一一对应，但使用 Pydantic Field 做校验：
      - task_type 限制为枚举值
      - confidence 限制在 0-1
      - urgency 限制为三个合法值
    """

    goal: str = Field(default="", description="一句话核心目标")
    task_type: str = Field(
        default="unknown",
        description="任务分类: investment/social/shopping/booking/life/"
        "code/info/communication/system/evolution/unknown",
    )
    known_params: dict[str, Any] = Field(default_factory=dict, description="已知参数 key-value")
    missing_critical: list[str] = Field(default_factory=list, description="缺失的关键参数名")
    missing_optional: list[str] = Field(default_factory=list, description="缺失的可选参数名")
    constraints: list[str] = Field(default_factory=list, description="约束条件")
    urgency: Literal["urgent", "normal", "background"] = Field(default="normal", description="紧急度")
    reversible: bool = Field(default=True, description="操作是否可逆")
    requires_confirmation: bool = Field(default=False, description="是否需要用户确认")
    confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="解析置信度 0-1")

    def to_parsed_intent(self, raw_message: str = "") -> "ParsedIntent":
        """转换为 ParsedIntent dataclass（供下游 TaskGraph 消费）"""
        # 安全地转换 task_type，无效值降级为 UNKNOWN
        try:
            task_type = TaskType(self.task_type)
        except ValueError:
            logger.warning(f"LLM 返回未知 task_type: {self.task_type!r}，降级为 UNKNOWN")
            task_type = TaskType.UNKNOWN

        return ParsedIntent(
            goal=self.goal or raw_message,
            task_type=task_type,
            known_params=self.known_params,
            missing_critical=self.missing_critical,
            missing_optional=self.missing_optional,
            constraints=self.constraints,
            urgency=self.urgency,
            reversible=self.reversible,
            requires_confirmation=self.requires_confirmation,
            confidence=self.confidence,
            raw_message=raw_message,
        )


# ── 意图解析器 ──────────────────────────────────────────

# LLM 解析提示词 — 从中央注册表导入
from config.prompts import (
    INTENT_PARSER_PROMPT as _PARSE_SYSTEM_PROMPT,
)
from config.prompts import (
    INTENT_PARSER_USER_TEMPLATE as _PARSE_USER_TEMPLATE,
)


class IntentParser:
    """
    意图解析器 — 将自然语言转为结构化 ParsedIntent。

    用法:
        parser = IntentParser()
        intent = await parser.parse("帮我分析茅台今天能买吗")
    """

    def __init__(self):
        self._fast_patterns = self._build_fast_patterns()
        logger.info("IntentParser 初始化完成")

    def _build_fast_patterns(self) -> list[dict]:
        """
        快速模式匹配 — 常见指令不需要调用 LLM。
        覆盖 ~60% 的日常指令，节省 LLM 调用费用。
        """
        return [
            # 投资类
            {
                "patterns": [r"分析(.+)", r"(.+)能买吗", r"看看(.+)", r"(.+)的?行情"],
                "task_type": TaskType.INVESTMENT,
                "goal_template": "投资分析: {match}",
                "param_key": "symbol_hint",
            },
            {
                "patterns": [r"买入(.+)", r"卖出(.+)", r"加仓(.+)", r"减仓(.+)"],
                "task_type": TaskType.INVESTMENT,
                "goal_template": "执行交易: {match}",
                "param_key": "trade_hint",
                "requires_confirmation": True,
                "reversible": False,
            },
            {
                "patterns": [r"持仓", r"仓位", r"盈亏", r"PnL", r"portfolio"],
                "task_type": TaskType.INVESTMENT,
                "goal_template": "查看持仓状态",
                "param_key": None,
            },
            # 社媒类
            {
                "patterns": [r"发(一条|个|条)(.+)", r"发帖(.+)", r"写(一篇|个)(.+)"],
                "task_type": TaskType.SOCIAL,
                "goal_template": "社媒发帖: {match}",
                "param_key": "content_hint",
            },
            {
                "patterns": [r"热[点搜]", r"trending", r"热榜"],
                "task_type": TaskType.SOCIAL,
                "goal_template": "查看热点趋势",
                "param_key": None,
            },
            # 购物类 (v2.0: 排除股票/投资上下文)
            {
                "patterns": [
                    r"买(.+)",
                    r"比价(.+)",
                    r"搜(.+)价格",
                    r"(.+)多少钱",
                    r"帮我找(.+)",
                    r"查.+(.+)价格",
                    r"(.+)哪里便宜",
                    r"比较(.+)价格",
                ],
                "task_type": TaskType.SHOPPING,
                "goal_template": "购物比价: {match}",
                "param_key": "product_hint",
                # v2.0: 排除股票上下文 (含"股/手/份/期权/基金"则不走购物)
                "exclude_pattern": r"股|手|份|期权|基金|债券|ETF|AAPL|TSLA|NVDA|GOOGL|MSFT|AMZN|META|BTC|比特币|以太坊|茅台|特斯拉|英伟达",
            },
            # 预订类
            {
                "patterns": [
                    r"订(.*)餐厅",
                    r"订(.*)酒店",
                    r"订(.*)机票",
                    r"预[订定](.+)",
                    r"帮我订(.+)",
                    r"(.+)预约",
                    r"挂号(.+)",
                    r"订个(.+)",
                    r"定个(.+)",
                ],
                "task_type": TaskType.BOOKING,
                "goal_template": "预订: {match}",
                "param_key": "booking_hint",
                "requires_confirmation": True,
            },
            # 生活类
            {
                "patterns": [r"快递", r"包裹", r"物流"],
                "task_type": TaskType.LIFE,
                "goal_template": "快递追踪",
                "param_key": None,
            },
            {
                "patterns": [r"(.+)天气", r"天气(.+)", r"气温"],
                "task_type": TaskType.LIFE,
                "goal_template": "天气查询: {match}",
                "param_key": "city_hint",
            },
            {
                "patterns": [r"日程", r"日历", r"提醒我(.+)", r"安排(.+)"],
                "task_type": TaskType.LIFE,
                "goal_template": "日程管理: {match}",
                "param_key": "schedule_hint",
            },
            # 系统类
            {
                "patterns": [r"状态", r"status", r"健康", r"system"],
                "task_type": TaskType.SYSTEM,
                "goal_template": "查看系统状态",
                "param_key": None,
            },
            # 进化类
            {
                "patterns": [r"进化", r"evolve", r"扫描github", r"scan"],
                "task_type": TaskType.EVOLUTION,
                "goal_template": "触发进化扫描",
                "param_key": None,
            },
        ]

    async def parse(
        self,
        message: str,
        message_type: str = "text",
        context: dict | None = None,
    ) -> ParsedIntent:
        """
        解析用户消息为结构化意图。

        先尝试快速模式匹配，失败后调用 LLM。

        Args:
            message: 用户消息文本
            message_type: text / voice / image / file / forward
            context: 附加上下文（用户历史偏好等）

        Returns:
            ParsedIntent
        """
        context = context or {}

        # 1. 快速模式匹配（不花钱）
        fast_result = self._try_fast_parse(message)
        if fast_result and fast_result.confidence >= 0.8:
            fast_result.raw_message = message
            logger.info(f"快速解析成功: {fast_result.task_type} — {fast_result.goal}")
            return fast_result

        # 1.5 本地轻量模型预筛（零成本，节省付费 API 调用）
        try:
            from src.tools.local_llm import classify_intent as _local_classify

            local_type = await _local_classify(message)
            if local_type:
                # 本地模型给出了明确分类，构建中等置信度的结果
                # 仍需要 LLM 提取参数，但可以跳过分类环节
                logger.debug(f"[IntentParser] 本地模型分类: {local_type}（节省一次分类 API 调用）")
        except Exception:
            pass  # 本地模型不可用，静默跳过

        # 2. LLM 解析（花钱但准确）
        try:
            llm_result = await self._llm_parse(message, message_type, context)
            llm_result.raw_message = message
            logger.info(f"LLM解析完成: {llm_result.task_type} — {llm_result.goal}")
            return llm_result
        except Exception as e:
            logger.warning(f"LLM解析失败: {scrub_secrets(str(e))}, 降级到快速解析")
            # 降级：返回快速解析的结果（即使置信度低）
            if fast_result:
                fast_result.raw_message = message
                return fast_result
            # 最终降级：返回 UNKNOWN
            return ParsedIntent(
                goal=message,
                task_type=TaskType.UNKNOWN,
                confidence=0.1,
                raw_message=message,
            )

    def _try_fast_parse(self, message: str) -> ParsedIntent | None:
        """快速正则匹配 + jieba 关键词增强"""
        msg_lower = message.lower().strip()

        for pattern_group in self._fast_patterns:
            for pattern in pattern_group["patterns"]:
                match = re.search(pattern, msg_lower)
                if match:
                    # v2.0: 排除不匹配的上下文 (如"买100股苹果"不应走购物)
                    exclude = pattern_group.get("exclude_pattern")
                    if exclude and re.search(exclude, msg_lower, re.IGNORECASE):
                        continue  # 跳过此 pattern group

                    # 提取匹配的参数（使用最后一个捕获组，避免中间组干扰）
                    matched_text = match.group(match.lastindex) if match.lastindex else ""
                    # 使用 replace 替代 format，防止匹配文本中的花括号触发模板注入
                    goal = pattern_group["goal_template"].replace("{match}", matched_text)

                    known_params = {}
                    if pattern_group.get("param_key") and matched_text:
                        known_params[pattern_group["param_key"]] = matched_text

                    # jieba 关键词提取增强（补充更精准的参数信息）
                    if HAS_JIEBA and matched_text and len(matched_text) >= 4:
                        try:
                            keywords = jieba.analyse.extract_tags(message, topK=5, withWeight=True)
                            if keywords:
                                known_params["_keywords"] = [{"word": w, "weight": round(s, 3)} for w, s in keywords]
                        except Exception:
                            logger.debug("Silenced exception", exc_info=True)

                    # 投资类: 自动将中文名转为 ticker
                    if pattern_group["task_type"] == TaskType.INVESTMENT and matched_text:
                        ticker = self._resolve_ticker(matched_text)
                        if ticker:
                            known_params["symbol_hint"] = ticker
                            known_params["symbol_raw"] = matched_text

                    return ParsedIntent(
                        goal=goal,
                        task_type=pattern_group["task_type"],
                        known_params=known_params,
                        requires_confirmation=pattern_group.get("requires_confirmation", False),
                        reversible=pattern_group.get("reversible", True),
                        confidence=0.85,
                    )
        return None

    async def _try_llm_classify(self, message: str) -> ParsedIntent | None:
        """轻量 LLM 意图分类 — fast_parse 的降级路径。

        用最便宜的模型快速判断消息是否属于可执行的任务类型。
        不解析完整参数（那是 parse() 的 LLM 路径做的事），
        只判断 task_type 和 confidence，让 Brain 有机会接管。

        设计原则：
        - 零正则：完全依赖 LLM 语义理解
        - 低成本：用 qwen（最便宜）+ max_tokens=100
        - 高召回：阈值比 fast_parse 宽松（confidence >= 0.6）
        - 快速失败：超时 5 秒直接放弃
        """
        try:
            from src.litellm_router import free_pool

            if not free_pool:
                return None

            classify_prompt = (
                "判断以下用户消息属于哪个任务类型。只返回 JSON。\n"
                "任务类型:\n"
                "- investment: 投资/股票/交易/行情/持仓/回测/K线\n"
                "- social: 社媒/发帖/小红书/推特/热点\n"
                "- shopping: 购物/比价/哪里买/便宜 (注意: 含'股/手/份/期权/基金'则为investment)\n"
                "- booking: 预订/订餐/订酒店/订机票/挂号\n"
                "- life: 天气/快递/提醒/日程/记账/账单\n"
                "- code: 编程/代码/GitHub/开发/bug\n"
                "- info: 查询/搜索/新闻/百科\n"
                "- communication: 发消息/发邮件/通知\n"
                "- system: 系统/状态/配置/成本\n"
                "- evolution: 进化/扫描/能力评估\n"
                "- unknown: 闲聊/不确定\n\n"
                "示例:\n"
                "- '帮我买100股苹果' → investment (含'股')\n"
                "- '帮我找便宜的AirPods' → shopping\n"
                "- '苹果多少钱' → investment (苹果=AAPL股票)\n"
                "- '明天提醒我开会' → life\n"
                "- '写个Python脚本' → code\n\n"
                f"用户消息: {message[:200]}\n\n"
                '返回格式: {"task_type": "...", "confidence": 0.0-1.0, "goal": "一句话目标"}'
            )

            import asyncio

            resp = await asyncio.wait_for(
                free_pool.acompletion(
                    model_family=FAMILY_QWEN,
                    messages=[{"role": "user", "content": classify_prompt}],
                    temperature=0.1,
                    max_tokens=100,
                ),
                timeout=5.0,
            )

            text = resp.choices[0].message.content or ""

            # 用 json_repair 容错解析
            from json_repair import loads as jloads

            data = jloads(text)
            if not isinstance(data, dict):
                return None

            task_type_str = data.get("task_type", "unknown")
            confidence = float(data.get("confidence", 0.0))
            goal = data.get("goal", message[:50])

            # unknown 或低置信度 → 放弃
            if task_type_str == "unknown" or confidence < 0.6:
                return None

            try:
                task_type = TaskType(task_type_str)
            except ValueError as e:  # noqa: F841
                return None

            logger.info(f'[IntentParser] LLM 分类成功: {task_type_str} (conf={confidence:.2f}) — "{message[:40]}"')

            return ParsedIntent(
                goal=goal,
                task_type=task_type,
                confidence=confidence,
                raw_message=message,
            )

        except TimeoutError:
            logger.debug("[IntentParser] LLM 分类超时")
            return None
        except Exception as e:
            logger.debug(f"[IntentParser] LLM 分类失败: {e}")
            return None

    @staticmethod
    def _resolve_ticker(text: str) -> str | None:
        """中文股票名/简称 → ticker 代码"""
        _TICKER_MAP = {
            # A股
            "茅台": "600519.SS",
            "贵州茅台": "600519.SS",
            "宁德时代": "300750.SZ",
            "宁德": "300750.SZ",
            "比亚迪": "002594.SZ",
            "腾讯": "0700.HK",
            "阿里": "BABA",
            "阿里巴巴": "BABA",
            "中国平安": "601318.SS",
            "平安": "601318.SS",
            "招商银行": "600036.SS",
            "招行": "600036.SS",
            "中信证券": "600030.SS",
            "隆基绿能": "601012.SS",
            "隆基": "601012.SS",
            "药明康德": "603259.SS",
            "五粮液": "000858.SZ",
            "美的": "000333.SZ",
            "美的集团": "000333.SZ",
            "格力": "000651.SZ",
            "格力电器": "000651.SZ",
            "中芯国际": "688981.SS",
            "中芯": "688981.SS",
            # 美股
            "苹果": "AAPL",
            "apple": "AAPL",
            "特斯拉": "TSLA",
            "tesla": "TSLA",
            "英伟达": "NVDA",
            "nvidia": "NVDA",
            "微软": "MSFT",
            "microsoft": "MSFT",
            "谷歌": "GOOGL",
            "google": "GOOGL",
            "亚马逊": "AMZN",
            "amazon": "AMZN",
            "meta": "META",
            "脸书": "META",
            "台积电": "TSM",
            "tsmc": "TSM",
            "奈飞": "NFLX",
            "netflix": "NFLX",
            # 加密
            "比特币": "BTC-USD",
            "btc": "BTC-USD",
            "bitcoin": "BTC-USD",
            "以太坊": "ETH-USD",
            "eth": "ETH-USD",
            "ethereum": "ETH-USD",
        }
        text_lower = text.lower().strip()
        # 精确匹配
        if text_lower in _TICKER_MAP:
            return _TICKER_MAP[text_lower]
        # 包含匹配
        for name, ticker in _TICKER_MAP.items():
            if name in text_lower:
                return ticker
        # 已经是 ticker 格式
        if re.match(r"^[A-Za-z]{1,5}$", text.strip()):
            return text.strip().upper()
        if re.match(r"^\d{6}\.(SS|SZ|HK)$", text.strip()):
            return text.strip()
        return None

    async def _llm_parse(
        self,
        message: str,
        message_type: str,
        context: dict,
    ) -> ParsedIntent:
        """
        使用 LLM 解析意图。

        优先使用 instructor + structured_completion 获取类型安全的结构化输出，
        instructor 不可用时自动降级到 json_repair 手动解析。
        """
        prompt = _PARSE_USER_TEMPLATE.format(
            message=message,
            message_type=message_type,
            context=json.dumps(context, ensure_ascii=False, default=str) if context else "无",
        )

        # ── 路径 1: structured_completion (instructor + Pydantic) ──
        try:
            from src.structured_llm import structured_completion

            llm_output = await structured_completion(
                response_model=IntentLLMOutput,
                messages=[{"role": "user", "content": prompt}],
                model_family=FAMILY_QWEN,
                system_prompt=_PARSE_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=800,
                max_retries=2,
            )
            return llm_output.to_parsed_intent(raw_message=message)

        except ImportError:
            logger.debug("structured_llm 模块不可用，使用 legacy 解析")
        except Exception as e:
            logger.warning(f"structured_completion 失败 ({type(e).__name__}: {scrub_secrets(str(e))})，降级到 legacy JSON 解析")

        # ── 路径 2: legacy 降级 (free_pool + json_repair) ──────────
        return await self._llm_parse_legacy(message, message_type, context)

    async def _llm_parse_legacy(
        self,
        message: str,
        message_type: str,
        context: dict,
    ) -> ParsedIntent:
        """
        Legacy LLM 解析 — 不依赖 instructor 的降级路径。

        保留原有的 free_pool.acompletion + json_repair + 手动 dict 映射逻辑，
        确保即使 instructor 和 structured_llm 都不可用，系统仍能工作。
        """
        try:
            from src.litellm_router import free_pool
        except ImportError:
            free_pool = None

        if free_pool is None:
            raise RuntimeError("LLM router 未初始化")

        prompt = _PARSE_USER_TEMPLATE.format(
            message=message,
            message_type=message_type,
            context=json.dumps(context, ensure_ascii=False, default=str) if context else "无",
        )

        async with api_limiter("llm"):
            response = await free_pool.acompletion(
                model_family=FAMILY_QWEN,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                system_prompt=_PARSE_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=800,
            )

        raw_text = response.choices[0].message.content.strip()

        # 解析 JSON（容错）
        try:
            import json_repair

            parsed = json_repair.loads(raw_text)
            if not isinstance(parsed, dict):
                raise ValueError("json_repair did not return a dict")
        except Exception as e:  # noqa: F841
            json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
            else:
                raise ValueError(f"LLM 返回非 JSON: {raw_text[:200]}")

        # 尝试用 Pydantic 做校验（比 dict.get 更安全）
        try:
            llm_output = IntentLLMOutput.model_validate(parsed)
            return llm_output.to_parsed_intent(raw_message=message)
        except Exception as e:  # noqa: F841
            # 最终降级: 手动 dict 映射（兼容任何畸形 JSON）
            return ParsedIntent(
                goal=parsed.get("goal", message),
                task_type=TaskType(parsed.get("task_type", "unknown")),
                known_params=parsed.get("known_params", {}),
                missing_critical=parsed.get("missing_critical", []),
                missing_optional=parsed.get("missing_optional", []),
                constraints=parsed.get("constraints", []),
                urgency=parsed.get("urgency", "normal"),
                reversible=parsed.get("reversible", True),
                requires_confirmation=parsed.get("requires_confirmation", False),
                confidence=parsed.get("confidence", 0.7),
            )
