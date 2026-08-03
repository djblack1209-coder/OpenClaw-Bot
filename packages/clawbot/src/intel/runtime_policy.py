"""Intel Brief 运行时路由与社媒登录策略。

本模块只描述调度/执行倾向，不直接创建服务器、不保存 Cookie、也不触发登录。
用于把“国内业务优先国内节点，海外流量走海外节点”的产品决策沉淀为可测试策略。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE = "Asia/Singapore"
DEFAULT_INTEL_BRIEF_DELIVERY_TIME = "08:30"
DEFAULT_INTEL_BRIEF_WINDOW_START = (8, 30)
DEFAULT_INTEL_BRIEF_WINDOW_END = (10, 0)


class IntelBriefRuntimePolicyError(ValueError):
    """每日资讯运行策略配置错误，并携带可审计的稳定错误码。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RuntimePolicy:
    """单个数据源的运行节点偏好。"""

    source_name: str
    preferred_worker: str
    region_hint: str
    requires_overseas_egress: bool
    reason: str


@dataclass(frozen=True)
class SocialAuthStrategy:
    """社媒平台的无人值守优先登录策略。"""

    platform: str
    preferred_login_modes: list[str]
    unattended_first: bool
    qrcode_mode: str
    note: str


@dataclass(frozen=True)
class IntelBriefDeliveryWindowDecision:
    """每日资讯在指定业务时区内的投递窗口判定。"""

    scheduler_timezone: str
    local_now: datetime
    window_start: tuple[int, int]
    window_end: tuple[int, int]
    should_run: bool
    reason: str


_DOMESTIC_SOURCES = {
    "weibo",
    "xiaohongshu",
    "xhs",
    "rednote",
    "douyin",
    "zhihu",
    "bilibili",
    "baidu",
    "akshare",
    "astock_flow",
    "a_stock_flow",
    "eastmoney",
    "cn_stock_flow",
}

_OVERSEAS_SOURCES = {
    "sec_edgar",
    "edgar",
    "edgar_13f",
    "institutional_13f",
    "github",
    "github_trending",
    "ai_model_updates",
    "openai_rss",
    "anthropic_news",
    "anthropic_rss",
    "deepseek_news",
    "senate_trading",
    "senate-stock-watcher-data",
    "congress_trading",
    "housestockwatcher",
    "weather",
    "weather_monitor",
    "nws_weather",
}

_SOCIAL_AUTH_STRATEGIES = {
    "xiaohongshu": SocialAuthStrategy(
        platform="xiaohongshu",
        preferred_login_modes=["cdp_cookie", "cookie", "phone", "qrcode"],
        unattended_first=True,
        qrcode_mode="fallback_only",
        note="优先复用持久浏览器态或 Cookie；二维码只作为风控失效后的人工兜底。",
    ),
    "xhs": SocialAuthStrategy(
        platform="xiaohongshu",
        preferred_login_modes=["cdp_cookie", "cookie", "phone", "qrcode"],
        unattended_first=True,
        qrcode_mode="fallback_only",
        note="优先复用持久浏览器态或 Cookie；二维码只作为风控失效后的人工兜底。",
    ),
    "weibo": SocialAuthStrategy(
        platform="weibo",
        preferred_login_modes=["cdp_cookie", "cookie", "public_web", "phone", "qrcode"],
        unattended_first=True,
        qrcode_mode="fallback_only",
        note="优先公开页/持久登录态无人值守运行；二维码只作为风控失效后的人工兜底。",
    ),
}


def _normalize_source_name(source_name: str) -> str:
    """统一数据源名称，便于配置和代码里复用。"""
    return str(source_name or "").strip().lower().replace("-", "_")


def _validate_hhmm(value: tuple[int, int], *, field_name: str) -> tuple[int, int]:
    """校验小时和分钟，避免错误配置绕过投递窗口。"""
    try:
        hour, minute = int(value[0]), int(value[1])
    except (IndexError, TypeError, ValueError) as exc:
        raise IntelBriefRuntimePolicyError(
            "invalid_scheduler_window",
            f"{field_name} must be a valid HH:MM value",
        ) from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise IntelBriefRuntimePolicyError(
            "invalid_scheduler_window",
            f"{field_name} must be a valid HH:MM value",
        )
    return hour, minute


def evaluate_intel_brief_delivery_window(
    *,
    now: datetime,
    scheduler_timezone: str = DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE,
    window_start: tuple[int, int] = DEFAULT_INTEL_BRIEF_WINDOW_START,
    window_end: tuple[int, int] = DEFAULT_INTEL_BRIEF_WINDOW_END,
) -> IntelBriefDeliveryWindowDecision:
    """把当前时刻换算到业务时区，并判断是否位于允许投递的分钟窗口。"""
    timezone_name = str(scheduler_timezone or DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE).strip()
    try:
        scheduler_zone = ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise IntelBriefRuntimePolicyError(
            "invalid_scheduler_timezone",
            "scheduler_timezone must be a valid IANA timezone",
        ) from exc

    start = _validate_hhmm(window_start, field_name="window_start")
    end = _validate_hhmm(window_end, field_name="window_end")
    start_minute = start[0] * 60 + start[1]
    end_minute = end[0] * 60 + end[1]
    if end_minute < start_minute:
        raise IntelBriefRuntimePolicyError(
            "invalid_scheduler_window",
            "window_end must not be earlier than window_start",
        )

    # 无时区输入按配置的业务墙钟解释；有时区输入按同一绝对时刻换算。
    local_now = now.replace(tzinfo=scheduler_zone) if now.tzinfo is None else now.astimezone(scheduler_zone)
    current_minute = local_now.hour * 60 + local_now.minute
    if current_minute < start_minute:
        reason = "skipped_before_window"
        should_run = False
    elif current_minute > end_minute:
        reason = "skipped_late_trigger"
        should_run = False
    else:
        reason = "inside_delivery_window"
        should_run = True

    return IntelBriefDeliveryWindowDecision(
        scheduler_timezone=timezone_name,
        local_now=local_now,
        window_start=start,
        window_end=end,
        should_run=should_run,
        reason=reason,
    )


def resolve_runtime_policy(source_name: str) -> RuntimePolicy:
    """返回数据源的推荐运行节点策略。

    国内源（微博、小红书、A股等）默认放国内 worker，减少绕路和跨境出口依赖；
    需要访问 GitHub/SEC/海外官网的源默认放海外 worker。
    """
    normalized = _normalize_source_name(source_name)
    if normalized in _DOMESTIC_SOURCES:
        return RuntimePolicy(
            source_name=normalized,
            preferred_worker="domestic",
            region_hint="cn",
            requires_overseas_egress=False,
            reason="domestic_source",
        )
    if normalized in _OVERSEAS_SOURCES:
        return RuntimePolicy(
            source_name=normalized,
            preferred_worker="overseas",
            region_hint="global",
            requires_overseas_egress=True,
            reason="overseas_source",
        )
    return RuntimePolicy(
        source_name=normalized,
        preferred_worker="controller",
        region_hint="auto",
        requires_overseas_egress=False,
        reason="unknown_source",
    )


def should_use_domestic_worker(source_name: str) -> bool:
    """判断某个数据源是否应优先派发到国内 worker。"""
    return resolve_runtime_policy(source_name).preferred_worker == "domestic"


def get_social_auth_strategy(platform: str) -> SocialAuthStrategy:
    """返回社媒平台登录策略；未知平台默认仍采用无人值守优先、扫码兜底。"""
    normalized = _normalize_source_name(platform)
    strategy = _SOCIAL_AUTH_STRATEGIES.get(normalized)
    if strategy is not None:
        return strategy
    return SocialAuthStrategy(
        platform=normalized,
        preferred_login_modes=["cdp_cookie", "cookie", "public_web", "qrcode"],
        unattended_first=True,
        qrcode_mode="fallback_only",
        note="未知平台按保守策略处理：优先持久登录态，二维码仅兜底。",
    )
