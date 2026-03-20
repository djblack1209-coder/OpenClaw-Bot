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
    get_stock_quote, invest_warmup, context_manager,
)
from src.monitoring import AutoRecovery, start_metrics_server, AlertManager, AlertRule
from src.trading_system import (
    init_trading_system, start_trading_system, stop_trading_system,
    set_ai_team_callers,
)
from src.trading_journal import journal, trading_memory_bridge
from src.litellm_router import free_pool, ROUTE_BALANCED
from src.context_manager import TieredContextManager
from src.chat_router import PriorityMessageQueue
from src.strategy_engine import create_default_engine
from src.social_tools import ABTestManager
from src.langfuse_obs import init_langfuse
import src.bot.globals as g


# ============ Bot 配置 ============

_COMMON_COMMANDS = [
    # --- 基础 ---
    BotCommand("start", "开始使用 / 帮助菜单"),
    BotCommand("clear", "清空对话历史"),
    BotCommand("status", "查看系统状态"),
    BotCommand("config", "查看运行配置"),
    BotCommand("cost", "配额与成本看板"),
    BotCommand("context", "上下文状态"),
    BotCommand("compact", "压缩上下文"),
    BotCommand("metrics", "运行指标"),
    BotCommand("model", "查看当前模型信息"),
    # --- 资讯 & 社媒 ---
    BotCommand("news", "AI/科技最新资讯"),
    BotCommand("hot", "热点一键发文"),
    BotCommand("post_social", "专用浏览器双平台发文"),
    BotCommand("post_x", "专用浏览器发 X"),
    BotCommand("post_xhs", "专用浏览器发小红书"),
    BotCommand("social_plan", "生成社媒发文计划"),
    BotCommand("social_persona", "查看当前社媒人设"),
    BotCommand("social_calendar", "社媒内容日历"),
    BotCommand("social_report", "社媒发帖效果报告"),
    BotCommand("topic", "研究一个题材"),
    # --- 执行场景 ---
    BotCommand("dev", "开发/配置流程"),
    BotCommand("ops", "更多高级入口"),
    BotCommand("brief", "执行简报 / PnL 日报"),
    # --- 投资 & 交易 ---
    BotCommand("invest", "投资分析"),
    BotCommand("quote", "实时行情"),
    BotCommand("scan", "市场扫描"),
    BotCommand("ta", "技术分析"),
    BotCommand("signal", "交易信号"),
    BotCommand("risk", "风险检查"),
    BotCommand("monitor", "持仓监控"),
    BotCommand("backtest", "回测策略"),
    BotCommand("rebalance", "再平衡建议"),
    # --- 群聊 & 系统 ---
    BotCommand("lanes", "群聊分流规则"),
    BotCommand("xianyu", "闲鱼AI客服 start/stop/status"),
]

# Free-LLM-Bot 简化命令集（聚焦核心功能，避免冗余）
_FREE_LLM_COMMANDS = [
    BotCommand("start", "开始使用 / 帮助菜单"),
    BotCommand("clear", "清空对话历史"),
    BotCommand("status", "查看状态与当前模型"),
    BotCommand("pool", "免费API池状态"),
    BotCommand("model", "查看当前使用的模型"),
    BotCommand("cost", "配额与成本看板"),
    BotCommand("news", "AI/科技最新资讯"),
    BotCommand("quote", "实时行情"),
]

BOTS = [
    {
        "id": "qwen235b",
        "token": os.getenv('QWEN235B_TOKEN', ''),
        "username": os.getenv('QWEN235B_USERNAME', 'carven_Qwen235B_Bot'),
        "model": "qwen-3-235b",
        "api_type": "free_pool",
        "is_claude": False,
        "keywords": ["qwen", "千问", "235b", "研究路线", "学习路径"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "gptoss",
        "token": os.getenv('GPTOSS_TOKEN', ''),
        "username": os.getenv('GPTOSS_USERNAME', 'carven_GPTOSS120B_Bot'),
        "model": "gpt-oss-120b",
        "api_type": "free_pool",
        "is_claude": False,
        "keywords": ["gptoss", "gpt-oss", "oss", "快问", "翻译"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "claude_sonnet",
        "token": os.getenv('CLAUDE_SONNET_TOKEN', ''),
        "username": os.getenv('CLAUDE_SONNET_USERNAME', 'carven_ClaudeSonnet_Bot'),
        "model": "claude-sonnet-4-5",
        "api_type": "free_pool",
        "is_claude": False,
        "keywords": ["claude", "sonnet", "架构设计", "复杂分析", "系统设计", "方案设计"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "claude_haiku",
        "token": os.getenv('CLAUDE_HAIKU_TOKEN', ''),
        "username": os.getenv('CLAUDE_HAIKU_USERNAME', 'carven_ClaudeHaiku_Bot'),
        "model": "claude-haiku-4-5",
        "api_type": "free_pool",
        "is_claude": False,
        "keywords": ["haiku", "文案", "创意", "短文案", "标题灵感"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "deepseek_v3",
        "token": os.getenv('DEEPSEEK_V3_TOKEN', ''),
        "username": os.getenv('DEEPSEEK_V3_USERNAME', 'carven_DeepSeekV3_Bot'),
        "model": "deepseek-v3.2",
        "api_type": "free_pool",
        "is_claude": False,
        "keywords": ["deepseek", "v3", "代码实现", "中文润色", "技术实现", "执行步骤"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "claude_opus",
        "token": os.getenv('CLAUDE_OPUS_TOKEN', ''),
        "username": os.getenv('CLAUDE_OPUS_USERNAME', 'carven_ClaudeOpus_Bot'),
        "model": "claude-opus-4-5",
        "api_type": "free_first",
        "is_claude": False,
        "keywords": ["opus", "终极分析", "深度推理", "复杂推理", "大脑"],
        "commands": list(_COMMON_COMMANDS),
    },
    {
        "id": "free_llm",
        "token": os.getenv('FREE_LLM_TOKEN', '8676504472:AAFNbg40iy_Px0-jl1GlfHQTC92kGwPw-A8'),
        "username": os.getenv('FREE_LLM_USERNAME', 'Free_LLM_Bot'),
        "model": "free-pool-best",
        "api_type": "free_pool",
        "is_claude": False,
        "keywords": ["free", "免费", "白嫖", "gemini", "groq", "cerebras", "mistral", "kimi"],
        "commands": list(_FREE_LLM_COMMANDS),
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

    # === 集成优化模块 (2026-03-17 优化报告) ===

    # 0. 初始化 Langfuse 观测层（LLM 全链路追踪）
    langfuse_ok = init_langfuse()
    logger.info(f"  Langfuse 观测层: {'已连接' if langfuse_ok else '未配置（静默降级）'}")

    # 1. 启动 Prometheus 指标服务器
    metrics_port = int(os.environ.get("METRICS_PORT", "9090"))
    metrics_server = start_metrics_server(port=metrics_port)
    logger.info(f"  Prometheus 指标服务器: http://localhost:{metrics_port}/metrics")

    # 2. 设置 API 池路由策略为综合均衡模式
    free_pool.default_routing = ROUTE_BALANCED
    logger.info(f"  API 池路由策略: {ROUTE_BALANCED}")

    # 3. 初始化分层上下文管理 (MemGPT 风格) → 注入全局
    g.tiered_context_manager = TieredContextManager(
        context_manager=context_manager,
        shared_memory=shared_memory,
    )
    logger.info("  分层上下文管理器已初始化 → globals.tiered_context_manager")

    # 4. 初始化策略引擎 → 注入全局
    g.strategy_engine_instance = create_default_engine()
    logger.info(f"  策略引擎已初始化 ({len(g.strategy_engine_instance._strategies)} 个内置策略) → globals.strategy_engine_instance")

    # 5. 初始化优先级消息队列 → 注入全局
    g.priority_message_queue = PriorityMessageQueue()
    logger.info("  优先级消息队列已初始化 → globals.priority_message_queue")

    # 6. 初始化社交 A/B 测试管理器 → 注入全局
    g.ab_test_manager = ABTestManager()
    logger.info("  社交 A/B 测试管理器已初始化 → globals.ab_test_manager")

    # 8. 挂载交易记忆桥接（自动将交易事件写入共享记忆）
    trading_memory_bridge.attach(shared_memory=shared_memory)
    logger.info("  交易记忆桥接已挂载 (开仓/平仓/复盘 → SharedMemory)")

    # 7. 设置告警规则
    alert_mgr = AlertManager()

    # 告警: API 连续错误过多
    def _check_high_errors():
        stats = free_pool.get_stats()
        active = stats.get("active_sources", 0)
        total = stats.get("total_sources", 1)
        return active < total * 0.5  # 超过一半源不可用
    def _msg_high_errors():
        stats = free_pool.get_stats()
        return f"⚠️ [告警] API 池健康度下降: {stats.get('active_sources', 0)}/{stats.get('total_sources', 0)} 源可用"

    # 告警: Bot 心跳丢失
    def _check_heartbeat_lost():
        status = health_checker.check_all()
        return any(not healthy for healthy in status.values()) if status else False
    def _msg_heartbeat_lost():
        status = health_checker.get_status()
        unhealthy = [bid for bid, s in status.items() if not s["healthy"]]
        return f"⚠️ [告警] Bot 心跳丢失: {', '.join(unhealthy)}"

    alert_mgr.add_rule(AlertRule(
        name="high_error_rate",
        condition_fn=_check_high_errors,
        message_fn=_msg_high_errors,
        cooldown=300,
    ))
    alert_mgr.add_rule(AlertRule(
        name="heartbeat_lost",
        condition_fn=_check_heartbeat_lost,
        message_fn=_msg_heartbeat_lost,
        cooldown=120,
    ))
    logger.info(f"  告警管理器已初始化 ({len(alert_mgr.rules)} 条规则)")

    # 8.5 初始化全局错误处理器 + Telegram 告警通知
    from src.error_handler import init_error_handler
    from src.monitoring_extras import TelegramAlertNotifier
    admin_chat_id = int(os.environ.get("ADMIN_CHAT_ID", "0")) or None
    first_token = BOTS[0]["token"] if BOTS else None
    if admin_chat_id and first_token:
        init_error_handler(
            admin_chat_id=admin_chat_id,
            bot_token=first_token,
            structured_logger=metrics,
        )
        # AlertManager → Telegram 通知
        notifier = TelegramAlertNotifier(bot_token=first_token, chat_id=admin_chat_id)
        alert_mgr.on_alert(notifier.sync_callback)
        logger.info(f"  错误处理器 + Telegram 告警通知已初始化 (admin={admin_chat_id})")
    else:
        init_error_handler(structured_logger=metrics)
        logger.info("  错误处理器已初始化 (无 Telegram 通知，未配置 ADMIN_CHAT_ID)")

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

    # 初始化智能记忆管道（搬运自 mem0 模式）
    from src.smart_memory import init_smart_memory
    if router_instance:
        async def _memory_llm(prompt: str) -> str:
            return await router_instance._call_api(-998, prompt, save_history=False)
        smart_mem = init_smart_memory(shared_memory, llm_fn=_memory_llm)
        logger.info("  智能记忆管道已初始化 (mem0 模式, LLM=qwen235b)")
    else:
        smart_mem = init_smart_memory(shared_memory)
        logger.info("  智能记忆管道已初始化 (无 LLM, 仅规则模式)")

    # mem0 记忆层已内置于 SharedMemory v4.0，无需额外 memory_layer
    logger.info(f"  记忆引擎: {shared_memory.get_stats().get('engine', 'sqlite')}")

    # 初始化 browser-use 浏览器代理
    try:
        from src.browser_use_bridge import init_browser_use
        init_browser_use(headless=True)
        logger.info("  browser-use 浏览器代理已初始化")
    except Exception as e:
        logger.info(f"  browser-use 初始化跳过: {e}")

    # 初始化 CrewAI 多 Agent 协作桥接
    try:
        from src.crewai_bridge import init_crewai_bridge
        init_crewai_bridge()
        logger.info("  CrewAI 多 Agent 协作桥接已初始化")
    except Exception as e:
        logger.info(f"  CrewAI 初始化跳过: {e}")

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
        """增强通知 — 搬运 freqtrade 的 actionable notification 模式
        关键交易事件自动附加 inline keyboard 操作按钮
        """
        if not bots or not _notify_chat_id:
            return
        try:
            app = bots[0].app
            if not app:
                return

            # 检测交易关键事件，附加操作按钮
            reply_markup = None
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                text_lower = text.lower() if text else ""

                if "交易执行成功" in text or "交易已成交" in text:
                    # 成交通知 → 查看持仓 / 查看风控
                    reply_markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📊 持仓", callback_data="cmd:/monitor"),
                        InlineKeyboardButton("🛡 风控", callback_data="cmd:/risk"),
                        InlineKeyboardButton("📈 系统", callback_data="cmd:/tradingsystem"),
                    ]])
                elif "风控拒绝" in text or "决策验证拒绝" in text:
                    # 风控拒绝 → 查看风控详情
                    reply_markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("🛡 风控详情", callback_data="cmd:/risk"),
                        InlineKeyboardButton("⚙️ 系统状态", callback_data="cmd:/tradingsystem"),
                    ]])
                elif "止损触发" in text or "止盈触发" in text or "追踪止损" in text:
                    # 平仓通知 → 查看持仓 / 今日PnL
                    reply_markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📊 持仓", callback_data="cmd:/monitor"),
                        InlineKeyboardButton("📋 日报", callback_data="cmd:/brief"),
                    ]])
                elif "订单已提交待成交" in text:
                    # 挂单通知 → 查看系统 / 取消
                    reply_markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📈 系统状态", callback_data="cmd:/tradingsystem"),
                        InlineKeyboardButton("🚫 取消挂单", callback_data="cmd:/autotrader cancel"),
                    ]])
                elif "告警" in text or "⚠️" in text:
                    # 告警通知 → 查看状态
                    reply_markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📊 状态", callback_data="cmd:/status"),
                        InlineKeyboardButton("🔧 系统", callback_data="cmd:/tradingsystem"),
                    ]])
            except Exception:
                pass  # inline keyboard 构建失败不影响通知发送

            await app.bot.send_message(
                chat_id=_notify_chat_id, text=text,
                reply_markup=reply_markup,
            )
        except Exception as e:
            logger.error("[TradingSystem] 通知发送失败: %s", e)

    # 通知批量合并器 — 防止 auto_trader 刷屏
    from src.telegram_ux import NotificationBatcher
    _notify_batcher = NotificationBatcher(
        send_func=_notify_telegram,
        flush_interval=20.0,
        max_batch=8,
    )

    async def _notify_batched(text):
        """智能通知：尊重用户偏好 + 关键事件立即发送 + 普通更新合并"""
        from src.bot.globals import user_prefs

        # 检查用户通知偏好
        notify_level = user_prefs.get(_notify_chat_id, "notify_level", "normal")
        auto_notify = user_prefs.get(_notify_chat_id, "auto_trade_notify", True)

        force_keywords = (
            "交易执行成功", "交易已成交", "止损触发", "止盈触发", "追踪止损",
            "风控拒绝", "自动停机", "熔断", "告警", "⚠️",
        )
        is_critical = any(kw in (text or "") for kw in force_keywords)

        # silent 模式：只发关键告警（风控/熔断/止损）
        if notify_level == "silent" and not is_critical:
            return
        # 用户关闭了交易通知 — 只过滤交易相关，非交易通知正常发
        if not auto_notify and any(kw in (text or "") for kw in ("交易", "BUY", "SELL", "止损", "止盈")):
            if not is_critical:
                return

        await _notify_batcher.add(_notify_chat_id, text, force=is_critical)

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
        notify_func=_notify_batched,
        capital=float(os.environ.get("IBKR_BUDGET", "2000.0")),
        auto_mode=os.environ.get("AUTO_TRADE_MODE", "true").lower() == "true",
        scan_interval=int(os.environ.get("SCAN_INTERVAL", "30")),
    )
    ibkr.set_notify(_notify_batched)

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

    # 注册告警回调 -> Telegram 通知
    def _on_alert(rule_name, message):
        asyncio.create_task(_notify_telegram(message))
    alert_mgr.on_alert(_on_alert)

    _heartbeat_interval = int(os.environ.get("HEARTBEAT_INTERVAL", "60"))
    _cleanup_interval = int(os.environ.get("CLEANUP_INTERVAL", "60"))
    _cleanup_max_age = float(os.environ.get("CLEANUP_MAX_AGE", "3600.0"))
    _alert_check_interval = int(os.environ.get("ALERT_CHECK_INTERVAL", "30"))

    try:
        cleanup_counter = 0
        heartbeat_counter = 0
        alert_counter = 0
        while not stop_event.is_set():
            await asyncio.sleep(1)
            cleanup_counter += 1
            heartbeat_counter += 1
            alert_counter += 1
            if heartbeat_counter >= _heartbeat_interval:
                heartbeat_counter = 0
                for bot in bots:
                    if bot.app and bot.app.updater and bot.app.updater.running:
                        health_checker.heartbeat(bot.bot_id)
            if cleanup_counter >= _cleanup_interval:
                cleanup_counter = 0
                collab_orchestrator.cleanup_old_tasks(max_age=_cleanup_max_age)
            if alert_counter >= _alert_check_interval:
                alert_counter = 0
                alert_mgr.check_all()
    except asyncio.CancelledError:
        pass

    # 优雅关闭
    logger.info("正在停止...")
    await execution_hub.stop_scheduler()
    await stop_trading_system()
    if auto_recovery:
        auto_recovery.stop()
    if metrics_server:
        metrics_server.shutdown()
        logger.info("  Prometheus 指标服务器已停止")
    # Langfuse 刷新 — 确保所有观测数据上报
    try:
        from src.langfuse_obs import shutdown as langfuse_shutdown
        langfuse_shutdown()
        logger.info("  Langfuse 观测层已关闭")
    except Exception:
        pass
    metrics.shutdown()
    history_store.close()
    shared_memory.close()
    for bot in bots:
        # 分开 try/except，确保 close 失败不影响 stop
        try:
            await bot.http_client.close()
        except Exception as e:
            logger.warning(f"关闭 http_client 失败 ({getattr(bot, 'bot_id', '?')}): {e}")
        try:
            await bot.stop_async()
        except Exception as e:
            logger.warning(f"停止 bot 失败 ({getattr(bot, 'bot_id', '?')}): {e}")
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
