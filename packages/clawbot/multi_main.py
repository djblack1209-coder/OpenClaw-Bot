#!/usr/bin/env python3
"""
ClawBot 多机器人版 v5.0 - Mixin 架构版
- MultiBot 类已拆分到 src/bot/ 目录（Mixin 架构）
- 本文件仅保留：Bot 配置、main() 启动逻辑、信号处理
"""
import os
import sys
import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from telegram import BotCommand

# 加载配置
config_path = Path(__file__).parent / 'config' / '.env'
load_dotenv(config_path)

# 配置日志
log_dir = Path(__file__).parent / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / 'multi_bot.log')
    ]
)
logger = logging.getLogger(__name__)

# 降噪：抑制高频第三方库日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("ib_insync.wrapper").setLevel(logging.WARNING)
logging.getLogger("ib_insync.client").setLevel(logging.WARNING)

# 导入重构后的 MultiBot 和全局共享组件
from src.bot.multi_bot import MultiBot
from src.bot.globals import (
    SILICONFLOW_KEYS, CLAUDE_KEY, ALLOWED_USER_IDS,
    history_store, chat_router, collab_orchestrator,
    metrics, health_checker, shared_memory,
    bot_registry, ibkr, portfolio, execution_hub,
    get_stock_quote, invest_warmup,
)
from src.monitoring import AutoRecovery
from src.trading_system import (
    init_trading_system, start_trading_system, stop_trading_system,
    set_ai_team_callers,
)
from src.trading_journal import journal


# ============ Bot 配置 ============

_COMMON_COMMANDS = [
    BotCommand("start", "开始使用"),
    BotCommand("clear", "清空对话"),
    BotCommand("status", "查看状态"),
    BotCommand("config", "查看运行配置"),
    BotCommand("cost", "查看请求/配额"),
    BotCommand("context", "上下文状态"),
    BotCommand("compact", "压缩上下文"),
    BotCommand("news", "最新资讯"),
    BotCommand("metrics", "运行指标"),
    BotCommand("hot", "热点一键发文"),
    BotCommand("post_social", "专用浏览器双平台发文"),
    BotCommand("post_x", "专用浏览器发 X"),
    BotCommand("post_xhs", "专用浏览器发小红书"),
    BotCommand("social_plan", "生成社媒发文计划"),
    BotCommand("social_persona", "查看当前社媒人设"),
    BotCommand("topic", "研究一个题材"),
    BotCommand("dev", "开发/配置流程"),
    BotCommand("ops", "更多高级入口"),
    BotCommand("invest", "投资分析"),
    BotCommand("quote", "实时行情"),
    BotCommand("scan", "市场扫描"),
    BotCommand("ta", "技术分析"),
    BotCommand("signal", "交易信号"),
    BotCommand("risk", "风险检查"),
    BotCommand("monitor", "持仓监控"),
    BotCommand("backtest", "回测策略"),
    BotCommand("rebalance", "再平衡建议"),
    BotCommand("lanes", "群聊分流规则"),
    BotCommand("xianyu", "闲鱼AI客服 start/stop/status/reload"),
    BotCommand("social_calendar", "社媒内容日历"),
    BotCommand("social_report", "社媒发帖效果报告"),
]

BOTS = [
    {
        "id": "qwen235b",
        "token": os.getenv('QWEN235B_TOKEN', ''),
        "username": os.getenv('QWEN235B_USERNAME', 'carven_Qwen235B_Bot'),
        "model": "qwen-3-235b",
        "api_type": "g4f",
        "is_claude": False,
        "keywords": ["qwen", "千问", "235b", "研究路线", "学习路径"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "gptoss",
        "token": os.getenv('GPTOSS_TOKEN', ''),
        "username": os.getenv('GPTOSS_USERNAME', 'carven_GPTOSS120B_Bot'),
        "model": "gpt-oss-120b",
        "api_type": "g4f",
        "is_claude": False,
        "keywords": ["gptoss", "gpt-oss", "oss", "快问", "翻译"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "claude_sonnet",
        "token": os.getenv('CLAUDE_SONNET_TOKEN', ''),
        "username": os.getenv('CLAUDE_SONNET_USERNAME', 'carven_ClaudeSonnet_Bot'),
        "model": "claude-sonnet-4.5",
        "api_type": "kiro",
        "is_claude": False,
        "keywords": ["claude", "sonnet", "架构设计", "复杂分析", "系统设计", "方案设计"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "claude_haiku",
        "token": os.getenv('CLAUDE_HAIKU_TOKEN', ''),
        "username": os.getenv('CLAUDE_HAIKU_USERNAME', 'carven_ClaudeHaiku_Bot'),
        "model": "claude-haiku-4.5",
        "api_type": "kiro",
        "is_claude": False,
        "keywords": ["haiku", "文案", "创意", "短文案", "标题灵感"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "deepseek_v3",
        "token": os.getenv('DEEPSEEK_V3_TOKEN', ''),
        "username": os.getenv('DEEPSEEK_V3_USERNAME', 'carven_DeepSeekV3_Bot'),
        "model": "deepseek-3.2",
        "api_type": "kiro",
        "is_claude": False,
        "keywords": ["deepseek", "v3", "代码实现", "中文润色", "技术实现", "执行步骤"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "claude_opus",
        "token": os.getenv('CLAUDE_OPUS_TOKEN', ''),
        "username": os.getenv('CLAUDE_OPUS_USERNAME', 'carven_ClaudeOpus_Bot'),
        "model": "claude-opus-4-6",
        "api_type": "g4f",
        "is_claude": False,
        "keywords": ["opus", "终极分析", "深度推理", "复杂推理", "大脑"],
        "commands": list(_COMMON_COMMANDS),
    },
]


# ============ 全局变量 ============

bots: list = []
stop_event = asyncio.Event()
auto_recovery: Optional[AutoRecovery] = None


# ============ 主函数 ============

async def main():
    global bots, auto_recovery

    logger.info("=" * 60)
    logger.info("ClawBot 多机器人系统 v5.0 (Mixin 架构版)")
    logger.info("=" * 60)
    logger.info(f"配置文件: {config_path}")
    logger.info(f"硅基流动 Keys: {len(SILICONFLOW_KEYS)} 个")
    logger.info(f"Claude API: {'已配置' if CLAUDE_KEY else '未配置'}")
    logger.info(f"允许用户: {ALLOWED_USER_IDS or '所有'}")
    logger.info(f"存储: SQLite ({history_store.db_path})")
    logger.info("=" * 60)

    # 启动所有 bot
    for config in BOTS:
        try:
            bot = MultiBot(config)
            result = await bot.run_async()
            if result:
                bots.append(bot)
                bot_registry[bot.bot_id] = bot
                # 注册 bot 的 Telegram user_id，用于过滤 bot 互相回复
                try:
                    app = bot.app
                    if app:
                        bot_info = await app.bot.get_me()
                        chat_router.register_bot_user_id(bot_info.id)
                        logger.info(f"[{config['id']}] 注册 bot user_id: {bot_info.id}")
                except Exception as e:
                    logger.warning(f"[{config['id']}] 获取 bot user_id 失败: {e}")
        except Exception as e:
            logger.error(f"[{config['id']}] 启动失败: {e}")

    # 启动自动恢复
    auto_recovery = AutoRecovery(
        health_checker,
        max_restarts=int(os.environ.get("MAX_RESTARTS", "3")),
        restart_cooldown=float(os.environ.get("RESTART_COOLDOWN", "60.0")),
    )
    for bot in bots:
        auto_recovery.register_restart_func(bot.bot_id, bot.run_async, bot.stop_async)
        collab_orchestrator.register_api_caller(bot.bot_id, bot._call_api)
    auto_recovery.start()

    # 注册 LLM 路由（使用 qwen235b 作为路由模型，免费无限）
    router_instance = next((b for b in bots if b.bot_id == "qwen235b"), None)
    if router_instance:
        async def _llm_router_call(chat_id: int, prompt: str) -> str:
            return await router_instance._call_api(chat_id, prompt, save_history=False)
        chat_router.register_llm_router(_llm_router_call)
        logger.info("  LLM 路由已注册 (使用 qwen235b/qwen-3-235b, 不保存历史)")

    logger.info("=" * 60)
    logger.info(f"成功启动 {len(bots)} 个 Bot:")
    for bot in bots:
        logger.info(f"  {bot.emoji} {bot.name} - {bot.role} (@{bot.username})")
    logger.info("=" * 60)

    # 后台预热 yfinance
    asyncio.create_task(invest_warmup())

    # 连接 IBKR Paper Trading
    async def _connect_ibkr():
        ok = await ibkr.connect()
        if ok:
            logger.info("[IBKR] Paper Trading 连接成功 (预算$%.0f)" % ibkr.budget)
        else:
            logger.warning("[IBKR] 连接失败，IBKR命令不可用（IB Gateway是否运行？）")
    asyncio.create_task(_connect_ibkr())

    # 初始化自动交易系统
    _notify_chat_id = int(os.environ.get("NOTIFY_CHAT_ID", "0"))
    if not _notify_chat_id and ALLOWED_USER_IDS:
        _notify_chat_id = next(iter(ALLOWED_USER_IDS))
    _private_notify_chat_id = int(os.environ.get("PRIVATE_NOTIFY_CHAT_ID", "0"))
    if not _private_notify_chat_id and ALLOWED_USER_IDS:
        _private_notify_chat_id = next(iter(ALLOWED_USER_IDS))

    async def _notify_telegram(text):
        if bots and _notify_chat_id:
            try:
                app = bots[0].app
                if app:
                    await app.bot.send_message(chat_id=_notify_chat_id, text=text)
            except Exception as e:
                logger.error("[TradingSystem] 通知发送失败: %s", e)

    async def _notify_private_telegram(text):
        if bots and _private_notify_chat_id:
            try:
                app = bots[0].app
                if app:
                    await app.bot.send_message(chat_id=_private_notify_chat_id, text=text)
            except Exception as e:
                logger.error("[ExecutionHub] 私聊通知发送失败: %s", e)

    init_trading_system(
        broker=ibkr,
        journal=journal,
        portfolio=portfolio,
        get_quote_func=get_stock_quote,
        notify_func=_notify_telegram,
        capital=float(os.environ.get("IBKR_BUDGET", "2000.0")),
        auto_mode=os.environ.get("AUTO_TRADE_MODE", "true").lower() == "true",
        scan_interval=int(os.environ.get("SCAN_INTERVAL", "30")),
    )
    ibkr.set_notify(_notify_telegram)

    # 注入AI团队API callers
    ai_callers = {}
    for bot in bots:
        if bot.bot_id in ("claude_haiku", "qwen235b", "gptoss", "deepseek_v3", "claude_sonnet", "claude_opus"):
            async def _make_caller(b):
                async def _call(chat_id, prompt):
                    return await b._call_api(chat_id, prompt, save_history=False)
                return _call
            ai_callers[bot.bot_id] = await _make_caller(bot)
    if ai_callers:
        set_ai_team_callers(ai_callers)
        execution_hub.set_social_ai_callers(ai_callers)
        logger.info("  - AI团队投票已就绪: %s", list(ai_callers.keys()))

    asyncio.create_task(start_trading_system())
    logger.info("  - 自动交易系统已初始化 (风控/监控/管道/调度)")

    await execution_hub.start_scheduler(_notify_telegram, _notify_private_telegram)
    logger.info("  - 执行场景调度器已启动")

    _heartbeat_interval = int(os.environ.get("HEARTBEAT_INTERVAL", "60"))
    _cleanup_interval = int(os.environ.get("CLEANUP_INTERVAL", "60"))
    _cleanup_max_age = float(os.environ.get("CLEANUP_MAX_AGE", "3600.0"))

    try:
        cleanup_counter = 0
        heartbeat_counter = 0
        while not stop_event.is_set():
            await asyncio.sleep(1)
            cleanup_counter += 1
            heartbeat_counter += 1
            if heartbeat_counter >= _heartbeat_interval:
                heartbeat_counter = 0
                for bot in bots:
                    if bot.app and bot.app.updater and bot.app.updater.running:
                        health_checker.heartbeat(bot.bot_id)
            if cleanup_counter >= _cleanup_interval:
                cleanup_counter = 0
                collab_orchestrator.cleanup_old_tasks(max_age=_cleanup_max_age)
    except asyncio.CancelledError:
        pass

    # 优雅关闭
    logger.info("正在停止...")
    await execution_hub.stop_scheduler()
    await stop_trading_system()
    if auto_recovery:
        auto_recovery.stop()
    metrics.shutdown()
    history_store.close()
    shared_memory.close()
    for bot in bots:
        try:
            await bot.http_client.close()
            await bot.stop_async()
        except Exception:
            pass
    logger.info("已停止")


def signal_handler(sig, frame):
    logger.info("收到停止信号")
    stop_event.set()


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
