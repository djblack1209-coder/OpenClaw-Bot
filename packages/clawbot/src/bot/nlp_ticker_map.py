# nlp_ticker_map.py — 中文 ticker 映射 + 对话噪音清洗 + 模糊命令建议
# 从 chinese_nlp_mixin.py 拆分 (HI-358)

import difflib
import re

# ── 中文对话粒子清洗 (Gap 5 修复) ──────────────────────────
# 用户说"帮我分析一下苹果的走势好不好"时，regex捕获到"一下苹果的走势好不好"
# 这个函数剥离对话噪音，只留"苹果的走势"

_FILLER_PATTERNS = re.compile(
    r'^(?:帮我|给我|帮忙|请|麻烦|看看|查一下|来个|来条)?'  # 前缀
    r'|(?:一下|一个|一些|吧|啊|呢|呀|嘛|喔|哦|了|的话|好吗|行吗|可以吗|好不好|怎么样|行不行)$'  # 后缀
)


def _clean_capture(text: str) -> str:
    """剥离中文对话噪音，只留核心内容。"""
    if not text:
        return text
    result = text.strip()
    # 多轮剥离（前缀+后缀可能嵌套）
    for _ in range(3):
        cleaned = _FILLER_PATTERNS.sub('', result).strip()
        cleaned = cleaned.strip('的')  # 尾部"的"
        if cleaned == result or not cleaned:
            break
        result = cleaned
    return result or text.strip()


# ── "你是不是想说…" 建议机制 (Gap 3 修复) ──────────────────
# 用户输入和已知命令模糊匹配，阈值 0.6

_COMMAND_KEYWORDS: list[tuple[str, str, str]] = [
    # (关键词, action_name, 显示标签)
    ('开始', 'start', '开始/帮助'), ('帮助', 'start', '开始/帮助'),
    ('你好', 'start', '打招呼'), ('菜单', 'start', '功能菜单'),
    ('清空对话', 'clear', '清空对话'), ('清空', 'clear', '清空对话'),
    ('重置对话', 'clear', '重置对话'),
    ('状态', 'status', '查看状态'), ('查看状态', 'status', '查看状态'),
    ('配置', 'config', '查看配置'),
    ('成本', 'cost', '查看成本'), ('配额', 'cost', '查看配额'), ('用量', 'cost', '查看用量'),
    ('上下文', 'context', '上下文状态'),
    ('压缩', 'compact', '压缩上下文'),
    ('新闻', 'news', '科技早报'), ('早报', 'news', '科技早报'),
    ('指标', 'metrics', '运行指标'),
    ('分流', 'lanes', '分流规则'),
    ('赏金列表', 'ops_bounty_list', '赏金列表'),
    ('赏金排行', 'ops_bounty_top', '赏金排行'),
    ('首发包', 'social_launch', '社媒首发包'),
    ('社媒人设', 'social_persona', '社媒人设'),
    ('一键发文', 'social_hotpost', '一键发文'),
    ('资讯监控列表', 'ops_monitor_list', '资讯监控'),
    ('运行资讯监控', 'ops_monitor_run', '运行监控'),
    # 新增: 高频命令的中文触发词
    ('自选股', 'watchlist', '自选股'), ('关注列表', 'watchlist', '自选股'),
    ('交易记录', 'trades', '交易记录'), ('交易历史', 'trades', '交易记录'),
    ('订单状态', 'iorders', '盈透订单'),
    ('账户余额', 'iaccount', '盈透账户'),
    ('发文日历', 'social_calendar', '发文日历'),
    ('语音播报', 'voice', '语音播报'),
    ('写小说', 'novel', 'AI写作'),
    ('发货管理', 'ship', '发货管理'),
    ('复盘历史', 'review_history', '复盘历史'),
]


def _suggest_command(text: str):
    """模糊匹配用户输入，返回最接近的命令建议。"""
    if not text or len(text) > 20:
        return None
    keywords = [kw for kw, _, _ in _COMMAND_KEYWORDS]
    matches = difflib.get_close_matches(text, keywords, n=1, cutoff=0.55)
    if matches:
        matched = matches[0]
        for kw, action, label in _COMMAND_KEYWORDS:
            if kw == matched:
                return (action, kw, label)
    return None


# ── v2.0: 中文公司名 → ticker 映射 (高频交易标的) ─────────────
# 覆盖用户最常提到的公司, 不做全量映射 (全量用 akshare/yfinance 解析)
_CN_TICKER_MAP = {
    # 美股科技
    '苹果': 'AAPL', '谷歌': 'GOOGL', '微软': 'MSFT', '亚马逊': 'AMZN',
    '特斯拉': 'TSLA', '英伟达': 'NVDA', '脸书': 'META', 'meta': 'META',
    '奈飞': 'NFLX', '网飞': 'NFLX', '英特尔': 'INTC', 'amd': 'AMD',
    '高通': 'QCOM', '台积电': 'TSM', '博通': 'AVGO', '超微': 'AMD',
    # 美股中概
    '阿里': 'BABA', '阿里巴巴': 'BABA', '京东': 'JD', '拼多多': 'PDD',
    '百度': 'BIDU', '网易': 'NTES', '腾讯': 'TCEHY', '小鹏': 'XPEV',
    '蔚来': 'NIO', '理想': 'LI', '哔哩哔哩': 'BILI', 'b站': 'BILI',
    # 美股金融/消费
    '波音': 'BA', '迪士尼': 'DIS', '星巴克': 'SBUX', '可口可乐': 'KO',
    '摩根': 'JPM', '高盛': 'GS', '伯克希尔': 'BRK-B', '巴菲特': 'BRK-B',
    # 加密货币
    '比特币': 'BTC-USD', '以太坊': 'ETH-USD', '狗狗币': 'DOGE-USD',
    '瑞波': 'XRP-USD', '索拉纳': 'SOL-USD',
    # 美股ETF
    '标普': 'SPY', '纳斯达克': 'QQQ', '道琼斯': 'DIA',
}


def _resolve_chinese_ticker(name: str) -> str:
    """中文公司名/代号 → 标准 ticker

    优先级: 直接映射 → 英文 ticker 格式检测 → 返回空
    """
    name = (name or '').strip()
    if not name:
        return ''
    # 已经是英文 ticker
    if re.fullmatch(r'[A-Za-z]{1,5}(?:-USD)?', name):
        return name.upper()
    # 中文映射
    lower = name.lower().replace(' ', '')
    ticker = _CN_TICKER_MAP.get(lower, '')
    if ticker:
        return ticker
    # 部分匹配 (如 "苹果公司" → 苹果)
    for cn_name, tk in _CN_TICKER_MAP.items():
        if cn_name in lower or lower in cn_name:
            return tk
    return ''
