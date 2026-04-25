#!/usr/bin/env python3
"""
ClawBot 多机器人版 v5.0 - Mixin 架构版
- MultiBot 类已拆分到 src/bot/ 目录（Mixin 架构）
- 本文件仅保留：Bot 配置、main() 启动逻辑、信号处理
"""
import os
import sys

# ── macOS 隐藏 Dock 图标: 防止 Python 进程在 Dock 栏显示和跳动 ──
if sys.platform == "darwin":
    try:
        import AppKit
        _NSApplicationActivationPolicyProhibited = 2
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            _NSApplicationActivationPolicyProhibited
        )
    except Exception:
        pass  # 非 macOS 或 AppKit 不可用时静默跳过

import logging
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── loguru 日志系统 (23.7k⭐) — 必须在所有业务 import 之前初始化 ──
from src.log_config import setup_logging
setup_logging(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    json_log_dir=str(Path(__file__).parent / "logs"),
)

import asyncio
from typing import Optional

from dotenv import load_dotenv
from telegram import BotCommand

# 加载配置
config_path = Path(__file__).parent / 'config' / '.env'
load_dotenv(config_path)

logger = logging.getLogger(__name__)

# 注: 第三方库降噪已由 src/log_config.py 统一管理 (_NOISY_LIBS)

# 导入重构后的 MultiBot 和全局共享组件
from src.bot.multi_bot import MultiBot
from src.bot.globals import (
    SILICONFLOW_KEYS, CLAUDE_KEY, ALLOWED_USER_IDS,
    history_store, chat_router, collab_orchestrator,
    metrics, health_checker, shared_memory,
    bot_registry, execution_hub,
    get_stock_quote, context_manager,
)
# 幻影导入修复: ibkr/portfolio/warmup 从实际定义模块导入
from src.broker_selector import ibkr
from src.invest_tools import portfolio, warmup as invest_warmup
from src.monitoring import AutoRecovery, start_metrics_server, AlertManager, AlertRule
from src.trading_system import (
    init_trading_system, start_trading_system, stop_trading_system,
    set_ai_team_callers,
)
from src.trading_journal import journal
from src.trading_memory_bridge import trading_memory_bridge
from src.litellm_router import free_pool, ROUTE_BALANCED
from src.context_manager import TieredContextManager
from src.routing import PriorityMessageQueue
from src.strategy_engine import create_default_engine
from src.social_tools import ABTestManager
from src.langfuse_obs import init_langfuse
from src.api.server import start_api_server, stop_api_server
from src.api.schemas import WSMessageType
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
    BotCommand("pricewatch", "降价提醒 add/list/remove"),
    # --- 补全缺失命令 ---
    BotCommand("accuracy", "AI预测准确率"),
    BotCommand("equity", "权益曲线"),
    BotCommand("targets", "盈利目标进度"),
    BotCommand("weekly", "综合周报"),
    BotCommand("bill", "话费水电费追踪"),
    BotCommand("xianyu_report", "闲鱼运营报表"),
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
        "token": os.getenv('FREE_LLM_TOKEN', ''),
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

    # === 启动前配置验证 ===
    from src.core.config_validator import validate_startup_config, log_validation_results
    _cfg_errors, _cfg_warnings = validate_startup_config()
    _cfg_ok = log_validation_results(_cfg_errors, _cfg_warnings)
    if not _cfg_ok:
        logger.critical("配置验证失败 — 请检查 config/.env 和环境变量后重试")
        # 不阻止启动但记录严重告警，让运维人员决定

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

    # 7. 自适应路由器已废弃 — LiteLLM Router 内置自适应路由，无需单独初始化
    logger.info("  自适应路由: LiteLLM Router 内置，无需单独初始化")

    # 7.5 初始化闲鱼监控（可选）
    try:
        from src.xianyu.goofish_monitor import init_goofish_monitor
        init_goofish_monitor()
        logger.info("  闲鱼监控已初始化")
    except Exception as e:
        logger.debug("  闲鱼监控初始化跳过: %s", e)

    # 7.6 初始化 CookieCloud 自动同步（可选）
    try:
        from src.xianyu.cookie_cloud import get_cookie_cloud_manager
        cc_manager = get_cookie_cloud_manager()
        if cc_manager.enabled:
            asyncio.ensure_future(cc_manager.run_sync_loop())
            logger.info("  CookieCloud 自动同步已启动 (间隔 %ds)", cc_manager._sync_interval)
        else:
            logger.info("  CookieCloud 未配置，跳过自动同步")
    except Exception as e:
        logger.debug("  CookieCloud 初始化跳过: %s", e)

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
        # 添加诊断信息：每个不健康 Bot 的上次心跳距今多久
        details = []
        for bid in unhealthy:
            s = status.get(bid, {})
            ago = s.get("last_heartbeat_ago", 0)
            errs = s.get("consecutive_errors", 0)
            detail = f"  • {bid}: {ago:.0f}s前"
            if errs > 0:
                detail += f" (连续{errs}次错误)"
            details.append(detail)
        msg = f"⚠️ [告警] Bot 心跳丢失: {', '.join(unhealthy)}"
        if details:
            msg += "\n" + "\n".join(details)
        return msg

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

    # 并发启动所有 bot — 相比顺序启动速度提升约 N 倍（N = bot 数量）
    async def _start_single_bot(config):
        """启动单个 Bot 并注册到全局注册表"""
        try:
            bot = MultiBot(config)
            result = await bot.run_async()
            if result:
                # 获取 bot 的 Telegram user_id，用于过滤 bot 互相回复
                try:
                    app = bot.app
                    if app:
                        bot_info = await app.bot.get_me()
                        chat_router.register_bot_user_id(bot_info.id)
                        logger.info(f"[{config['id']}] 注册 bot user_id: {bot_info.id}")
                except Exception as e:
                    logger.warning(f"[{config['id']}] 获取 bot user_id 失败: {e}")
                return bot
            return None
        except Exception as e:
            logger.error(f"[{config['id']}] 启动失败: {e}")
            return None

    # 并发启动全部 Bot
    start_results = await asyncio.gather(
        *[_start_single_bot(config) for config in BOTS],
        return_exceptions=True,
    )
    for i, result in enumerate(start_results):
        if isinstance(result, Exception):
            logger.error(f"[{BOTS[i]['id']}] 并发启动异常: {result}")
        elif result is not None:
            bots.append(result)
            bot_registry[result.bot_id] = result

    if not bots:
        logger.critical("所有 Bot 启动失败! 系统将在无 Bot 模式下运行 — 无法接收或发送消息")

    # 启动自动恢复
    auto_recovery = AutoRecovery(
        health_checker,
        max_restarts=int(os.environ.get("MAX_RESTARTS", "3")),
        restart_cooldown=float(os.environ.get("RESTART_COOLDOWN", "60.0")),
        # notify_func 在后面 _notify_telegram 定义后再设置
    )
    for bot in bots:
        auto_recovery.register_restart_func(bot.bot_id, bot.run_async, bot.stop_async)
        collab_orchestrator.register_api_caller(bot.bot_id, bot._call_api)
    auto_recovery.start()

    # 非阻塞 API Key 健康验证 (不阻塞启动)
    async def _background_key_validation():
        try:
            report = await free_pool.validate_keys(timeout=10.0)
            h, u = report["healthy"], report["unhealthy"]
            logger.info(f"  [Key验证] {h}/{h + u} providers 健康, {u} 异常, 耗时 {report['elapsed_s']}s")
            if u > 0:
                for prov, info in report.get("providers", {}).items():
                    if info.get("status") not in ("ok", "partial"):
                        logger.warning(f"  [Key验证] ❌ {prov}: {info.get('status')} — {info.get('error', '')[:80]}")
                    elif info.get("dead_indices"):
                        logger.warning(f"  [Key验证] ⚠️ {prov}: dead keys #{info['dead_indices']}")
        except Exception as e:
            logger.warning(f"  [Key验证] 启动验证跳过: {e}")
    # 辅助: 为 fire-and-forget 任务统一添加异常回调
    def _task_done_cb(label: str):
        def _cb(t):
            if not t.cancelled() and t.exception():
                logger.critical("[%s] 后台任务失败: %s", label, t.exception())
        return _cb

    asyncio.create_task(_background_key_validation()).add_done_callback(
        _task_done_cb("KeyValidation")
    )

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

    # 初始化主动智能引擎 (搬运自 BasedHardware/omi 17k⭐ 的 proactive_notification 三步管道)
    try:
        from src.core.proactive_engine import get_proactive_engine, setup_proactive_listeners
        proactive = get_proactive_engine()
        await setup_proactive_listeners(proactive)
        logger.info("  主动智能引擎已启动 (Gate→Generate→Critic 三步管道)")
    except Exception as e:
        logger.info(f"  主动智能引擎初始化跳过: {e}")

    # 启动自选股异动监控（搬运交易类产品标配告警模式）
    try:
        from src.watchlist_monitor import get_watchlist_monitor
        _wm = get_watchlist_monitor()
        await _wm.start()
    except Exception as e:
        logger.info(f"  自选股异动监控跳过: {e}")

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

    # === 启动内控 API 服务器 (搬运 freqtrade RPC + Open WebUI 模式) ===
    api_port = int(os.environ.get("API_PORT", "18790"))
    try:
        api_server = start_api_server(port=api_port)
        logger.info(f"  内控 API 服务器已启动: http://127.0.0.1:{api_port}/api/docs")
    except Exception as e:
        api_server = None
        logger.warning(f"  内控 API 服务器启动失败（非致命）: {e}")

    # === OMEGA v2.0 核心模块初始化 ===
    _omega_brain = None
    _omega_gateway = None
    try:
        from src.core.event_bus import get_event_bus
        _omega_event_bus = get_event_bus()
        logger.info("  OMEGA 事件总线已初始化")
    except Exception as e:
        logger.info(f"  OMEGA 事件总线初始化跳过: {e}")

    # === 统一通知系统 (搬运 Apprise 16.1k⭐) — 订阅 EventBus 事件 ===
    try:
        from src.notifications import get_notification_manager
        _notification_manager = get_notification_manager()
        await _notification_manager.register_event_handlers()
        logger.info("  统一通知系统已初始化 (EventBus 事件订阅已注册)")
    except Exception as e:
        logger.info(f"  统一通知系统初始化跳过: {e}")

    try:
        from src.core.brain import init_brain
        _omega_brain = init_brain()
        logger.info("  OMEGA 核心编排器 (Brain) 已初始化")
    except Exception as e:
        logger.info(f"  OMEGA Brain 初始化跳过: {e}")

    try:
        from src.core.cost_control import get_cost_controller
        _omega_cost = get_cost_controller()
        logger.info(f"  OMEGA 成本控制已初始化 (日预算 ${_omega_cost._daily_budget:.2f})")
    except Exception as e:
        logger.info(f"  OMEGA 成本控制初始化跳过: {e}")

    try:
        from src.core.security import get_security_gate
        _omega_security = get_security_gate()
        logger.info(f"  OMEGA 安全门控已初始化 (管理员: {len(_omega_security._admin_ids)})")
    except Exception as e:
        logger.info(f"  OMEGA 安全门控初始化跳过: {e}")

    # 协同管道 — 跨模块飞轮效应（借鉴 n8n 数据管道模式）
    try:
        from src.core.synergy_pipelines import init_synergy_pipelines
        _omega_synergy = await init_synergy_pipelines()
        logger.info(f"  OMEGA 协同管道已注册 ({_omega_synergy.get_stats()['active_pipelines']} 条管道)")
    except Exception as e:
        logger.info(f"  OMEGA 协同管道初始化跳过: {e}")

    _stop_gateway_fn = None
    try:
        from src.gateway.telegram_gateway import start_gateway, stop_gateway as _stop_gw
        _stop_gateway_fn = _stop_gw
        _omega_gateway = await start_gateway()
        if _omega_gateway:
            logger.info("  OMEGA Telegram Gateway Bot 已启动")
        else:
            logger.info("  OMEGA Gateway Bot 未配置 (设置 OMEGA_GATEWAY_BOT_TOKEN 启用)")
    except Exception as e:
        logger.info(f"  OMEGA Gateway Bot 初始化跳过: {e}")

    # === 进化引擎初始化 (搬运 GitHub Trending 扫描模式) ===
    _evolution_engine = None
    try:
        from src.evolution.engine import EvolutionEngine
        _evolution_engine = EvolutionEngine()
        logger.info("  进化引擎已就绪（可通过 Manager UI 触发扫描）")
    except Exception as e:
        logger.info(f"  进化引擎初始化跳过: {e}")

    # === 社交自动驾驶 — 检查是否需要自动恢复 (搬运 APScheduler 模式) ===
    try:
        from src.social_scheduler import SocialAutopilot, _load_state as _load_ap_state
        _autopilot = SocialAutopilot()
        _ap_state = _load_ap_state()
        if _ap_state.get("enabled", False):
            _autopilot.start()
            logger.info("  社交自动驾驶已恢复运行（上次关闭前为启用状态）")
        else:
            logger.info("  社交自动驾驶待命（可通过 Manager UI 启动）")
    except Exception as e:
        logger.info(f"  社交自动驾驶初始化跳过: {e}")

    logger.info("=" * 60)
    logger.info(f"成功启动 {len(bots)} 个 Bot:")
    for bot in bots:
        logger.info(f"  {bot.emoji} {bot.name} - {bot.role} (@{bot.username})")
    logger.info("=" * 60)

    # 后台预热 yfinance
    _t = asyncio.create_task(invest_warmup())
    _t.add_done_callback(_task_done_cb("InvestWarmup"))

    # 连接 IBKR Paper Trading
    async def _connect_ibkr():
        ok = await ibkr.connect()
        if ok:
            logger.info("[IBKR] Paper Trading 连接成功 (预算$%.0f)" % ibkr.budget)
        else:
            logger.warning("[IBKR] 连接失败，IBKR命令不可用（IB Gateway是否运行？）")
    _t = asyncio.create_task(_connect_ibkr())
    _t.add_done_callback(_task_done_cb("IBKR_Connect"))

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

            # Push to WebSocket live event feed alongside Telegram
            try:
                from src.api.routers.ws import push_event
                if "交易执行" in text or "交易已成交" in text:
                    push_event(WSMessageType.TRADE_EXECUTED, {"message": text})
                    # EventBus: 交易执行事件 → 协同管道自动生成社媒草稿
                    try:
                        from src.core.event_bus import get_event_bus, EventType as EvtType
                        direction = "BUY" if "买入" in text else "SELL" if "卖出" in text else "HOLD"
                        _t = asyncio.create_task(get_event_bus().publish(
                            EvtType.TRADE_EXECUTED,
                            {"signal": direction, "reason": text[:100], "message": text},
                            source="trading_system",
                        ))
                        _t.add_done_callback(_task_done_cb("EventBus_TradeExec"))
                    except Exception as e:
                        logger.debug("EventBus publish failed (TradeExec): %s", e, exc_info=True)
                    # 旧 Synergy 兼容（逐步迁移到 EventBus）
                    try:
                        from src.synergy import get_synergy
                        direction = "BUY" if "买入" in text else "SELL" if "卖出" in text else "HOLD"
                        _t = asyncio.create_task(get_synergy().on_trade_signal({
                            "signal": direction, "reason": text[:100], "score": 80, "symbol": "",
                        }))
                        _t.add_done_callback(_task_done_cb("Synergy_TradeSignal"))
                    except Exception as e:
                        logger.debug("EventBus publish failed (Synergy_TradeSignal): %s", e, exc_info=True)
                elif "止损" in text or "止盈" in text or "风控" in text:
                    push_event(WSMessageType.RISK_ALERT, {"message": text})
                    # EventBus: 风控事件
                    try:
                        from src.core.event_bus import get_event_bus, EventType as EvtType
                        _t = asyncio.create_task(get_event_bus().publish(
                            EvtType.RISK_ALERT,
                            {"message": text},
                            source="trading_system",
                        ))
                        _t.add_done_callback(_task_done_cb("EventBus_RiskAlert"))
                    except Exception as e:
                        logger.debug("EventBus publish failed (RiskAlert): %s", e, exc_info=True)
                elif "信号" in text or "signal" in text.lower():
                    push_event(WSMessageType.TRADE_SIGNAL, {"message": text})
                    # EventBus: 交易信号
                    try:
                        from src.core.event_bus import get_event_bus, EventType as EvtType
                        _t = asyncio.create_task(get_event_bus().publish(
                            EvtType.TRADE_SIGNAL,
                            {"message": text},
                            source="trading_system",
                        ))
                        _t.add_done_callback(_task_done_cb("EventBus_TradeSignal"))
                    except Exception as e:
                        logger.debug("EventBus publish failed (TradeSignal): %s", e, exc_info=True)
                elif "告警" in text or "错误" in text or "失败" in text:
                    push_event(WSMessageType.BOT_ERROR, {"message": text})
            except Exception as e:
                logger.debug("EventBus publish failed (outer): %s", e, exc_info=True)
        except Exception as e:
            logger.error("[TradingSystem] 通知发送失败: %s", e)

        # 微信同步推送 — 日报/交易等通知同步发送到微信
        try:
            from src.wechat_bridge import send_to_wechat
            _t = asyncio.create_task(send_to_wechat(text))
            _t.add_done_callback(_task_done_cb("WeChat_Notify"))
        except Exception as e:
            logger.warning("[WeChat] 同步推送失败: %s", e)

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
        # 微信镜像推送 — 定时推送（晨报/周报/闲鱼/预算等）也要到达微信
        try:
            from src.wechat_bridge import send_to_wechat
            _t = asyncio.create_task(send_to_wechat(text))
            _t.add_done_callback(_task_done_cb("WeChat_Private"))
        except Exception as e:
            logger.warning("[WeChat] 私聊镜像推送失败: %s", e)

    # 给 AutoRecovery 设置通知函数 — 崩溃/恢复时主动推送 Telegram 通知
    if auto_recovery and bots:
        auto_recovery._notify_func = _notify_batched

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

    _t = asyncio.create_task(start_trading_system())
    _t.add_done_callback(_task_done_cb("TradingSystem"))
    logger.info("  - 自动交易系统已初始化 (风控/监控/管道/调度)")

    await execution_hub.start_scheduler(_notify_telegram, _notify_private_telegram)
    logger.info("  - 执行场景调度器已启动")

    # 注册告警回调 -> Telegram 通知
    def _on_alert(rule_name, message):
        _t = asyncio.create_task(_notify_telegram(message))
        _t.add_done_callback(_task_done_cb("AlertNotify"))
    alert_mgr.on_alert(_on_alert)

    # 注册告警回调 -> WebSocket 实时推送
    from src.api.routers.ws import push_event
    alert_mgr.on_alert(lambda name, msg: push_event(WSMessageType.RISK_ALERT, {"rule": name, "message": msg}))

    _heartbeat_interval = int(os.environ.get("HEARTBEAT_INTERVAL", "60"))
    _cleanup_interval = int(os.environ.get("CLEANUP_INTERVAL", "60"))
    _cleanup_max_age = float(os.environ.get("CLEANUP_MAX_AGE", "3600.0"))
    _alert_check_interval = int(os.environ.get("ALERT_CHECK_INTERVAL", "30"))
    _evolution_interval = int(os.environ.get("EVOLUTION_SCAN_INTERVAL", "86400"))  # 24h
    _proactive_interval = int(os.environ.get("PROACTIVE_CHECK_INTERVAL", "1800"))  # 30分钟

    # 笔笔省自动领券 — 每日 08:30 执行（使用时间点比较，不漂移）
    _coupon_hour = int(os.environ.get("COUPON_CLAIM_HOUR", "8"))
    _coupon_minute = int(os.environ.get("COUPON_CLAIM_MINUTE", "30"))
    _coupon_last_date = ""  # 记录上次执行日期，避免同一天重复执行

    try:
        cleanup_counter = 0
        heartbeat_counter = 0
        alert_counter = 0
        evolution_counter = 0
        proactive_counter = 0
        while not stop_event.is_set():
            await asyncio.sleep(1)
            cleanup_counter += 1
            heartbeat_counter += 1
            alert_counter += 1
            evolution_counter += 1
            proactive_counter += 1
            if heartbeat_counter >= _heartbeat_interval:
                heartbeat_counter = 0
                for bot in bots:
                    # 只要 Bot 实例存在就发心跳，不依赖 updater.running
                    # 避免网络波动导致所有 Bot 同时丢失心跳
                    if bot.app:
                        health_checker.heartbeat(bot.bot_id)
            if cleanup_counter >= _cleanup_interval:
                cleanup_counter = 0
                collab_orchestrator.cleanup_old_tasks(max_age=_cleanup_max_age)
                chat_router.cleanup_stale_sessions(max_age_seconds=1800)
                try:
                    from src.core.brain import get_brain
                    get_brain().cleanup_pending_callbacks(max_age_seconds=600)
                except Exception as e:
                    logger.debug("清理过期回调时异常(可忽略): %s", e)
            if alert_counter >= _alert_check_interval:
                alert_counter = 0
                alert_mgr.check_all()
            # 进化引擎定时扫描（默认每24小时）
            if _evolution_engine and evolution_counter >= _evolution_interval:
                evolution_counter = 0
                async def _run_evolution_scan():
                    try:
                        proposals = await _evolution_engine.daily_scan()
                        if proposals:
                            logger.info("[Evolution] 发现 %d 个进化提案", len(proposals))
                    except Exception as e:
                        logger.debug("[Evolution] 扫描异常: %s", e)
                asyncio.create_task(_run_evolution_scan()).add_done_callback(
                    _task_done_cb("EvolutionScan")
                )
            # 主动智能定时检查（默认每30分钟）
            if proactive_counter >= _proactive_interval:
                proactive_counter = 0
                try:
                    from src.core.proactive_engine import get_proactive_engine, periodic_proactive_check
                    _pe = get_proactive_engine()
                    asyncio.create_task(periodic_proactive_check(_pe)).add_done_callback(
                        _task_done_cb("ProactiveCheck")
                    )
                except Exception as e:
                    logger.debug(f"[Proactive] 定时检查启动失败: {e}")

            # 笔笔省每日自动领券（每天 08:30，优先用已保存 token，省略 mitmproxy 流程）
            try:
                from src.utils import now_et
                _now = now_et()
                _today_str = _now.strftime("%Y-%m-%d")
                if (_now.hour == _coupon_hour and _now.minute == _coupon_minute
                        and _today_str != _coupon_last_date):
                    _coupon_last_date = _today_str

                    async def _run_coupon_claim():
                        try:
                            from src.execution.wechat_coupon import claim_with_saved_token, auto_claim_coupon
                            # 优先用已保存的 token（轻量路径，不需要 mitmproxy）
                            result = await claim_with_saved_token()
                            if "过期" in result or "没有" in result:
                                # token 不可用，走完整 mitmproxy 流程
                                logger.info("[笔笔省] 保存的 token 不可用，尝试完整领券流程")
                                result = await auto_claim_coupon()
                            logger.info("[笔笔省] 自动领券结果: %s", result)
                            # 通过 Telegram 通知用户结果
                            try:
                                await _notify_private_telegram(f"🎫 笔笔省每日领券\n{result}")
                            except Exception as e:
                                logger.debug("笔笔省领券通知发送失败(可忽略): %s", e)
                        except ImportError:
                            logger.debug("[笔笔省] 领券模块未就绪")
                        except Exception as e:
                            logger.warning("[笔笔省] 自动领券异常: %s", e)

                    asyncio.create_task(_run_coupon_claim()).add_done_callback(
                        _task_done_cb("CouponClaim")
                    )
            except Exception as e:
                logger.debug("定时任务调度异常(可忽略): %s", e)
    except asyncio.CancelledError:
        pass

    # 优雅关闭（带超时保护，防止进程卡死）
    logger.info("正在停止...")

    # ── 第 0 步: 立即停止所有 Bot 接收新消息 ──
    # 必须最先执行！否则关闭资源期间 Bot 仍在处理新消息，访问已关闭资源导致异常
    for bot in bots:
        try:
            await bot.stop_async()
            logger.info("  Bot %s 已停止接收消息", getattr(bot, 'bot_id', '?'))
        except Exception as e:
            logger.warning("停止 Bot polling 失败 (%s): %s", getattr(bot, 'bot_id', '?'), e)

    # ── 第 1 步: 关机通知 (VPS + Telegram 管理员) ──
    try:
        import subprocess
        vps_host = os.getenv("DEPLOY_VPS_HOST", "")
        vps_user = os.getenv("DEPLOY_VPS_USER", "openclaw")
        if not vps_host:
            logger.debug("  DEPLOY_VPS_HOST 未设置，跳过 VPS 关机通知")
            raise ValueError("DEPLOY_VPS_HOST 未配置")
        # 1. 通知 VPS: 写入 shutdown 标记文件，VPS failover 可秒级切换
        await asyncio.to_thread(
            subprocess.run,
            ["ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=accept-new",
             f"{vps_user}@{vps_host}",
             "touch /opt/openclaw/data/primary_shutdown"],
            timeout=5, capture_output=True,
        )
        logger.info("  已通知 VPS 主节点关机")
    except Exception as e:
        logger.debug("  VPS 关机通知失败 (非阻塞): %s", e)

    try:
        # 2. 通知 Telegram 管理员
        admin_ids = os.getenv("ALLOWED_USER_IDS", "")
        if bots and admin_ids:
            first_admin = int(admin_ids.split(",")[0].strip())
            await bots[0].app.bot.send_message(
                chat_id=first_admin,
                text="🔄 系统正在关机维护，服务将短暂中断。",
            )
            logger.info("  已通知管理员关机")
    except Exception as e:
        logger.debug("  管理员关机通知失败 (非阻塞): %s", e)

    # 停止自选股异动监控
    try:
        from src.watchlist_monitor import get_watchlist_monitor
        await get_watchlist_monitor().stop()
    except Exception as e:
        logger.debug("关闭自选股监控时异常(可忽略): %s", e)
    # 刷新通知批量合并器 — 防止待发通知丢失
    try:
        await _notify_batcher.flush()
        logger.info("  通知批量合并器已刷新")
    except Exception as e:
        logger.warning("  通知批量合并器刷新失败: %s", e)
    # 停止 OMEGA Gateway Bot
    if _omega_gateway and _stop_gateway_fn:
        try:
            await _stop_gateway_fn()
            logger.info("  OMEGA Gateway Bot 已停止")
        except Exception as e:
            logger.warning(f"  OMEGA Gateway 停止失败: {e}")
    # 停止 OMEGA 执行引擎
    try:
        from src.core.executor import get_executor
        await get_executor().close()
    except Exception as e:
        logger.debug("关闭OMEGA执行引擎时异常(可忽略): %s", e)
    await execution_hub.stop_scheduler()
    await stop_trading_system()
    # 停止内控 API 服务器
    try:
        stop_api_server()
        logger.info("  内控 API 服务器已停止")
    except Exception as e:
        logger.debug("关闭内控API服务器时异常(可忽略): %s", e)
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
    except Exception as e:
        logger.debug("关闭Langfuse观测层时异常(可忽略): %s", e)
    metrics.shutdown()
    history_store.close()
    shared_memory.close()
    # 关闭 LLM 缓存（sqlite3 缓存需要显式 close 才能刷盘）
    try:
        from src.litellm_router import _fallback_cache
        if _fallback_cache:
            _fallback_cache.close()
            logger.info("  LLM 缓存已关闭")
    except Exception as e:
        logger.debug("关闭LLM缓存时异常(可忽略): %s", e)
    # 关闭 httpx 长生命周期客户端（防止 TCP 连接泄漏）
    try:
        from src.xianyu.goofish_monitor import _monitor as _gm
        if _gm and hasattr(_gm, 'close'):
            await _gm.close()
            logger.info("  GoofishMonitor httpx 客户端已关闭")
    except Exception as e:
        logger.debug("GoofishMonitor 关闭跳过: %s", e)
    try:
        from src.execution.social.media_crawler_bridge import MediaCrawlerBridge
        if hasattr(MediaCrawlerBridge, '_instance') and MediaCrawlerBridge._instance:
            await MediaCrawlerBridge._instance.close()
            logger.info("  MediaCrawlerBridge httpx 客户端已关闭")
    except Exception as e:
        logger.debug("MediaCrawlerBridge 关闭跳过: %s", e)
    # 关闭社交自动化的 headless Chrome 浏览器
    try:
        import subprocess as _sp
        _sp.run(["pkill", "-f", "remote-debugging-port=19222"], capture_output=True, timeout=5)
        logger.info("  社交浏览器已终止")
    except Exception:
        pass
    for bot in bots:
        # Bot 已在关闭序列开头停止 polling，这里只关闭 HTTP 连接
        try:
            await bot.http_client.close()
        except Exception as e:
            logger.warning(f"关闭 http_client 失败 ({getattr(bot, 'bot_id', '?')}): {e}")
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
    except Exception as e:
        # 捕获所有未处理的异常，记录到日志后让 LaunchAgent 重启进程
        logger.critical(f"主进程意外崩溃，LaunchAgent 将自动重启: {type(e).__name__}: {e}")
        import traceback
        logger.critical(traceback.format_exc())
        # 退出码 1 让 LaunchAgent 知道是异常退出需要重启
        import sys
        sys.exit(1)
