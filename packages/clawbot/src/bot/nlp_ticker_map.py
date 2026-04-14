# nlp_ticker_map.py — 中文 ticker 映射 + 对话噪音清洗 + 模糊命令建议
# 从 chinese_nlp_mixin.py 拆分 (HI-358)

import difflib
import re

# ── 中文对话粒子清洗 (Gap 5 修复) ──────────────────────────
# 用户说"帮我分析一下苹果的走势好不好"时，regex捕获到"一下苹果的走势好不好"
# 这个函数剥离对话噪音，只留"苹果的走势"

_FILLER_PATTERNS = re.compile(
    r"^(?:帮我|给我|帮忙|请|麻烦|看看|查一下|来个|来条)?"  # 前缀
    r"|(?:一下|一个|一些|吧|啊|呢|呀|嘛|喔|哦|了|的话|好吗|行吗|可以吗|好不好|怎么样|行不行)$"  # 后缀
)


def _clean_capture(text: str) -> str:
    """剥离中文对话噪音，只留核心内容。"""
    if not text:
        return text
    result = text.strip()
    # 多轮剥离（前缀+后缀可能嵌套）
    for _ in range(3):
        cleaned = _FILLER_PATTERNS.sub("", result).strip()
        cleaned = cleaned.strip("的")  # 尾部"的"
        if cleaned == result or not cleaned:
            break
        result = cleaned
    return result or text.strip()


# ── "你是不是想说…" 建议机制 v2.0 (jieba 增强) ──────────────
# 三层匹配: 1.关键词包含 → 2.jieba分词交集 → 3.difflib字符相似
# 覆盖"帮我看看我的持仓情况怎么样" → 分词抽出"持仓" → 命中 portfolio

_COMMAND_KEYWORDS: list[tuple[str, str, str]] = [
    # (关键词, action_name, 显示标签)
    ("开始", "start", "开始/帮助"),
    ("帮助", "start", "开始/帮助"),
    ("你好", "start", "打招呼"),
    ("菜单", "start", "功能菜单"),
    ("清空对话", "clear", "清空对话"),
    ("清空", "clear", "清空对话"),
    ("重置对话", "clear", "重置对话"),
    ("状态", "status", "查看状态"),
    ("查看状态", "status", "查看状态"),
    ("配置", "config", "查看配置"),
    ("成本", "cost", "查看成本"),
    ("配额", "cost", "查看配额"),
    ("用量", "cost", "查看用量"),
    ("上下文", "context", "上下文状态"),
    ("压缩", "compact", "压缩上下文"),
    ("新闻", "news", "科技早报"),
    ("早报", "news", "科技早报"),
    ("指标", "metrics", "运行指标"),
    ("分流", "lanes", "分流规则"),
    ("赏金列表", "ops_bounty_list", "赏金列表"),
    ("赏金排行", "ops_bounty_top", "赏金排行"),
    ("首发包", "social_launch", "社媒首发包"),
    ("社媒人设", "social_persona", "社媒人设"),
    ("一键发文", "social_hotpost", "一键发文"),
    ("资讯监控列表", "ops_monitor_list", "资讯监控"),
    ("运行资讯监控", "ops_monitor_run", "运行监控"),
    ("自选股", "watchlist", "自选股"),
    ("关注列表", "watchlist", "自选股"),
    ("交易记录", "trades", "交易记录"),
    ("交易历史", "trades", "交易记录"),
    ("订单状态", "iorders", "盈透订单"),
    ("账户余额", "iaccount", "盈透账户"),
    ("发文日历", "social_calendar", "发文日历"),
    ("语音播报", "voice", "语音播报"),
    ("写小说", "novel", "AI写作"),
    ("发货管理", "ship", "发货管理"),
    ("复盘历史", "review_history", "复盘历史"),
    # v2.0 新增: 高频场景补全
    ("持仓", "portfolio", "查看持仓"),
    ("仓位", "portfolio", "查看持仓"),
    ("投资组合", "portfolio", "投资组合"),
    ("行情", "market", "市场概览"),
    ("大盘", "market", "市场概览"),
    ("比价", "smart_shop", "购物比价"),
    ("简报", "ops_brief", "今日简报"),
    ("日报", "ops_brief", "今日简报"),
    ("周报", "weekly", "综合周报"),
    ("提醒", "ops_life_remind", "设置提醒"),
    ("闹钟", "ops_life_remind", "设置提醒"),
    ("记账", "expense_add", "记账"),
    ("账单", "bill_list", "账单追踪"),
    ("话费", "bill_list", "话费追踪"),
    ("闲鱼", "xianyu_report", "闲鱼报告"),
    ("复盘", "review", "交易复盘"),
    ("绩效", "performance", "投资绩效"),
    ("风控", "risk", "风控检查"),
    ("回测", "backtest", "策略回测"),
    ("监控", "monitor", "持仓监控"),
    ("扫描", "scan", "市场扫描"),
    ("热点", "social_hotpost", "热点发文"),
    ("发文", "social_post", "双平台发文"),
    ("小红书", "social_xhs", "发小红书"),
]

# jieba 分词器（条件导入，不可用时降级 difflib）
try:
    import jieba

    jieba.setLogLevel(20)  # 关闭 jieba 初始化日志
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

# 预构建关键词到命令的倒排索引（启动时一次性构建）
_KW_INDEX: dict[str, tuple[str, str, str]] = {}
for _kw, _act, _lbl in _COMMAND_KEYWORDS:
    _KW_INDEX[_kw] = (_act, _kw, _lbl)


def _suggest_command(text: str):
    """模糊匹配用户输入到已知命令 — jieba 增强 v2.0

    三层匹配策略:
      L1: 关键词直接包含 — "我想看持仓" 包含 "持仓" → portfolio
      L2: jieba 分词交集 — "帮我看看我的投资组合情况" → 分词 → "投资组合" 命中
      L3: difflib 字符相似 — "清空对话记录" ≈ "清空对话" → clear
    """
    if not text or len(text) > 50:
        return None
    cleaned = text.strip()

    # ── L1: 关键词包含匹配（最快，O(n)扫描）──
    # 按关键词长度降序匹配，优先匹配更精确的长关键词
    for kw in sorted(_KW_INDEX, key=len, reverse=True):
        if kw in cleaned:
            return _KW_INDEX[kw]

    # ── L2: jieba 分词交集（中等速度，捕获长句中的关键词）──
    if _HAS_JIEBA and len(cleaned) >= 4:
        # 对用户输入分词
        user_words = set(jieba.cut(cleaned, cut_all=False))
        # 和所有关键词做交集（也对多字关键词分词后比较）
        best_match = None
        best_overlap = 0
        for kw, act, lbl in _COMMAND_KEYWORDS:
            kw_words = set(jieba.cut(kw, cut_all=False)) if len(kw) >= 2 else {kw}
            overlap = len(user_words & kw_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = (act, kw, lbl)
        if best_match and best_overlap >= 1:
            return best_match

    # ── L3: difflib 字符相似（兜底）──
    if len(cleaned) <= 20:
        keywords = [kw for kw, _, _ in _COMMAND_KEYWORDS]
        matches = difflib.get_close_matches(cleaned, keywords, n=1, cutoff=0.55)
        if matches:
            return _KW_INDEX[matches[0]]

    return None


# ── v2.0: 中文公司名 → ticker 映射 (高频交易标的) ─────────────
# 覆盖用户最常提到的公司, 不做全量映射 (全量用 akshare/yfinance 解析)
_CN_TICKER_MAP = {
    # 美股科技
    "苹果": "AAPL",
    "谷歌": "GOOGL",
    "微软": "MSFT",
    "亚马逊": "AMZN",
    "特斯拉": "TSLA",
    "英伟达": "NVDA",
    "脸书": "META",
    "meta": "META",
    "奈飞": "NFLX",
    "网飞": "NFLX",
    "英特尔": "INTC",
    "amd": "AMD",
    "高通": "QCOM",
    "台积电": "TSM",
    "博通": "AVGO",
    "超微": "AMD",
    # 美股中概
    "阿里": "BABA",
    "阿里巴巴": "BABA",
    "京东": "JD",
    "拼多多": "PDD",
    "百度": "BIDU",
    "网易": "NTES",
    "腾讯": "TCEHY",
    "小鹏": "XPEV",
    "蔚来": "NIO",
    "理想": "LI",
    "哔哩哔哩": "BILI",
    "b站": "BILI",
    # 美股金融/消费
    "波音": "BA",
    "迪士尼": "DIS",
    "星巴克": "SBUX",
    "可口可乐": "KO",
    "摩根": "JPM",
    "高盛": "GS",
    "伯克希尔": "BRK-B",
    "巴菲特": "BRK-B",
    # 加密货币
    "比特币": "BTC-USD",
    "以太坊": "ETH-USD",
    "狗狗币": "DOGE-USD",
    "瑞波": "XRP-USD",
    "索拉纳": "SOL-USD",
    # 美股ETF
    "标普": "SPY",
    "纳斯达克": "QQQ",
    "道琼斯": "DIA",
}


def _resolve_chinese_ticker(name: str) -> str:
    """中文公司名/代号 → 标准 ticker

    优先级: 直接映射 → 英文 ticker 格式检测 → 返回空
    """
    name = (name or "").strip()
    if not name:
        return ""
    # 已经是英文 ticker
    if re.fullmatch(r"[A-Za-z]{1,5}(?:-USD)?", name):
        return name.upper()
    # 中文映射
    lower = name.lower().replace(" ", "")
    ticker = _CN_TICKER_MAP.get(lower, "")
    if ticker:
        return ticker
    # 部分匹配 (如 "苹果公司" → 苹果)
    for cn_name, tk in _CN_TICKER_MAP.items():
        if cn_name in lower or lower in cn_name:
            return tk
    return ""
