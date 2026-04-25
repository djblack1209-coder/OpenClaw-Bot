"""微信消息处理 API Router。

接收云端 wechat_receiver 转发的微信消息。
支持编号命令快捷操作 + 中文自然语言 + LLM 对话。
"""

import logging
import re
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wechat")


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
    # 🛒 400-409: 闲鱼 & 电商
    400: ("闲鱼控制", False, "cmd_xianyu"),
    401: ("闲鱼报表", False, "cmd_xianyu_report"),
    402: ("闲鱼话术", False, "cmd_xianyu_style"),
    403: ("闲鱼发货", False, "cmd_ship"),
    404: ("降价监控", True, "cmd_pricewatch"),
    405: ("折扣搜索", True, "cmd_deals"),
    406: ("微信领券", False, "cmd_coupon"),
    407: ("全球情报", False, "cmd_intel"),
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
}


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
        "300 热点发文  |  401 闲鱼报表\n"
        "\n"
        "💡 带参数用法\n"
        "发 \"200 AAPL\" → 查苹果股价\n"
        "发 \"103 一只猫\" → AI 画图\n"
        "发 \"217 半导体\" → AI 投资分析会\n"
        "发 \"206 TSLA\" → K线图\n"
        "\n"
        "📈 投资: 200-221 | 🏦 实盘: 230-235\n"
        "📱 社媒: 300-308 | 🛒 闲鱼: 400-407\n"
        "🏠 生活: 500-503 | ⚙️ 系统: 600-606\n"
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
        4: "🛒 闲鱼 & 电商 (400-407)",
        5: "🏠 生活助手 (500-503)",
        6: "⚙️ 系统设置 (600-606)",
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


async def _execute_numbered_cmd(num: int, arg: str) -> str:
    """执行编号命令，返回文本结果。

    通过 RPC 层调用后端业务逻辑，避免依赖 Telegram Update 对象。
    """
    from src.api.rpc import ClawBotRPC

    cmd_info = NUMBERED_COMMANDS.get(num)
    if not cmd_info:
        return f"未知命令编号: {num}"

    desc, needs_arg, func_name = cmd_info

    # 需要参数但没提供
    if needs_arg and not arg:
        return f"命令 {num}({desc}) 需要参数\n例如: \"{num} 内容\""

    try:
        # ── 投资类: 通过 RPC 调用 ──
        if func_name == "cmd_quote":
            data = await ClawBotRPC._rpc_trading_quote(arg)
            if isinstance(data, dict) and data.get("error"):
                return f"查询失败: {data['error']}"
            if isinstance(data, str):
                return data
            return _format_quote(data)

        if func_name == "cmd_market":
            data = ClawBotRPC._rpc_trading_market_overview()
            return _format_dict_result("市场概览", data)

        if func_name == "cmd_portfolio":
            data = await ClawBotRPC._rpc_trading_portfolio_summary()
            return _format_dict_result("投资组合", data)

        if func_name == "cmd_ta":
            data = await ClawBotRPC._rpc_trading_ta(arg)
            return _format_dict_result(f"{arg} 技术分析", data)

        if func_name == "cmd_signal":
            data = ClawBotRPC._rpc_trading_signals()
            return _format_dict_result("交易信号", data)

        if func_name == "cmd_trades":
            data = ClawBotRPC._rpc_trading_journal_entries(limit=10)
            return _format_dict_result("最近交易", data)

        if func_name == "cmd_watchlist":
            data = ClawBotRPC._rpc_trading_watchlist()
            return _format_dict_result("自选股", data)

        if func_name == "cmd_risk":
            data = ClawBotRPC._rpc_trading_risk_status()
            return _format_dict_result("风控状态", data)

        if func_name in ("cmd_ipositions", "cmd_monitor"):
            data = await ClawBotRPC._rpc_trading_positions()
            return _format_positions(data)

        if func_name == "cmd_iaccount":
            data = await ClawBotRPC._rpc_trading_pnl()
            return _format_dict_result("IBKR 账户", data)

        if func_name == "cmd_tradingsystem":
            data = ClawBotRPC._rpc_trading_system_status()
            return _format_dict_result("交易系统", data)

        if func_name == "cmd_performance":
            data = await ClawBotRPC._rpc_trading_pnl()
            return _format_dict_result("投资绩效", data)

        # ── 系统类 ──
        if func_name == "cmd_status":
            data = ClawBotRPC._rpc_system_status()
            return _format_dict_result("系统状态", data)

        if func_name == "cmd_news":
            data = await ClawBotRPC._rpc_daily_brief()
            if isinstance(data, str):
                return data
            return _format_dict_result("今日简报", data)

        if func_name == "cmd_pool":
            data = ClawBotRPC._rpc_pool_stats()
            return _format_dict_result("API 池", data)

        if func_name == "cmd_memory":
            data = ClawBotRPC._rpc_memory_stats()
            return _format_dict_result("记忆管理", data)

        if func_name == "cmd_cost":
            data = ClawBotRPC._rpc_omega_cost()
            return _format_dict_result("成本配额", data)

        if func_name == "cmd_perf":
            data = ClawBotRPC._rpc_system_perf()
            return _format_dict_result("性能指标", data)

        # ── 闲鱼类 ──
        if func_name == "cmd_xianyu":
            data = ClawBotRPC._rpc_xianyu_conversations()
            return _format_dict_result("闲鱼客服", data)

        if func_name == "cmd_xianyu_report":
            data = ClawBotRPC._rpc_xianyu_profit()
            return _format_dict_result("闲鱼报表", data)

        # ── 社媒类 ──
        if func_name == "cmd_social_report":
            data = ClawBotRPC._rpc_social_analytics(days=7)
            return _format_dict_result("社媒报告", data)

        if func_name == "cmd_social_persona":
            data = ClawBotRPC._rpc_social_personas()
            return _format_dict_result("社媒人设", data)

        # ── 需要 Telegram 交互的命令: 走 LLM 代理 ──
        if func_name in (
            "cmd_draw", "cmd_tts", "cmd_qr", "cmd_calc", "cmd_chart",
            "cmd_backtest", "cmd_invest", "cmd_post", "cmd_xpost",
            "cmd_xhspost", "cmd_topic", "cmd_hot", "cmd_social_plan",
            "cmd_social_calendar", "cmd_ibuy", "cmd_isell", "cmd_icancel",
            "cmd_iorders", "cmd_xianyu_style", "cmd_ship", "cmd_pricewatch",
            "cmd_deals", "cmd_coupon", "cmd_intel", "cmd_brief", "cmd_bill",
            "cmd_export", "cmd_ops", "cmd_settings", "cmd_model", "cmd_config",
            "cmd_scan", "cmd_journal", "cmd_review", "cmd_equity",
            "cmd_targets", "cmd_accuracy", "cmd_weekly", "cmd_rebalance",
            "cmd_clear",
        ):
            # 这些命令需要复杂的交互逻辑，走 LLM 语义理解
            prompt = f"用户想要执行「{desc}」"
            if arg:
                prompt += f"，参数: {arg}"
            reply = await _generate_wechat_reply(prompt)
            return reply or f"已收到指令: {desc}" + (f" ({arg})" if arg else "")

        # 默认: 用 LLM 处理
        return f"命令 {num}({desc}) 正在处理中..."

    except Exception as e:
        logger.warning("[微信] 命令 %d 执行失败: %s", num, e)
        return f"命令执行出错，请稍后再试"


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


async def _generate_wechat_reply(text: str) -> str | None:
    """微信场景走轻量 LLM 链路，避免完整 Brain 链路响应过慢。"""
    try:
        from src.litellm_router import free_pool

        response = await free_pool.acompletion(
            model_family="qwen",
            messages=[
                {"role": "system", "content": "你是 OpenClaw AI 助手。用中文简洁友好地回答用户的问题。"},
                {"role": "user", "content": text},
            ],
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

    # ── 1. 编号命令优先 ──
    num, arg = _parse_numbered_cmd(text)
    if num is not None:
        # 特殊处理: 100 = 帮助菜单
        if num == 100:
            return WeChatIncomingResponse(reply=_build_full_help())
        reply = await _execute_numbered_cmd(num, arg)
        elapsed = round(time.time() - start, 2)
        logger.info("[微信] 命令 %d 执行 (%ss): %s...", num, elapsed, reply[:50])
        return WeChatIncomingResponse(reply=reply)

    # ── 2. 招呼语 → 欢迎消息 ──
    if text.lower() in ("/start", "你好", "hi", "hello", "菜单", "帮助", "help"):
        return WeChatIncomingResponse(reply=_build_welcome_message())

    # ── 3. LLM 对话 ──
    reply = await _generate_wechat_reply(text)
    if not reply:
        reply = "抱歉，我暂时没能理解你的意思。换个方式再试试？"

    reply = _strip_g4f_ads(reply)
    elapsed = round(time.time() - start, 2)
    logger.info("[微信] 回复生成 (%ss): %s...", elapsed, reply[:50])
    return WeChatIncomingResponse(reply=reply)
