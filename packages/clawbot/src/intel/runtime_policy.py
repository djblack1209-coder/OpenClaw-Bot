"""Intel Brief 运行时路由与社媒登录策略。

本模块只描述调度/执行倾向，不直接创建服务器、不保存 Cookie、也不触发登录。
用于把“国内业务优先国内节点，海外流量走海外节点”的产品决策沉淀为可测试策略。
"""

from __future__ import annotations

from dataclasses import dataclass


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
