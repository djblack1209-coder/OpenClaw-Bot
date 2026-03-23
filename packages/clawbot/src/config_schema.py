"""
OpenClaw 类型安全配置管理 — 搬运 pydantic-settings (3.3k⭐)

替代分散在各模块中的 os.getenv() 调用，提供：
  - 类型验证 (int/float/bool 不再需要手动转换)
  - 默认值 + 文档 (Field description)
  - .env 文件自动加载
  - 嵌套配置 (交易/社媒/AI 分组)
  - 运行时配置查看 (不暴露敏感值)

搬运自: pydantic-settings (3.3k⭐), Dify/AutoGPT 配置管理最佳实践

用法:
    from src.config_schema import settings
    print(settings.trading.daily_budget)      # 2000.0
    print(settings.ai.litellm_log_level)      # "WARNING"
    print(settings.telegram.admin_user_ids)   # [123456789]
    print(settings.to_safe_dict())            # 不含密钥的配置快照
"""
import logging
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── pydantic-settings 可选 ──────────────────────────────────
_HAS_PYDANTIC_SETTINGS = False
try:
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _HAS_PYDANTIC_SETTINGS = True
    logger.debug("[config_schema] pydantic-settings 已加载")
except ImportError:
    logger.info("[config_schema] pydantic-settings 未安装 (pip install pydantic-settings)")

_ENV_FILE = Path(__file__).resolve().parent.parent / "config" / ".env"


if _HAS_PYDANTIC_SETTINGS:

    class TradingConfig(BaseSettings):
        """交易系统配置"""
        model_config = SettingsConfigDict(env_prefix="TRADING_")

        daily_budget: float = Field(default=2000.0, description="每日交易预算 (USD)")
        max_position_pct: float = Field(default=2.0, description="单笔最大仓位 (%)")
        max_daily_loss: float = Field(default=100.0, description="日亏损限制 (USD)")
        auto_trade: bool = Field(default=False, description="自动交易开关")
        scan_interval_min: int = Field(default=15, description="市场扫描间隔 (分钟)")

    class AIConfig(BaseSettings):
        """AI/LLM 配置"""
        model_config = SettingsConfigDict(env_prefix="AI_")

        daily_cost_limit: float = Field(default=50.0, description="每日 LLM 成本限制 (USD)")
        default_model: str = Field(default="qwen", description="默认模型族")
        litellm_log_level: str = Field(default="WARNING", description="LiteLLM 日志级别")
        cache_ttl: int = Field(default=3600, description="LLM 缓存 TTL (秒)")

    class TelegramConfig(BaseSettings):
        """Telegram Bot 配置"""
        model_config = SettingsConfigDict(env_prefix="TG_")

        admin_user_ids: str = Field(default="", description="管理员 user_id (逗号分隔)")
        rate_limit_per_min: int = Field(default=20, description="每分钟消息限制")
        streaming_edit_interval: float = Field(default=1.0, description="流式编辑间隔 (秒)")

    class SocialConfig(BaseSettings):
        """社媒运营配置"""
        model_config = SettingsConfigDict(env_prefix="SOCIAL_")

        auto_publish: bool = Field(default=False, description="自动发布开关")
        default_platforms: str = Field(default="x,xhs", description="默认发布平台")
        content_review: bool = Field(default=True, description="发布前人工审核")

    class XianyuConfig(BaseSettings):
        """闲鱼客服配置"""
        model_config = SettingsConfigDict(env_prefix="XIANYU_")

        hb_interval: int = Field(default=15, description="心跳间隔 (秒)")
        token_ttl: int = Field(default=3600, description="Token 有效期 (秒)")
        manual_timeout: int = Field(default=3600, description="人工接管超时 (秒)")
        simulate_typing: bool = Field(default=True, description="模拟人工打字延迟")

    class AppSettings(BaseSettings):
        """OpenClaw 主配置"""
        model_config = SettingsConfigDict(
            env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
            env_file_encoding="utf-8",
            extra="ignore",
        )

        # 子配置
        trading: TradingConfig = TradingConfig()
        ai: AIConfig = AIConfig()
        telegram: TelegramConfig = TelegramConfig()
        social: SocialConfig = SocialConfig()
        xianyu: XianyuConfig = XianyuConfig()

        # 全局
        debug: bool = Field(default=False, description="调试模式")
        data_dir: str = Field(
            default=str(Path(__file__).resolve().parent.parent / "data"),
            description="数据目录",
        )

        def to_safe_dict(self) -> dict:
            """导出配置快照（不含敏感值）"""
            return {
                "debug": self.debug,
                "data_dir": self.data_dir,
                "trading": {
                    "daily_budget": self.trading.daily_budget,
                    "auto_trade": self.trading.auto_trade,
                    "scan_interval_min": self.trading.scan_interval_min,
                },
                "ai": {
                    "daily_cost_limit": self.ai.daily_cost_limit,
                    "default_model": self.ai.default_model,
                    "cache_ttl": self.ai.cache_ttl,
                },
                "telegram": {
                    "rate_limit_per_min": self.telegram.rate_limit_per_min,
                    "streaming_edit_interval": self.telegram.streaming_edit_interval,
                },
                "social": {
                    "auto_publish": self.social.auto_publish,
                    "content_review": self.social.content_review,
                },
                "xianyu": {
                    "simulate_typing": self.xianyu.simulate_typing,
                    "hb_interval": self.xianyu.hb_interval,
                },
            }

    # 全局单例
    settings = AppSettings()

else:
    # pydantic-settings 不可用时的降级
    class _FallbackSettings:
        """降级配置 — 直接读 os.getenv()"""
        class _Sub:
            def __getattr__(self, name):
                return os.getenv(name.upper(), None)
        trading = _Sub()
        ai = _Sub()
        telegram = _Sub()
        social = _Sub()
        xianyu = _Sub()
        debug = os.getenv("DEBUG", "").lower() == "true"
        data_dir = str(Path(__file__).resolve().parent.parent / "data")

        def to_safe_dict(self):
            return {"source": "fallback", "debug": self.debug}

    settings = _FallbackSettings()
