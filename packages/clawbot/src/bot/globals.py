"""
全局共享状态 — 从 multi_main.py 提取
所有 mixin 通过 import 此模块访问共享组件，避免循环依赖。
"""
import os
import logging
import asyncio
from pathlib import Path
from typing import Dict, Optional

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from src.http_client import ResilientHTTPClient, RetryConfig, CircuitBreaker, CircuitOpenError
from src.history_store import HistoryStore
from src.message_sender import send_long_message
from src.chat_router import ChatRouter, BotCapability, CollabOrchestrator
from src.monitoring import StructuredLogger, HealthChecker, AutoRecovery
from src.news_fetcher import NewsFetcher
from src.tools.image_tool import ImageTool
from src.context_manager import ContextManager
from src.tool_executor import ToolExecutor, MULTI_BOT_TOOLS
from src.shared_memory import SharedMemory
from src.execution_hub import ExecutionHub
from config.bot_profiles import get_bot_config, BOT_PROFILES
from src.invest_tools import (
    get_stock_quote, get_crypto_quote, get_market_summary,
    format_quote, portfolio, warmup as invest_warmup,
)
from src.broker_bridge import ibkr
from src.ta_engine import (
    get_full_analysis, scan_market, format_analysis,
    format_scan_results, compute_signal_score, calc_position_size,
)
from src.universe import full_market_scan, format_full_scan, get_universe_stats, get_full_universe
from src.trading_journal import journal
from src.trading_system import (
    init_trading_system, start_trading_system, stop_trading_system,
    get_risk_manager, get_position_monitor, get_auto_trader,
    get_trading_pipeline, get_system_status,
)
from src.pipeline_helper import execute_trade_via_pipeline

logger = logging.getLogger(__name__)

if load_dotenv:
    _config_env_path = Path(__file__).resolve().parents[2] / "config" / ".env"
    if _config_env_path.exists():
        load_dotenv(_config_env_path)

# ============ 环境变量 / API 配置 ============

def parse_ids(s):
    if not s:
        return set()
    return {int(x.strip()) for x in s.split(',') if x.strip().isdigit()}

ALLOWED_USER_IDS = parse_ids(os.getenv('ALLOWED_USER_IDS', ''))

SILICONFLOW_KEYS = [k.strip() for k in os.getenv('SILICONFLOW_KEYS', '').split(',') if k.strip()]
SILICONFLOW_BASE = os.getenv('SILICONFLOW_BASE_URL', 'https://api.siliconflow.cn/v1')
CLAUDE_KEY = os.getenv('CLAUDE_API_KEY', '')
CLAUDE_BASE = os.getenv('CLAUDE_BASE_URL', 'https://api.anthropic.com/v1')
G4F_BASE = os.getenv('G4F_BASE_URL', 'http://127.0.0.1:18791/v1')
G4F_KEY = os.getenv('G4F_API_KEY', 'dummy')
KIRO_BASE = os.getenv('KIRO_BASE_URL', 'http://127.0.0.1:18793/v1')
KIRO_KEY = os.getenv('KIRO_API_KEY', '')

# 硅基流动 Key 管理
current_sf_key_idx = 0
_sf_init_balance = float(os.getenv("SF_INITIAL_BALANCE", "13.0"))
sf_key_balances = {k: _sf_init_balance for k in SILICONFLOW_KEYS}
LOW_BALANCE_THRESHOLD = float(os.getenv('SF_LOW_BALANCE', '1.0'))


def get_siliconflow_key():
    """获取可用的硅基流动 Key，自动跳过低余额的"""
    global current_sf_key_idx
    if not SILICONFLOW_KEYS:
        return None
    for _ in range(len(SILICONFLOW_KEYS)):
        key = SILICONFLOW_KEYS[current_sf_key_idx % len(SILICONFLOW_KEYS)]
        current_sf_key_idx += 1
        balance = sf_key_balances.get(key, 0)
        if balance > LOW_BALANCE_THRESHOLD:
            return key
    logger.warning("所有 API Key 余额不足！")
    return SILICONFLOW_KEYS[0] if SILICONFLOW_KEYS else None


def update_key_balance(key: str, cost: float):
    if key in sf_key_balances:
        sf_key_balances[key] = max(0, sf_key_balances[key] - cost)
        if sf_key_balances[key] < LOW_BALANCE_THRESHOLD:
            logger.warning(f"API Key {key[:20]}... 余额不足: {sf_key_balances[key]:.2f}元")


def get_total_balance() -> float:
    return sum(sf_key_balances.values())


def mark_key_exhausted(key: str):
    """API 返回余额不足错误时，标记该 Key 为耗尽"""
    if key in sf_key_balances:
        sf_key_balances[key] = 0
        logger.warning(f"API Key {key[:20]}... 已标记为耗尽（API返回余额不足）")


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


def _cleanup_pending_trades():
    """清理超过1小时的过期待确认交易，防止内存泄漏"""
    from datetime import datetime
    now = datetime.now()
    expired = []
    for k, v in _pending_trades.items():
        try:
            ts = datetime.fromisoformat(v.get("timestamp", ""))
            if (now - ts).total_seconds() > 3600:
                expired.append(k)
        except (ValueError, TypeError):
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
    parts = _split_message(cleaned, 4000)

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
