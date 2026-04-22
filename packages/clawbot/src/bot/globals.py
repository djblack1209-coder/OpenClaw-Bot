"""
全局共享状态 — 从 multi_main.py 提取
所有 mixin 通过 import 此模块访问共享组件，避免循环依赖。

注意: 纯配置(环境变量/API Key管理)已提取到 src.bot.config (HI-359)。
本模块保留运行时共享状态 + 向后兼容 re-export。
"""
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# ---- 从 config.py 导入纯配置 (HI-359: 打破循环依赖) ----
from src.bot.config import (  # noqa: F401 — 向后兼容 re-export
    parse_ids,
    ALLOWED_USER_IDS,
    SILICONFLOW_KEYS, SILICONFLOW_BASE, SILICONFLOW_PAID_KEYS,
    DATA_DIR, CLAUDE_KEY, CLAUDE_BASE,
    G4F_BASE, G4F_KEY, KIRO_BASE, KIRO_KEY,
    SERPAPI_KEY, BRAVE_SEARCH_API_KEY,
    COMPOSIO_API_KEY, SKYVERN_API_KEY,
    current_sf_key_idx, sf_key_balances, LOW_BALANCE_THRESHOLD,
    get_siliconflow_key, update_key_balance, get_total_balance, mark_key_exhausted,
)

from src.constants import TG_SAFE_LENGTH
from src.history_store import HistoryStore
from src.routing import ChatRouter, CollabOrchestrator
from src.monitoring import StructuredLogger, HealthChecker
from src.news_fetcher import NewsFetcher
from src.tools.image_tool import ImageTool
from src.context_manager import ContextManager
from src.tool_executor import ToolExecutor
from src.shared_memory import SharedMemory
from src.execution import ExecutionHub
from src.litellm_router import init_free_pool
from src.utils import now_et
from src.message_sender import send_long_message  # noqa: F401 re-export: 78+ 处引用
from src.invest_tools import get_stock_quote  # noqa: F401 re-export: message_mixin 等引用
from src.pipeline_helper import execute_trade_via_pipeline  # noqa: F401 re-export
from src.trading_system import get_trading_pipeline  # noqa: F401 re-export

logger = logging.getLogger(__name__)

# ============ 全局共享组件 ============

history_store = HistoryStore()
context_manager = ContextManager()
news_fetcher = NewsFetcher()
execution_hub = ExecutionHub(news_fetcher=news_fetcher)
image_tool = ImageTool()
chat_router = ChatRouter()
collab_orchestrator = CollabOrchestrator(chat_router)
metrics = StructuredLogger("multi_bot")
health_checker = HealthChecker()
shared_memory = SharedMemory()
tool_executor = ToolExecutor(
    working_dir=str(Path(__file__).parents[2]),
    siliconflow_key_func=lambda: get_siliconflow_key(),
    shared_memory=shared_memory,
)

# Bot 实例注册表
bot_registry: Dict[str, 'object'] = {}

# 待确认交易
_pending_trades: Dict[str, dict] = {}

# ============ 优化模块全局实例（供 mixin 层访问） ============
# 由 multi_main.py 启动时注入，避免 mixin 层自行实例化

tiered_context_manager = None       # TieredContextManager 实例
priority_message_queue = None       # PriorityMessageQueue 实例
strategy_engine_instance = None     # StrategyEngine 实例
ab_test_manager = None              # ABTestManager 实例

# 初始化免费API池
init_free_pool()


def _cleanup_pending_trades():
    """清理超过1小时的过期待确认交易，防止内存泄漏"""
    now = now_et()
    expired = []
    for k, v in _pending_trades.items():
        try:
            ts = datetime.fromisoformat(v.get("timestamp", ""))
            if (now - ts).total_seconds() > 3600:
                expired.append(k)
        except (ValueError, TypeError) as e:  # noqa: F841
            expired.append(k)  # 无效时间戳也清理
    for k in expired:
        _pending_trades.pop(k, None)
    if expired:
        logger.info("[PendingTrades] 清理 %d 个过期待确认交易", len(expired))


# ============ 辅助函数 ============

async def send_as_bot(bot_id: str, chat_id: int, text: str, reply_to_message_id: Optional[int] = None):
    """用指定 bot 自己的 Telegram 账号发送消息"""
    from src.message_sender import _clean_for_telegram, _split_message

    target_bot = bot_registry.get(bot_id)
    if not target_bot or not target_bot.app:
        logger.warning(f"[send_as_bot] {bot_id} 未注册或未启动")
        return

    bot_telegram = target_bot.app.bot
    cleaned = _clean_for_telegram(text)
    parts = _split_message(cleaned, TG_SAFE_LENGTH)

    for i, part in enumerate(parts):
        reply_id = reply_to_message_id if i == 0 else None
        try:
            await bot_telegram.send_message(
                chat_id=chat_id, text=part,
                parse_mode="Markdown", reply_to_message_id=reply_id,
            )
        except Exception:
            logger.debug("[send_as_bot] Markdown failed for %s, falling back to plain text", bot_id)
            try:
                await bot_telegram.send_message(
                    chat_id=chat_id, text=part,
                    reply_to_message_id=reply_id,
                )
            except Exception:
                logger.debug("[send_as_bot] reply fallback failed for %s, sending without reply", bot_id)
                await bot_telegram.send_message(chat_id=chat_id, text=part)
        if i < len(parts) - 1:
            await asyncio.sleep(0.3)


async def safe_edit(msg, text: str, parse_mode: str = "Markdown"):
    """安全编辑消息，Markdown 失败回退纯文本"""
    try:
        await msg.edit_text(text, parse_mode=parse_mode)
    except Exception:
        logger.debug("[safe_edit] parse_mode=%s failed, falling back to plain text", parse_mode)
        try:
            await msg.edit_text(text)
        except Exception as e:
            logger.debug("[safe_edit] plain text edit also failed: %s", e)


# ============ Per-User 偏好管理 — 搬运自 father-bot 的 user settings 模式 ============

import json as _json

class UserPreferencesManager:
    """Per-user 偏好管理器 — 持久化到 JSON 文件

    搬运自 father-bot/chatgpt_telegram_bot 的 user settings 模式。
    每个用户独立的通知/语言/风险/模式偏好。
    """
    DEFAULTS = {
        "notify_level": "normal",       # silent / normal / verbose
        "risk_tolerance": "moderate",   # conservative / moderate / aggressive
        "language": "zh",               # zh / en
        "chat_mode": "assistant",       # assistant / trader / analyst / creative
        "auto_trade_notify": True,      # 是否接收自动交易通知
        "daily_report": True,           # 是否接收每日报告
        "social_preview": False,        # 社交发文是否默认预览模式
    }

    def __init__(self, data_dir: str = "data"):
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._filepath = self._dir / "user_preferences.json"
        self._prefs: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if self._filepath.exists():
            try:
                with open(self._filepath, 'r', encoding='utf-8') as f:
                    self._prefs = _json.load(f)
            except Exception as e:  # noqa: F841
                self._prefs = {}

    def _save(self):
        try:
            with open(self._filepath, 'w', encoding='utf-8') as f:
                _json.dump(self._prefs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("[UserPrefs] 保存失败: %s", e)

    def get(self, user_id: int, key: str, default=None):
        uid = str(user_id)
        user_prefs = self._prefs.get(uid, {})
        if default is not None:
            return user_prefs.get(key, default)
        return user_prefs.get(key, self.DEFAULTS.get(key))

    def set(self, user_id: int, key: str, value):
        uid = str(user_id)
        if uid not in self._prefs:
            self._prefs[uid] = {}
        self._prefs[uid][key] = value
        self._save()

    def get_all(self, user_id: int) -> dict:
        uid = str(user_id)
        result = dict(self.DEFAULTS)
        result.update(self._prefs.get(uid, {}))
        return result

    def reset(self, user_id: int):
        uid = str(user_id)
        self._prefs.pop(uid, None)
        self._save()


# 全局实例
user_prefs = UserPreferencesManager()
