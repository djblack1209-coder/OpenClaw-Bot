"""微信消息处理 API Router。

接收云端 wechat_receiver 转发的微信消息。
支持编号命令快捷操作 + 中文自然语言 + LLM 对话。
"""

import logging
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wechat")


# ── 微信对话记忆缓存 ──
# 每个用户保留最近 10 条消息，30 分钟无活动自动过期
_wechat_memory: dict[str, dict] = {}
_wechat_pending_actions: dict[str, dict] = {}
_MEMORY_TTL = 1800  # 30 分钟
_PENDING_TTL = 600  # 10 分钟
_MAX_MESSAGES = 10


def _get_user_history(user_id: str) -> list[dict]:
    """获取用户的对话历史，过期则清空。"""
    entry = _wechat_memory.get(user_id)
    if not entry:
        return []
    if time.time() - entry["last_active"] > _MEMORY_TTL:
        del _wechat_memory[user_id]
        return []
    return list(entry["messages"])


def _add_to_history(user_id: str, role: str, content: str) -> None:
    """追加一条消息到用户历史。"""
    if user_id not in _wechat_memory:
        _wechat_memory[user_id] = {"messages": [], "last_active": time.time()}
    entry = _wechat_memory[user_id]
    entry["messages"].append({"role": role, "content": content})
    entry["last_active"] = time.time()
    # 保留最近 N 条
    if len(entry["messages"]) > _MAX_MESSAGES:
        entry["messages"] = entry["messages"][-_MAX_MESSAGES:]


def _set_pending_action(user_id: str, action: str) -> None:
    """记录微信下一条普通文字要接着完成的操作。"""
    if not user_id:
        return
    _wechat_pending_actions[user_id] = {"action": action, "last_active": time.time()}


def _get_pending_action(user_id: str) -> str:
    """读取微信两步式操作，过期自动清理。"""
    entry = _wechat_pending_actions.get(user_id)
    if not entry:
        return ""
    if time.time() - float(entry.get("last_active", 0)) > _PENDING_TTL:
        _wechat_pending_actions.pop(user_id, None)
        return ""
    return str(entry.get("action") or "")


def _clear_pending_action(user_id: str) -> None:
    """清理微信两步式操作状态。"""
    _wechat_pending_actions.pop(user_id, None)


class WeChatIncomingRequest(BaseModel):
    """微信云端转发的消息体。"""

    from_user: str = Field(default="", max_length=256)
    text: str = Field(default="", max_length=4000)


class WeChatIncomingResponse(BaseModel):
    """返回给微信转发器的回复体。"""

    reply: str


# ── 编号命令映射表 ──
# 格式: {编号: (描述, 是否需要参数, 处理函数名)}
# 处理函数在 _execute_numbered_cmd 中统一调度
NUMBERED_COMMANDS: dict[int, tuple[str, bool, str]] = {
    # 🤖 100-109: AI & 基础功能
    100: ("帮助菜单", False, "cmd_help"),
    101: ("清空对话", False, "cmd_clear"),
    102: ("系统状态", False, "cmd_status"),
    103: ("AI 画图", True, "cmd_draw"),
    104: ("科技早报", False, "cmd_news"),
    105: ("文字转语音", True, "cmd_tts"),
    106: ("生成二维码", True, "cmd_qr"),
    # 📈 200-229: 投资分析
    200: ("行情查询", True, "cmd_quote"),
    201: ("市场概览", False, "cmd_market"),
    202: ("投资组合", False, "cmd_portfolio"),
    203: ("技术分析", True, "cmd_ta"),
    204: ("交易信号", True, "cmd_signal"),
    205: ("全市场扫描", False, "cmd_scan"),
    206: ("K线图", True, "cmd_chart"),
    207: ("仓位计算器", True, "cmd_calc"),
    208: ("交易记录", False, "cmd_trades"),
    209: ("投资绩效", False, "cmd_performance"),
    210: ("AI 交易复盘", False, "cmd_review"),
    211: ("交易日志", False, "cmd_journal"),
    212: ("自选股", False, "cmd_watchlist"),
    213: ("风控状态", False, "cmd_risk"),
    214: ("持仓监控", False, "cmd_monitor"),
    215: ("交易系统状态", False, "cmd_tradingsystem"),
    216: ("回测", True, "cmd_backtest"),
    217: ("AI 投资分析会", True, "cmd_invest"),
    218: ("权益曲线", False, "cmd_equity"),
    219: ("盈利目标", False, "cmd_targets"),
    220: ("预测准确率", False, "cmd_accuracy"),
    221: ("综合周报", False, "cmd_weekly"),
    # 🏦 230-239: IBKR 实盘
    230: ("实盘买入", True, "cmd_ibuy"),
    231: ("实盘卖出", True, "cmd_isell"),
    232: ("实盘持仓", False, "cmd_ipositions"),
    233: ("实盘挂单", False, "cmd_iorders"),
    234: ("实盘账户", False, "cmd_iaccount"),
    235: ("取消订单", True, "cmd_icancel"),
    # 📱 300-319: 社媒
    300: ("热点发文", False, "cmd_hot"),
    301: ("双平台发文", True, "cmd_post"),
    302: ("发 X 推文", True, "cmd_xpost"),
    303: ("发小红书", True, "cmd_xhspost"),
    304: ("发文计划", False, "cmd_social_plan"),
    305: ("社媒人设", False, "cmd_social_persona"),
    306: ("题材研究", True, "cmd_topic"),
    307: ("社媒报告", False, "cmd_social_report"),
    308: ("发文日历", False, "cmd_social_calendar"),
    # 🛒 400-409: 电商
    404: ("降价监控", True, "cmd_pricewatch"),
    405: ("折扣搜索", True, "cmd_deals"),
    407: ("全球情报", False, "cmd_intel"),
    408: ("黑五折扣", True, "cmd_deals"),  # 用法: "408 VPS" → 等效于 /deals bf VPS
    # 🏠 500-509: 生活
    500: ("执行简报", False, "cmd_brief"),
    501: ("话费账单", False, "cmd_bill"),
    502: ("数据导出", False, "cmd_export"),
    503: ("自动化工作台", False, "cmd_ops"),
    # ⚙️ 600-609: 系统
    600: ("记忆管理", False, "cmd_memory"),
    601: ("偏好设置", False, "cmd_settings"),
    602: ("当前模型", False, "cmd_model"),
    603: ("API 池状态", False, "cmd_pool"),
    604: ("性能指标", False, "cmd_perf"),
    605: ("成本配额", False, "cmd_cost"),
    606: ("运行配置", False, "cmd_config"),
    # 🧭 700-708: 每日简报
    700: ("每日简报菜单", False, "cmd_intel_menu"),
    701: ("简报状态", False, "cmd_intel_status"),
    702: ("市场资金", False, "cmd_intel_market"),
    703: ("AI科技", False, "cmd_intel_ai"),
    704: ("天气预警", False, "cmd_intel_weather"),
    705: ("推送时间", False, "cmd_intel_schedule"),
    706: ("添加追踪", True, "cmd_intel_custom"),
    707: ("简报帮助", False, "cmd_intel_help"),
    708: ("暂停简报", False, "cmd_intel_pause"),
}

_INTEL_NUMBERED_FUNC_TO_NUM: dict[str, int] = {
    "cmd_intel_menu": 700,
    "cmd_intel_status": 701,
    "cmd_intel_market": 702,
    "cmd_intel_ai": 703,
    "cmd_intel_weather": 704,
    "cmd_intel_schedule": 705,
    "cmd_intel_custom": 706,
    "cmd_intel_help": 707,
    "cmd_intel_pause": 708,
}

_INTEL_TEXT_SHORTCUTS: dict[str, tuple[int, str]] = {
    "今日简报": (700, ""),
    "看今日简报": (700, ""),
    "每日简报": (700, ""),
    "我的订阅": (701, ""),
    "订阅状态": (701, ""),
    "简报状态": (701, ""),
    "市场资金": (702, ""),
    "AI科技": (703, ""),
    "AI 科技": (703, ""),
    "天气预警": (704, ""),
    "推送时间": (705, ""),
    "设置时间": (705, ""),
    "添加追踪": (706, ""),
    "简报帮助": (707, ""),
    "暂停简报": (708, ""),
    "暂停": (708, ""),
}

_INTEL_TEXT_PREFIX_SHORTCUTS: tuple[tuple[str, int], ...] = (
    ("推送时间", 705),
    ("设置时间", 705),
    ("添加追踪", 706),
    ("追踪", 706),
)


def _intel_brief_db_path() -> Path:
    """返回每日简报数据库路径，优先使用生产环境配置。"""
    configured = os.environ.get("INTEL_BRIEF_DB_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "data" / "intel_brief.db"


def _build_welcome_message() -> str:
    """生成微信端完整欢迎消息（含编号命令快查表）。"""
    return (
        "🐾 你好！我是 OpenClaw AI 助手\n"
        "\n"
        "发数字编号即可快速操作：\n"
        "\n"
        "📌 常用功能\n"
        "100 帮助  |  104 早报\n"
        "200 查股价  |  201 市场概览\n"
        "202 组合  |  217 AI投资会\n"
        "300 热点发文  |  307 社媒报告\n"
        "700 每日简报  |  706 英伟达\n"
        "\n"
        "💡 带参数用法\n"
        "发 \"200 AAPL\" → 查苹果股价\n"
        "发 \"103 一只猫\" → AI 画图\n"
        "发 \"217 半导体\" → AI 投资分析会\n"
        "发 \"206 TSLA\" → K线图\n"
        "发 \"706 英伟达\" → 追踪英伟达相关新闻\n"
        "\n"
        "📈 投资: 200-221 | 🏦 实盘: 230-235\n"
        "📱 社媒: 300-308 | 🔎 发现: 404-408\n"
        "🏠 生活: 500-503 | ⚙️ 系统: 600-606\n"
        "🧭 每日简报: 700-708\n"
        "\n"
        "也可以直接说中文：\n"
        "  · \"特斯拉多少钱\"\n"
        "  · \"帮我找便宜的 AirPods\"\n"
        "  · \"今日简报\"\n"
        "\n"
        "发 100 查看完整功能列表"
    )


def _build_full_help() -> str:
    """生成完整编号命令列表。"""
    lines = ["📋 OpenClaw 完整功能列表\n"]
    current_group = ""
    group_headers = {
        1: "🤖 AI & 基础 (100-109)",
        2: "📈 投资分析 (200-221)",
        23: "🏦 IBKR 实盘 (230-235)",
        3: "📱 社媒发文 (300-308)",
        4: "🔎 发现与折扣 (404-408)",
        5: "🏠 生活助手 (500-503)",
        6: "⚙️ 系统设置 (600-606)",
        7: "🧭 每日简报 (700-708)",
    }

    for num, (desc, needs_arg, _) in sorted(NUMBERED_COMMANDS.items()):
        group = num // 100
        # IBKR 子组特殊处理
        group_key = 23 if 230 <= num <= 239 else group
        header = group_headers.get(group_key, "")
        if header != current_group:
            current_group = header
            lines.append(f"\n{header}")
        arg_hint = " [参数]" if needs_arg else ""
        lines.append(f"  {num} — {desc}{arg_hint}")

    lines.append("\n💡 带 [参数] 的命令: 发 \"编号 内容\"")
    lines.append("如: \"200 AAPL\" \"103 一只猫\"")
    return "\n".join(lines)


def _strip_g4f_ads(text: str) -> str:
    """清理 g4f 回复中的广告和思考标签。"""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\n*Need proxies cheaper than the market\?\s*\n*https?://op\.wtf\s*", "", cleaned)
    cleaned = re.sub(r"\n*Generated by .*?SUSPENDED.*?\n*", "", cleaned)
    return cleaned.strip()


def _parse_numbered_cmd(text: str) -> tuple[int | None, str]:
    """解析编号命令，返回 (编号, 参数)。

    支持格式:
    - "200"        → (200, "")
    - "200 AAPL"   → (200, "AAPL")
    - "103 一只猫"  → (103, "一只猫")
    """
    match = re.match(r"^(\d{3})\s*(.*)", text.strip())
    if match:
        num = int(match.group(1))
        arg = match.group(2).strip()
        if num in NUMBERED_COMMANDS:
            return num, arg
    return None, text


def _parse_intel_text_shortcut(text: str) -> tuple[int, str] | None:
    """解析微信每日简报中文快捷词，让小白用户不用记数字。"""
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return None
    direct = _INTEL_TEXT_SHORTCUTS.get(cleaned)
    if direct:
        return direct
    for prefix, number in _INTEL_TEXT_PREFIX_SHORTCUTS:
        if cleaned.startswith(f"{prefix} "):
            arg = cleaned[len(prefix) :].strip()
            return number, arg
    return None


async def _self_call_api(path: str, timeout: float = 10.0) -> dict | list | str:
    """调用本地 FastAPI 端点获取数据（self-call 模式）。

    所有编号命令通过 HTTP self-call 调用已验证的 API 路由层，
    避免直接引用可能不存在的 RPC 方法。
    """
    import os

    import httpx

    port = int(os.environ.get("API_PORT", "18790"))
    token = os.environ.get("OPENCLAW_API_TOKEN", "")
    headers = {"X-API-Token": token} if token else {}
    url = f"http://127.0.0.1:{port}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        logger.warning("[微信] API self-call 失败 %s: %s", path, e)
        return {"error": str(e)}


# ── 编号命令到 API 路径的映射 ──
# 只映射可以通过 GET 请求获取数据的命令
# 参考 FastAPI APIRouter path operation 文档（2026-07-02 复核）：微信编号入口只调用已存在的只读 GET 路由，写操作必须显式拒绝或转人工确认。
_CMD_API_MAP: dict[str, tuple[str, str]] = {
    # AI / 基础工具
    "cmd_draw": ("/api/v1/omega/tools/generate-image?prompt={arg}", "AI 画图"),
    # 投资类
    "cmd_quote": ("/api/v1/trading/kline?symbol={arg}&interval=1d&limit=1", "行情查询"),
    "cmd_market": ("/api/v1/monitor/finance/indices", "市场概览"),
    "cmd_portfolio": ("/api/v1/trading/portfolio-summary", "投资组合"),
    "cmd_signal": ("/api/v1/trading/signals", "交易信号"),
    "cmd_trades": ("/api/v1/trading/journal?limit=10", "交易记录"),
    "cmd_watchlist": ("/api/v1/trading/watchlist", "自选股"),
    "cmd_ipositions": ("/api/v1/trading/positions", "实盘持仓"),
    "cmd_monitor": ("/api/v1/trading/positions", "持仓监控"),
    "cmd_iaccount": ("/api/v1/trading/pnl", "IBKR 账户"),
    "cmd_tradingsystem": ("/api/v1/trading/system", "交易系统"),
    "cmd_performance": ("/api/v1/trading/pnl", "投资绩效"),
    "cmd_iorders": ("/api/v1/trading/positions", "实盘挂单"),
    "cmd_scan": ("/api/v1/monitor/extended", "全市场扫描"),
    "cmd_chart": ("/api/v1/trading/kline?symbol={arg}&interval=1d&limit=60", "K线图"),
    "cmd_backtest": ("/api/v1/omega/investment/backtest?symbol={arg}", "回测"),
    "cmd_invest": ("/api/v1/omega/investment/analyze?symbol={arg}", "AI 投资分析会"),
    "cmd_equity": ("/api/v1/trading/pnl", "权益曲线"),
    "cmd_targets": ("/api/v1/trading/pnl", "盈利目标"),
    "cmd_accuracy": ("/api/v1/trading/signals", "预测准确率"),
    "cmd_weekly": ("/api/v1/system/daily-brief", "综合周报"),
    "cmd_review": ("/api/v1/trading/journal?limit=20", "AI 交易复盘"),
    "cmd_journal": ("/api/v1/trading/journal?limit=20", "交易日志"),
    # 系统类
    "cmd_status": ("/api/v1/system/status", "系统状态"),
    "cmd_news": ("/api/v1/system/daily-brief", "科技早报"),
    "cmd_pool": ("/api/v1/pool/stats", "API 池状态"),
    "cmd_memory": ("/api/v1/memory/stats", "记忆管理"),
    "cmd_cost": ("/api/v1/omega/cost", "成本配额"),
    "cmd_perf": ("/api/v1/system/perf", "性能指标"),
    "cmd_brief": ("/api/v1/system/daily-brief", "执行简报"),
    "cmd_model": ("/api/v1/pool/stats", "当前模型"),
    "cmd_config": ("/api/v1/system/services", "运行配置"),
    "cmd_settings": ("/api/v1/controls/settings", "偏好设置"),
    # 社媒类
    "cmd_hot": ("/api/v1/social/extension/trends?platform=x&limit=8", "热点发文选题"),
    "cmd_social_report": ("/api/v1/social/analytics?days=7", "社媒报告"),
    "cmd_social_persona": ("/api/v1/social/personas", "社媒人设"),
    "cmd_social_plan": ("/api/v1/social/ops-workspace", "发文计划"),
    "cmd_topic": ("/api/v1/social/topics?count=10", "题材研究"),
    "cmd_social_calendar": ("/api/v1/social/calendar?days=7", "发文日历"),
    "cmd_deals": ("/api/v1/store/catalog?query={arg}", "折扣搜索"),
    "cmd_intel": ("/api/v1/monitor/news", "全球情报"),
    # 风控
    "cmd_risk": ("/api/v1/monitor/risk", "风控状态"),
    # 仪表盘
    "cmd_dashboard": ("/api/v1/trading/dashboard", "交易仪表盘"),
}

_LOCAL_COMMAND_HANDLERS: set[int] = {100, 101, 203, 207, 408, *range(700, 709)}
_EXPLICIT_UNAVAILABLE_COMMANDS: dict[int, str] = {
    105: "文字转语音目前只有 Telegram 文件发送形态，微信转发器没有对应音频回传 API；请在 Telegram 使用 /tts。",
    106: "二维码生成目前只有 Telegram 图片回传形态，微信转发器没有对应图片回传 API；请在 Telegram 使用 /qr。",
    230: "实盘买入涉及真实交易，微信编号入口不自动下单；请到交易面板人工确认，系统不会绕过风控。",
    231: "实盘卖出涉及真实交易，微信编号入口不自动下单；请到交易面板人工确认，系统不会绕过风控。",
    235: "取消订单会改变真实账户状态，微信编号入口不直接执行；请到交易面板人工确认。",
    301: "双平台发文只允许生成待审草稿，不会自动发布；请在 Social 中控人工确认。",
    302: "X 发文只允许生成待审草稿，不会自动发布；请在 Social 中控人工确认。",
    303: "小红书发文只允许生成待审草稿，不会自动发布；请在 Social 中控人工确认。",
    404: "降价监控目前没有稳定只读 API；可用 405 折扣搜索查看候选商品。",
    501: "话费账单历史自动化已下线，当前没有安全可用的账单 API。",
    502: "数据导出会生成本地文件，微信转发器没有安全附件回传通道；请在桌面端执行导出。",
    503: "自动化工作台当前只在桌面端提供，微信只保留状态查询，避免误触发本机自动化。",
}


async def _execute_numbered_cmd(num: int, arg: str, from_user: str = "") -> str:
    """执行编号命令，返回文本结果。

    通过 HTTP self-call 调用本地 FastAPI 端点，确保调用路径与 API 路由层完全一致。
    """
    cmd_info = NUMBERED_COMMANDS.get(num)
    if not cmd_info:
        return f"未知命令编号: {num}"

    desc, needs_arg, func_name = cmd_info

    # 每日简报的 706 没参数时要给示例，而不是返回通用错误。
    if 700 <= num <= 708:
        try:
            from src.intel.channel_menu import handle_numbered_intel_command

            result = handle_numbered_intel_command(
                _intel_brief_db_path(),
                channel="wechat",
                external_user_id=from_user or "wechat-user",
                number=num,
                arg=arg,
                now=datetime.now(UTC).isoformat(),
            )
            return str(result.get("reply_text") or "已处理每日简报命令。")
        except Exception as e:
            logger.warning("[微信] 每日简报命令 %d 执行失败: %s", num, e)
            return "每日简报命令执行出错，请稍后再试。"

    # 需要参数但没提供
    if needs_arg and not arg:
        return f"命令 {num}({desc}) 需要参数\n例如: \"{num} 内容\""

    try:
        # ── 有 API 映射的命令: 直接调用本地端点 ──
        if func_name in _CMD_API_MAP:
            path_template, title = _CMD_API_MAP[func_name]
            path = path_template.replace("{arg}", arg) if "{arg}" in path_template else path_template
            data = await _self_call_api(path, timeout=15.0)
            # 持仓数据特殊格式化
            if func_name in ("cmd_ipositions", "cmd_monitor"):
                return _format_positions(data) if isinstance(data, dict) else _format_dict_result(title, data)
            return _format_dict_result(title, data)

        # ── 技术分析: 需要拼 symbol 参数 ──
        if func_name == "cmd_ta":
            data = await _self_call_api(f"/api/v1/trading/kline?symbol={arg}&interval=1d&limit=30", timeout=15.0)
            return _format_dict_result(f"{arg} 技术分析", data)

        if func_name == "cmd_calc":
            return (
                "📐 仓位计算器\n\n"
                "请发送: 207 入场价 止损价 账户资金 风险比例\n"
                "示例: 207 100 95 2000 0.02\n"
                "该微信入口只做计算建议，不会下单。"
            )

        if num in _EXPLICIT_UNAVAILABLE_COMMANDS:
            return f"⚠️ {desc}\n\n{_EXPLICIT_UNAVAILABLE_COMMANDS[num]}"

        # ── 黑五折扣搜索: 直接调用扫描器 ──
        if num == 408:
            try:
                from src.shopping.blackfriday_scanner import (
                    format_deals_message,
                    scan_blackfriday_deals,
                )
                deals = await scan_blackfriday_deals(arg)
                return format_deals_message(arg, deals)
            except Exception as e:
                logger.warning("[微信] 黑五折扣搜索失败: %s", e)
                return f"黑五折扣搜索失败: {e}"

        # ── 需要复杂交互的命令: 走 LLM 语义理解 ──
        prompt = f"用户想要执行「{desc}」"
        if arg:
            prompt += f"，参数: {arg}"
        reply = await _generate_wechat_reply(prompt)
        return reply or f"已收到指令: {desc}{(f' ({arg})' if arg else '')}"

    except Exception as e:
        logger.warning("[微信] 命令 %d 执行失败: %s", num, e)
        return "命令执行出错，请稍后再试"


def _format_quote(data: dict) -> str:
    """格式化行情数据为微信文本。"""
    if isinstance(data, str):
        return data
    symbol = data.get("symbol", "")
    price = data.get("price", 0)
    change = data.get("change_pct", 0)
    arrow = "📈" if change >= 0 else "📉"
    return (
        f"{arrow} {symbol}\n"
        f"价格: ${price}\n"
        f"涨跌: {change:+.2f}%\n"
        f"成交量: {data.get('volume', 'N/A')}"
    )


def _format_positions(data: dict) -> str:
    """格式化持仓数据。"""
    positions = data.get("positions", [])
    if not positions:
        return "当前无持仓"
    lines = ["📊 当前持仓\n"]
    for p in positions[:10]:
        sym = p.get("symbol", "?")
        qty = p.get("quantity", 0)
        val = p.get("market_value", 0)
        pnl = p.get("unrealized_pnl", 0)
        arrow = "📈" if pnl >= 0 else "📉"
        lines.append(f"{arrow} {sym}: {qty}股 ${val:,.0f} ({pnl:+,.0f})")
    total = data.get("total_value", 0)
    if total:
        lines.append(f"\n总市值: ${total:,.2f}")
    return "\n".join(lines)


def _format_dict_result(title: str, data: dict | list | str) -> str:
    """通用格式化: 把 dict/list 转为可读文本。"""
    if isinstance(data, str):
        return f"📋 {title}\n\n{data}"
    if isinstance(data, list):
        if not data:
            return f"📋 {title}\n\n暂无数据"
        # 列表中每项转为简要文本
        lines = [f"📋 {title}\n"]
        for i, item in enumerate(data[:15], 1):
            if isinstance(item, dict):
                # 取前 3 个 key-value
                parts = [f"{k}: {v}" for k, v in list(item.items())[:3]]
                lines.append(f"{i}. {' | '.join(parts)}")
            else:
                lines.append(f"{i}. {item}")
        return "\n".join(lines)
    if isinstance(data, dict):
        if data.get("error"):
            return f"📋 {title}\n\n❌ {data['error']}"
        lines = [f"📋 {title}\n"]
        for k, v in list(data.items())[:20]:
            if k in ("error", "success", "detail"):
                continue
            # 简化展示
            if isinstance(v, float):
                display = f"{v:,.2f}"
            elif isinstance(v, (dict, list)):
                display = f"[{len(v) if isinstance(v, list) else len(v.keys())} 项]"
            else:
                display = str(v)[:100]
            # 翻译常见 key 名
            cn_key = _translate_key(k)
            lines.append(f"  {cn_key}: {display}")
        return "\n".join(lines)
    return f"📋 {title}\n\n{data}"


def _translate_key(key: str) -> str:
    """将英文 key 翻译为中文标签。"""
    translations = {
        "total_pnl": "总盈亏",
        "total_pnl_pct": "总收益率%",
        "daily_pnl": "今日盈亏",
        "account_value": "账户价值",
        "win_rate": "胜率",
        "total_trades": "总交易数",
        "winning_trades": "盈利交易",
        "losing_trades": "亏损交易",
        "sharpe_ratio": "夏普比率",
        "max_drawdown": "最大回撤",
        "cash": "现金",
        "buying_power": "购买力",
        "status": "状态",
        "uptime": "运行时长",
        "services": "服务",
        "positions": "持仓",
        "total_value": "总市值",
        "connected": "已连接",
        "price": "价格",
        "change_pct": "涨跌%",
        "volume": "成交量",
        "symbol": "代码",
        "name": "名称",
        "quantity": "数量",
        "market_value": "市值",
        "unrealized_pnl": "未实现盈亏",
        "total_memories": "总记忆数",
        "cpu_percent": "CPU%",
        "memory_mb": "内存MB",
        "initialized": "已初始化",
        "status_text": "状态详情",
    }
    return translations.get(key, key)


async def _generate_wechat_reply(text: str, history: list[dict] | None = None) -> str | None:
    """微信场景走轻量 LLM 链路，带对话记忆，避免完整 Brain 链路响应过慢。"""
    try:
        from src.litellm_router import free_pool

        messages: list[dict] = [
            {"role": "system", "content": "你是 OpenClaw AI 助手。用中文简洁友好地回答用户的问题。"},
        ]
        # 注入对话历史（如有）
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": text})

        response = await free_pool.acompletion(
            model_family="qwen",
            messages=messages,
            max_tokens=500,
        )
        llm_text = response.choices[0].message.content or ""
        return llm_text.strip() or None
    except Exception as exc:
        logger.warning("[微信] LLM 调用失败: %s", exc)
        return None


@router.post("/incoming", response_model=WeChatIncomingResponse)
async def wechat_incoming(payload: WeChatIncomingRequest) -> WeChatIncomingResponse:
    """处理云端转发的微信消息。

    优先级: 编号命令 > 招呼语 > 中文自然语言 > LLM 对话
    """
    from_user = payload.from_user
    text = payload.text.strip()

    if not text:
        return WeChatIncomingResponse(reply="你好！有什么可以帮你的吗？")

    logger.info("[微信] 收到消息 from=%s...: %s", from_user[:15], text[:50])
    start = time.time()

    # ── 1. 编号命令/显式菜单/中文快捷词优先 ──
    num, arg = _parse_numbered_cmd(text)

    # 菜单/帮助这类显式跳转要能打断两步式状态，避免把“菜单”误当成推送时间或追踪词。
    if num is None and text.lower() in ("/start", "你好", "hi", "hello", "菜单", "帮助", "help"):
        _clear_pending_action(from_user)
        return WeChatIncomingResponse(reply=_build_welcome_message())

    # 微信没有 Telegram 的点击按钮，小白用户常会直接发中文入口名。
    text_shortcut = _parse_intel_text_shortcut(text)
    if num is None and text_shortcut is not None:
        _clear_pending_action(from_user)
        num, arg = text_shortcut
        if num == 705 and not arg:
            _set_pending_action(from_user, "intel_schedule")
        if num == 706 and not arg:
            _set_pending_action(from_user, "intel_custom")
        reply = await _execute_numbered_cmd(num, arg, from_user=from_user)
        elapsed = round(time.time() - start, 2)
        logger.info("[微信] 快捷词命令 %d 执行 (%ss): %s...", num, elapsed, reply[:50])
        return WeChatIncomingResponse(reply=reply)

    pending_action = _get_pending_action(from_user)
    if pending_action and num is None:
        if text.lower() in ("0", "取消", "cancel", "算了", "不用了"):
            _clear_pending_action(from_user)
            return WeChatIncomingResponse(reply="已取消。需要时回复 700 打开每日简报菜单。")
        if pending_action == "intel_schedule":
            _clear_pending_action(from_user)
            return WeChatIncomingResponse(reply=await _execute_numbered_cmd(705, text, from_user=from_user))
        if pending_action == "intel_custom":
            _clear_pending_action(from_user)
            return WeChatIncomingResponse(reply=await _execute_numbered_cmd(706, text, from_user=from_user))
    if pending_action and num is not None:
        _clear_pending_action(from_user)
    if num is not None:
        # 特殊处理: 100 = 帮助菜单
        if num == 100:
            return WeChatIncomingResponse(reply=_build_full_help())
        # 101 = 清空对话记忆
        if num == 101:
            _wechat_memory.pop(from_user, None)
            _clear_pending_action(from_user)
            return WeChatIncomingResponse(reply="✅ 对话记忆已清空")
        if num == 705 and not arg:
            _set_pending_action(from_user, "intel_schedule")
        if num == 706 and not arg:
            _set_pending_action(from_user, "intel_custom")
        reply = await _execute_numbered_cmd(num, arg, from_user=from_user)
        elapsed = round(time.time() - start, 2)
        logger.info("[微信] 命令 %d 执行 (%ss): %s...", num, elapsed, reply[:50])
        return WeChatIncomingResponse(reply=reply)

    # ── 2. LLM 对话（带对话记忆）──
    history = _get_user_history(from_user)
    reply = await _generate_wechat_reply(text, history=history)
    if not reply:
        reply = "抱歉，我暂时没能理解你的意思。换个方式再试试？"
    else:
        # 对话成功 → 记录用户消息和助手回复到历史
        _add_to_history(from_user, "user", text)
        _add_to_history(from_user, "assistant", reply)

    reply = _strip_g4f_ads(reply)
    elapsed = round(time.time() - start, 2)
    logger.info("[微信] 回复生成 (%ss): %s...", elapsed, reply[:50])
    return WeChatIncomingResponse(reply=reply)


@router.get("/intel-brief-bridge-status")
async def wechat_intel_brief_bridge_status(
    max_age_seconds: int = Query(default=900, ge=30, le=86400),
) -> dict:
    """返回微信每日简报真实桥接状态，只读且不暴露聊天内容。"""
    from src.intel.wechat_bridge_runtime import (
        build_wechat_bridge_runtime_acceptance,
        summarize_wechat_bridge_status,
    )

    result = build_wechat_bridge_runtime_acceptance(max_age_seconds=max_age_seconds)
    summary = summarize_wechat_bridge_status(result)
    return {
        "ok": bool(summary.get("verified")),
        "state": summary["state"],
        "severity": summary["severity"],
        "title": summary["title"],
        "next_action": summary["next_action"],
        "checked_at": result.get("checked_at"),
        "max_age_seconds": result.get("max_age_seconds"),
        "age_seconds": result.get("age_seconds"),
        "blockers": summary.get("blockers", []),
        "latest": summary.get("latest", {}),
        "privacy": summary.get("privacy", {}),
        "safe_to_show_owner": True,
    }
