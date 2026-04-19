# input_processor.py — 输入预处理：纠正检测 + 智能回复键盘
# 从 message_mixin.py 拆分而来

import logging
import re

logger = logging.getLogger(__name__)


def _detect_correction(text: str) -> bool:
    """检测用户是否在纠正上一轮的回复 — 搬运 ChatGPT correction handling 模式

    检测信号词: "不对/说错了/搞错了/纠正/你记错了/不是X是Y"
    返回 True 表示这条消息是纠正指令，需要特殊处理。
    """
    if not text or len(text) < 2:
        return False
    _CORRECTION_PATTERNS = [
        r"^(?:不对|错了|说错了|搞错了|弄错了|你[搞说弄]错了|你记错了)",
        r"(?:不是.*(?:是|而是|应该是))",
        r"^(?:纠正|更正|我说的是|我的意思是|我是说)",
        r"^(?:重新(?:来|说|分析|查))",
    ]
    for pattern in _CORRECTION_PATTERNS:
        if re.search(pattern, text.strip()):
            return True
    return False


def _build_smart_reply_keyboard(
    response_text: str, bot_id: str, model_used: str, chat_id: int, ai_suggestions: list = None
):
    """分析 LLM 回复内容，生成上下文相关的行动按钮

    规则:
    1. 如果有 AI 生成的追问建议，优先显示在最前面
    2. 检测回复中提到的股票代码 → 技术分析/报价按钮
    3. 检测交易关键词 → 买入/卖出/止损按钮
    4. 检测商品/购物关键词 → 比价按钮
    5. 始终保留反馈按钮 (👍👎🔄)
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from src.feedback import build_feedback_keyboard

    text = (response_text or "").lower()
    action_buttons = []
    suggest_row = []  # AI 追问建议独立一行

    # 0. AI 追问建议按钮（智能追问引擎生成）
    if ai_suggestions:
        for suggestion in ai_suggestions[:3]:
            # Telegram callback_data 限制 64 字节
            # 中文 UTF-8 每字符 3 字节，截断到 ~18 字符确保安全
            cb_text = suggestion[:18]
            cb_data = f"suggest:{cb_text}"
            # 二次检查: callback_data 编码后不超过 64 字节
            if len(cb_data.encode("utf-8")) > 64:
                cb_data = f"suggest:{suggestion[:12]}"
            suggest_row.append(InlineKeyboardButton(f"💬 {suggestion[:15]}", callback_data=cb_data))

    # 1. 检测股票代码 (英文ticker)
    tickers_found = re.findall(r"\b([A-Z]{1,5})\b", response_text)
    # 过滤掉常见非ticker词
    skip_words = {
        "AI",
        "ETF",
        "RSI",
        "MACD",
        "KDJ",
        "EMA",
        "SMA",
        "ATR",
        "VWAP",
        "API",
        "USD",
        "BTC",
        "OK",
        "VS",
        "PDF",
        "URL",
        "VIA",
        "BOT",
        "LLM",
        "HTML",
        "CSS",
        "SQL",
        "NLP",
        "RPC",
        "SOP",
        "ROI",
        "PNL",
        "IPO",
        "CEO",
        "CTO",
        "GDP",
        "CPI",
        "FED",
        "SEC",
        "NYSE",
        "PRO",
        "MAX",
        "MIN",
    }
    valid_tickers = [t for t in tickers_found if t not in skip_words and len(t) >= 2]

    if valid_tickers:
        ticker = valid_tickers[0]  # 取第一个
        action_buttons.append(InlineKeyboardButton(f"📊 分析{ticker}", callback_data=f"ta_{ticker}"))
        if any(kw in text for kw in ["买入", "建仓", "加仓", "推荐买", "可以买", "值得买", "buy"]):
            action_buttons.append(InlineKeyboardButton(f"💰 买入{ticker}", callback_data=f"buy_{ticker}"))
        elif any(kw in text for kw in ["卖出", "减仓", "止盈", "清仓", "平仓", "sell"]):
            action_buttons.append(InlineKeyboardButton(f"📉 卖出{ticker}", callback_data=f"cmd:sell {ticker}"))
        else:
            action_buttons.append(InlineKeyboardButton(f"💹 报价{ticker}", callback_data=f"cmd:quote {ticker}"))

    # 2. 检测持仓/投资主题 (无特定ticker时)
    if not action_buttons and any(kw in text for kw in ["持仓", "仓位", "组合", "盈亏", "浮盈", "浮亏"]):
        action_buttons.append(InlineKeyboardButton("📋 查看持仓", callback_data="cmd:portfolio"))
        action_buttons.append(InlineKeyboardButton("📊 查看绩效", callback_data="cmd:performance"))

    # 3. 检测市场/行情主题
    if not action_buttons and any(kw in text for kw in ["大盘", "市场", "指数", "行情", "美股", "a股"]):
        action_buttons.append(InlineKeyboardButton("💹 市场概览", callback_data="cmd:market"))
        action_buttons.append(InlineKeyboardButton("📰 今日简报", callback_data="cmd:brief"))

    # 4. 检测购物/商品主题
    if not action_buttons and any(
        kw in text for kw in ["价格", "元", "优惠", "打折", "推荐", "购买", "京东", "淘宝", "拼多多", "亚马逊"]
    ):
        # 尝试提取商品名
        product_match = re.search(r"([\w\-]+\s*(?:Pro|Max|Plus|Ultra)?)", response_text)
        if product_match and len(product_match.group(1)) > 2:
            product = product_match.group(1).strip()[:20]
            action_buttons.append(InlineKeyboardButton(f"🛒 比价{product}", callback_data=f"shop:{product}"))

    # 4.5 中文商品名检测 (补充英文正则覆盖不到的场景)
    cn_product_match = re.search(
        r"(?:买|推荐|比价|搜|找)\s*(?:一[个台只双部条])?"
        r"([\u4e00-\u9fff]{2,8}(?:Pro|Max|Plus|Ultra|mini)?)",
        response_text,
    )
    if cn_product_match and not action_buttons:
        product = cn_product_match.group(1)
        action_buttons.append(InlineKeyboardButton(f"🛒 比价 {product}", callback_data=f"shop:{product}"))

    # 5. 检测社媒主题
    if not action_buttons and any(kw in text for kw in ["发文", "小红书", "推特", "热点", "社媒", "内容"]):
        action_buttons.append(InlineKeyboardButton("🔥 热点发文", callback_data="cmd:hotpost"))
        action_buttons.append(InlineKeyboardButton("📱 社媒计划", callback_data="cmd:social_plan"))

    # 通用聊天: 无特定领域按钮时，展示能力发现按钮（替代无用的"继续聊"）
    # 搬运灵感: ChatGPT 首页的 suggested prompts / Google Gemini 推荐操作
    if not action_buttons:
        _capability_buttons = [
            InlineKeyboardButton("📊 分析股票", callback_data="suggest:帮我分析一只股票"),
            InlineKeyboardButton("🛒 比价购物", callback_data="suggest:帮我比价一个商品"),
            InlineKeyboardButton("📱 社媒发文", callback_data="suggest:帮我写一篇小红书"),
        ]
        action_buttons.extend(_capability_buttons[:2])  # 最多展示2个

    # 组装键盘: AI建议行(如有) + 行动按钮(最多3个) + 反馈按钮
    rows = []
    if suggest_row:
        rows.append(suggest_row[:3])  # AI 追问建议放最前
    if action_buttons:
        rows.append(action_buttons[:3])  # 最多3个行动按钮

    # 反馈行 (简化)
    fb_keyboard = build_feedback_keyboard(bot_id, model_used, chat_id)
    rows.extend(fb_keyboard.inline_keyboard)

    return InlineKeyboardMarkup(rows)
