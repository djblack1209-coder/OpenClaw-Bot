# chinese_nlp_mixin.py — 中文自然语言命令匹配 & 分发
# 从 message_mixin.py 拆分: 中文 ticker 映射 + NLP 命令匹配 + 分发逻辑
# 保留 message_mixin 中的消息处理/流式/OCR/智能建议等功能

import difflib
import logging
import re

logger = logging.getLogger(__name__)

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


def _match_chinese_command(text=None):
    '''
    匹配中文自然语言触发词，返回 (action_type, arg) 或 None

    v2.0 (2026-03-24): 新增自然语言交易和购物触发
    - "帮我买100股苹果" → buy AAPL 100
    - "特斯拉能买吗" → signal TSLA
    - "帮我找便宜的AirPods" → smart_shop AirPods
    '''
    cleaned = (text or '').strip()

    # ── v2.0: 自然语言交易命令 (最高优先级, 防止被购物误匹配) ──
    # 模式: "帮我买100股苹果" / "买入AAPL" / "卖出100股特斯拉" / "买50股NVDA"
    m_trade = re.search(
        r'(?:帮我|请|我要)?(?:买入?|购买|建仓|加仓)\s*(\d+)\s*(?:股|手|份)\s*(.+)',
        cleaned,
    )
    if m_trade:
        qty = m_trade.group(1)
        name_or_ticker = m_trade.group(2).strip()
        ticker = _resolve_chinese_ticker(name_or_ticker)
        if ticker:
            return ('buy', f'{ticker} {qty}')
    # 模式: "买入苹果" / "买苹果股票" (不指定数量，默认用signal分析)
    m_trade2 = re.search(
        r'(?:帮我|请|我要)?(?:买入?|建仓)\s*(.{1,10}?)(?:的?股票|的?期权)?$',
        cleaned,
    )
    if m_trade2 and not re.search(r'个|件|台|部|双|套|箱|瓶|包|盒', cleaned):
        name = _clean_capture(m_trade2.group(1).strip())
        ticker = _resolve_chinese_ticker(name)
        if ticker:
            return ('signal', ticker)
    # 模式: "卖出100股苹果" / "卖掉AAPL"
    m_sell = re.search(
        r'(?:帮我|请|我要)?(?:卖出?|卖掉|清仓|平仓)\s*(\d+)?\s*(?:股|手|份)?\s*(.+)',
        cleaned,
    )
    if m_sell:
        name = m_sell.group(2).strip()
        ticker = _resolve_chinese_ticker(name)
        if ticker:
            qty = m_sell.group(1) or 'all'
            return ('sell', f'{ticker} {qty}')
    # 模式: "苹果/TSLA/英伟达 + 能买吗/怎么样/可以买吗" (中文公司名版)
    m_ask = re.search(r'^(.{1,10}?)(?:能买吗|能不能买|可以买吗|怎么样|值得买吗|能入吗)$', cleaned)
    if m_ask:
        name = _clean_capture(m_ask.group(1).strip())
        ticker = _resolve_chinese_ticker(name)
        if ticker:
            return ('signal', ticker)
    # 模式: "苹果/特斯拉 + 多少钱/股价/价格" (中文公司名报价)
    m_price = re.search(r'^(.{1,10}?)(?:多少钱|股价|价格|行情|现在多少)$', cleaned)
    if m_price:
        name = m_price.group(1).strip()
        ticker = _resolve_chinese_ticker(name)
        if ticker:
            return ('quote', ticker)
    # 模式: "X的K线" / "X图表" / "X走势图" (K线图表请求)
    m_chart = re.search(r'(.{1,10}?)(?:的)?(?:K线|k线|图表|走势图)', cleaned)
    if m_chart:
        name = m_chart.group(1).strip()
        ticker = _resolve_chinese_ticker(name)
        if not ticker:
            m_t = re.search(r'([A-Za-z]{1,5}(?:-USD)?)', name)
            if m_t:
                ticker = m_t.group(1).upper()
        if ticker:
            return ('chart', ticker)
    # 模式: "看看X图" (口语化K线请求)
    m_chart2 = re.search(r'看看(.{1,10}?)(?:的)?图', cleaned)
    if m_chart2:
        name = m_chart2.group(1).strip()
        ticker = _resolve_chinese_ticker(name)
        if not ticker:
            m_t = re.search(r'([A-Za-z]{1,5}(?:-USD)?)', name)
            if m_t:
                ticker = m_t.group(1).upper()
        if ticker:
            return ('chart', ticker)
    # 模式: "分析/看看/研究 + 中文公司名"
    m_ta_cn = re.search(r'(?:分析|技术分析|看看|研究)\s*(.{1,10})$', cleaned)
    if m_ta_cn and not re.search(r'[a-zA-Z]{2,}', m_ta_cn.group(1)):
        name = m_ta_cn.group(1).strip()
        ticker = _resolve_chinese_ticker(name)
        if ticker:
            return ('ta', ticker)

    # ── v2.5: 降价监控 (比购物比价优先级更高) ──
    # 模式: "帮我盯着AirPods，降到800告诉我" / "AirPods降价提醒 800"
    m_pw = re.search(
        r'(?:帮我)?盯着\s*(.{2,30}?)(?:[，,]\s*)?降到\s*(\d+(?:\.\d+)?)',
        cleaned,
    )
    if m_pw:
        keyword = m_pw.group(1).strip()
        price = m_pw.group(2)
        return ('pricewatch_add', f"{keyword}|||{price}")
    # 模式: "XXX降价提醒 800" / "XXX降到800提醒我"
    m_pw2 = re.search(
        r'(.{2,30}?)降(?:价提醒|到)\s*(\d+(?:\.\d+)?)\s*(?:提醒我|告诉我|通知我)?',
        cleaned,
    )
    if m_pw2 and not _resolve_chinese_ticker(m_pw2.group(1).strip()):
        keyword = m_pw2.group(1).strip()
        price = m_pw2.group(2)
        return ('pricewatch_add', f"{keyword}|||{price}")
    # 模式: "降价监控" / "我的监控" / "价格提醒列表"
    if re.search(r'(?:降价监控|我的监控|价格提醒列表|价格监控列表|降价提醒列表)$', cleaned):
        return ('pricewatch_list', '')

    # ── v2.0: 自然语言购物比价 ──
    # 模式: "帮我找便宜的AirPods" / "比较一下XX的价格" / "XX哪里买最便宜"
    m_shop = re.search(
        r'(?:帮我找|帮我搜|帮我比|比较一下|比价|哪里买)\s*(?:个|一个)?\s*(?:便宜的|最便宜的|划算的)?\s*(.{2,30})',
        cleaned,
    )
    if m_shop and not re.search(r'股|期权|基金|债券', cleaned):
        product = m_shop.group(1).strip().rstrip('的价格最便宜便宜')
        if product:
            return ('smart_shop', product)
    m_shop2 = re.search(r'(.{2,20}?)(?:哪里买|在哪买|哪个平台|哪里最便宜|多少钱一个)', cleaned)
    if m_shop2 and not _resolve_chinese_ticker(m_shop2.group(1).strip()):
        product = m_shop2.group(1).strip()
        return ('smart_shop', product)
    m_shop3 = re.search(r'(?:我想买|想买个?|想入手)\s*(.{2,30})', cleaned)
    if m_shop3 and not re.search(r'股|期权|基金', cleaned):
        product = m_shop3.group(1).strip()
        ticker = _resolve_chinese_ticker(product)
        if not ticker:
            return ('smart_shop', product)
    # ── 快递查询 ──
    m_express = re.search(r'(?:查|追踪|跟踪|查询)?快递(?:单号?)?[：:\s]*(.+)', cleaned)
    if m_express:
        return ('express', m_express.group(1).strip())
    # ── 记账 ──
    # "午饭 35" / "记账 35 午饭" / "花了35块买奶茶" / "记一笔 120 停车费"
    m_expense = re.search(
        r'(?:记[一笔账]?|花了?|消费|支出)[：:\s]*(\d+(?:\.\d+)?)\s*(?:块|元|￥)?\s*(.*)',
        cleaned
    )
    if m_expense:
        amount = m_expense.group(1)
        note = m_expense.group(2).strip() or "未备注"
        return ('expense_add', f"{amount}|||{note}")
    # "35 午饭" / "120 停车"（极简模式: 数字开头+备注）
    m_expense2 = re.search(r'^(\d+(?:\.\d+)?)\s*(?:块|元|￥)?\s+(.{1,20})$', cleaned)
    if m_expense2 and not re.search(r'(?:股|买入|卖出|提醒|闹钟)', cleaned):
        amount = m_expense2.group(1)
        note = m_expense2.group(2).strip()
        return ('expense_add', f"{amount}|||{note}")
    # "记账" / "我的账单" / "本月支出" / "支出汇总"
    if re.search(r'(?:我的)?(?:账单|支出|开支|花销|消费)(?:汇总|统计|报告)?$', cleaned):
        return ('expense_summary', '')
    # "撤销记账" / "删除上一笔"
    if re.search(r'(?:撤销|删除|取消)(?:上)?(?:一)?(?:笔)?(?:记账|支出|开支)', cleaned):
        return ('expense_undo', '')

    # ── 导出记账/闲鱼 ──
    # "导出记账" / "导出账单" / "导出记账90天"
    m_export_exp = re.search(r'导出(?:记账|账单|支出|开支)\s*(\d+)?(?:天)?', cleaned)
    if m_export_exp:
        days = m_export_exp.group(1) or "30"
        return ('export_expenses', days)
    # "导出闲鱼" / "闲鱼报表导出" / "导出闲鱼订单30天"
    m_export_xy = re.search(r'(?:导出闲鱼|闲鱼(?:报表|订单)?导出)\s*(?:订单)?\s*(\d+)?(?:天)?', cleaned)
    if m_export_xy:
        days = m_export_xy.group(1) or "90"
        return ('export_xianyu', days)

    # ── 收入记录 ──
    # "收入5000元" / "进账8000" / "工资到账5000" / "收到3000红包"
    m_income = re.search(
        r'(?:收入|进账|到账|收到|入账)[：:\s]*(\d+(?:\.\d+)?)\s*(?:块|元|￥)?\s*(.*)',
        cleaned
    )
    if m_income:
        amount = m_income.group(1)
        note = m_income.group(2).strip() or "未备注"
        return ('income_add', f"{amount}|||{note}")
    # "工资到账5000" / "薪资5000到账" / "工资5000"
    m_income2 = re.search(
        r'(?:工资|薪资|薪水|月薪)(?:到账)?[：:\s]*(\d+(?:\.\d+)?)',
        cleaned
    )
    if m_income2:
        amount = m_income2.group(1)
        return ('income_add', f"{amount}|||工资")

    # ── 月预算 ──
    # "月预算5000" / "设预算8000" / "每月花5000以内"
    m_budget = re.search(
        r'(?:月预算|设预算|每月(?:预算|花|消费))\s*(\d+(?:\.\d+)?)\s*(?:块|元|￥|以内)?',
        cleaned
    )
    if m_budget:
        return ('budget_set', m_budget.group(1))

    # ── 月度汇总 ──
    # "本月账单" / "这个月花了多少" / "月度报告" / "3月账单"
    m_monthly = re.search(
        r'(?:本月|这个月|这月|上个?月|月度|(\d{1,2})月)(?:花了多少|账单|报告|汇总|财务)',
        cleaned
    )
    if m_monthly:
        month_num = m_monthly.group(1) if m_monthly.group(1) else ""
        return ('monthly_summary', month_num)
    if re.search(r'(?:月度|本月|这个月)(?:报告|汇总|总结|财务)$', cleaned):
        return ('monthly_summary', '')

    # ── 预算检查 ──
    # "预算还剩多少" / "超预算了吗" / "预算情况"
    if re.search(r'(?:预算|月预算)(?:还剩|剩多少|情况|超了|超预算|还有多少|够不够)', cleaned):
        return ('budget_check', '')

    # ── 账单追踪 (话费/水电费余额检测提醒) ──
    # 9.1 更新余额: "话费还剩30块" / "电费余额120" / "水费剩15.5元"
    m_bill_update = re.search(
        r'(话费|电费|水费|燃气费|煤气费|宽带|网费|手机费|电话费|电力)'
        r'(?:还)?(?:剩|余额|剩余|还有|只剩|就剩)\s*'
        r'(\d+(?:\.\d+)?)\s*(?:块|元|￥)?',
        cleaned,
    )
    if m_bill_update:
        bill_type_cn = m_bill_update.group(1)
        balance = m_bill_update.group(2)
        return ('bill_update_nlp', f"{bill_type_cn}|||{balance}")
    # 9.2 添加追踪: "帮我盯着话费" / "话费低于30提醒我" / "帮我追踪电费"
    m_bill_add = re.search(
        r'(?:帮我|请)?(?:盯着|追踪|监控|关注)\s*(话费|电费|水费|燃气费|煤气费|宽带|网费|手机费|电话费)'
        r'(?:.*?低于\s*(\d+(?:\.\d+)?)\s*(?:块|元|￥)?)?',
        cleaned,
    )
    if m_bill_add:
        bill_type_cn = m_bill_add.group(1)
        threshold = m_bill_add.group(2) or "30"
        return ('bill_add_nlp', f"{bill_type_cn}|||{threshold}")
    m_bill_add2 = re.search(
        r'(话费|电费|水费|燃气费|煤气费|宽带|网费|手机费|电话费)'
        r'低于\s*(\d+(?:\.\d+)?)\s*(?:块|元|￥)?(?:.*?提醒)',
        cleaned,
    )
    if m_bill_add2:
        bill_type_cn = m_bill_add2.group(1)
        threshold = m_bill_add2.group(2)
        return ('bill_add_nlp', f"{bill_type_cn}|||{threshold}")
    # 9.3 列表查看: "我的账单" / "账单列表" / "话费水电费"
    if re.search(r'(?:我的)?(?:生活)?账单(?:列表|追踪)?$|话费水电费|水电费', cleaned):
        return ('bill_list', '')
    # 9.4 查询: "查话费" / "查电费" / "查水费"
    m_bill_query = re.search(r'查(话费|电费|水费|燃气费|煤气费|宽带|网费)', cleaned)
    if m_bill_query:
        return ('bill_query', m_bill_query.group(1))
    # ── 盈透订单/账户 (放在基础命令之前，避免被"状态"误匹配) ──
    if re.search('我的订单|盈透订单|订单状态', cleaned):
        return ('iorders', '')
    if re.search('我的账户|盈透账户|账户余额', cleaned):
        return ('iaccount', '')
    # ── 基础命令 (fullmatch→search容错: 支持"帮我XX"/"看看XX"等自然前缀) ──
    _PRE = r'(?:帮我|看看|查看|来个|来条|给我|打开|查一下|看一下)?'
    _SUF = r'(?:吧|啊|呢|呀|一下|看看)?$'
    if re.search(_PRE + r'(?:开始|帮助|菜单|命令|指令|使用说明|你好|hi|hello|嗨|在吗|你能做什么|能做什么|怎么用|如何使用|有什么功能|功能列表|你会什么)' + _SUF, cleaned, re.IGNORECASE):
        return ('start', '')
    if re.search(_PRE + r'(?:清空|清空对话|重置对话|重置会话|清空聊天|清空记录|清除记录|删掉对话|重新开始)' + _SUF, cleaned):
        return ('clear', '')
    if re.search(_PRE + r'(?:状态|查看状态|机器人状态|系统状态|运行状态|你的状态)' + _SUF, cleaned):
        return ('status', '')
    if re.search(_PRE + r'(?:配置|配置状态|当前配置|运行配置)' + _SUF, cleaned):
        return ('config', '')
    if re.search(_PRE + r'(?:成本|配额|用量|成本状态|配额状态|花了多少钱|还有多少额度)' + _SUF, cleaned):
        return ('cost', '')
    if re.search(_PRE + r'(?:上下文|上下文状态|上下文用量)' + _SUF, cleaned):
        return ('context', '')
    if re.search(_PRE + r'(?:压缩|压缩上下文|整理上下文)' + _SUF, cleaned):
        return ('compact', '')
    if re.search(_PRE + r'(?:新闻|科技早报|早报|今日新闻|最新消息|今天新闻)' + _SUF, cleaned):
        return ('news', '')
    if re.search(_PRE + r'(?:指标|运行指标|监控指标|运行数据)' + _SUF, cleaned):
        return ('metrics', '')
    if re.search(_PRE + r'(?:分流|分流规则|路由规则|话题分流|多bot分流|多机器人分流)' + _SUF, cleaned):
        return ('lanes', '')
    if re.search(r'(画|绘|画一|画个|画张|生成图片)', cleaned):
        return ('draw', cleaned)
    if re.search(r'(我的记忆|查记忆|记忆管理)', cleaned):
        return ('memory', '')
    if re.search(r'(设置|偏好设置|我的设置)', cleaned):
        return ('settings', '')
    if re.search('执行场景|自动化菜单|ops帮助', cleaned):
        return ('ops_help', '')
    if re.search('整理邮箱|邮件整理|邮箱分类', cleaned):
        return ('ops_email', '')
    if re.search('执行简报|行业简报|今日简报', cleaned):
        return ('ops_brief', '')
    if re.search('最重要.{0,2}3件事|任务优先级|今日任务', cleaned):
        return ('ops_task_top', '')
    if re.search(r'赏金猎人|自动接单|接单机器人|\bbounty\b', cleaned, re.IGNORECASE):
        return ('ops_bounty_run', '')
    m_bounty_scan = re.search(r'(?:扫赏金|扫描赏金|找赏金|赏金扫描)\s*(.*)', cleaned)
    if m_bounty_scan:
        kw = (m_bounty_scan.group(1) or '').strip()
        return ('ops_bounty_scan', kw)
    if re.search(_PRE + r'(?:赏金列表|赏金机会|赏金看板|有什么赏金)' + _SUF, cleaned):
        return ('ops_bounty_list', '')
    if re.search(_PRE + r'(?:赏金top|赏金排行|高收益赏金|赏金排行榜)' + _SUF, cleaned):
        return ('ops_bounty_top', '')
    if re.search(_PRE + r'(?:开工赚钱|打开赏金机会|开赏金链接|我要赚钱)' + _SUF, cleaned):
        return ('ops_bounty_open', '')
    m_tweet_plan = re.search(r'(?:推文计划|分析推文|推文执行计划)\s+(.+)', cleaned)
    if m_tweet_plan:
        return ('ops_tweet_plan', m_tweet_plan.group(1).strip())
    m_tweet_run = re.search(r'(?:执行推文|推文执行|推文赚钱|跟着推文赚钱)\s+(.+)', cleaned)
    if m_tweet_run:
        return ('ops_tweet_run', m_tweet_run.group(1).strip())
    m_docs_search = re.search(r'(?:文档检索|文档搜索|搜文档)\s+(.+)', cleaned)
    if m_docs_search:
        return ('ops_docs_search', m_docs_search.group(1).strip())
    m_docs_index = re.search(r'(?:建立文档索引|索引文档)\s*(.*)', cleaned)
    if m_docs_index and re.search('文档', cleaned):
        target = (m_docs_index.group(1) or '.').strip() or '.'
        return ('ops_docs_index', target)
    m_meeting = re.search(r'(?:会议纪要|总结会议)\s+(.+)', cleaned)
    if m_meeting:
        return ('ops_meeting', m_meeting.group(1).strip())
    m_content = re.search(r'(?:社媒选题|内容选题|写作选题)\s*(.*)', cleaned)
    if m_content and re.search('选题', cleaned):
        keyword = (m_content.group(1) or 'AI').strip() or 'AI'
        return ('ops_content', keyword)
    m_social_plan = re.search(r'(?:社媒计划|今日发什么)\s*(.*)', cleaned)
    if m_social_plan and re.search('计划|发什么', cleaned):
        return ('social_plan', (m_social_plan.group(1) or '').strip())
    m_social_repost = re.search(r'(?:双平台改写|改写双平台|改写成双平台|双平台草稿)\s*(.*)', cleaned)
    if m_social_repost:
        return ('social_repost', (m_social_repost.group(1) or '').strip())
    m_dualpost = re.search(r'(?:双平台发文|一键双发|双平台一键发文)\s*(.*)', cleaned)
    if m_dualpost:
        return ('dualpost', (m_dualpost.group(1) or '').strip())
    if re.search(_PRE + r'(?:数字生命首发|首发包|社媒首发包|数字生命人设首发|做个首发)' + _SUF, cleaned):
        return ('social_launch', '')
    if re.search(_PRE + r'(?:当前社媒人设|社媒人设|数字生命人设|当前人设|我的人设)' + _SUF, cleaned):
        return ('social_persona', '')
    m_topic = re.search('(?:研究|分析|看看|学习)(.+?)(?:题材|方向|内容)', cleaned)
    if m_topic:
        return ('social_topic', m_topic.group(1).strip())
    m_xhs = re.search('(?:给我|帮我)?发(?:一篇)?(.+?)(?:类)?(?:文章|内容)?到小红书', cleaned)
    if m_xhs:
        return ('social_xhs', m_xhs.group(1).strip())
    m_x = re.search('(?:给我|帮我)?发(?:一篇)?(.+?)(?:类)?(?:文章|内容)?到(?:x|推特|推文)', cleaned, re.IGNORECASE)
    if m_x:
        return ('social_x', m_x.group(1).strip())
    m_dual = re.search('(?:给我|帮我)?发(?:一篇)?(.+?)(?:类)?(?:文章|内容)?(?:双平台|同时发|发到两个平台)', cleaned)
    if m_dual:
        return ('social_post', m_dual.group(1).strip())
    if re.search(_PRE + r'(?:一键发文|热点发文|热点一键发文|蹭热点发文|自动发文|发个热点)' + _SUF, cleaned):
        return ('social_hotpost', '')
    m_hotpost = re.search(r'(?:一键发文|热点发文|蹭热点发文|自动发文)\s+(.+)', cleaned)
    if m_hotpost:
        return ('social_hotpost', m_hotpost.group(1).strip())
    # v2.0: 社媒报告 NL 触发
    if re.search('社媒报告|社交报告|发文报告|运营报告|社媒数据', cleaned):
        return ('social_report', '')
    # ── 社媒日历 ──
    if re.search('发文日历|内容日历|发文计划', cleaned):
        return ('social_calendar', '')
    # v4.0: 闲鱼 BI 报表 NL 触发 — 报告/排行/高峰/转化
    if re.search('闲鱼报告|闲鱼数据|闲鱼报表|闲鱼分析|商品排行|哪个商品卖得好|热销排行|咨询高峰|什么时候咨询最多|转化率|转化漏斗|闲鱼转化', cleaned):
        return ('xianyu_report', '')
    # v5.0: 闲鱼回复风格 / FAQ 管理 NL 触发
    if re.search('闲鱼风格|闲鱼回复风格|客服风格|闲鱼客服风格|AI客服风格', cleaned):
        return ('xianyu_style_show', '')
    if re.search('闲鱼常见问题|闲鱼FAQ|闲鱼faq', cleaned):
        return ('xianyu_style_faq_list', '')
    # ── 语音播报 ──
    m_voice = re.search(r'(?:念出来|语音播报|朗读)\s*(.*)', cleaned)
    if m_voice:
        return ('voice', (m_voice.group(1) or '').strip())
    # ── AI写作 ──
    if re.search('写小说|续写小说|AI写作', cleaned):
        return ('novel', '')
    # ── 闲鱼发货 ──
    if re.search('发货管理|闲鱼发货', cleaned):
        return ('ship', '')
    # v3.0: 综合周报 NL 触发
    if re.search(_PRE + r'(?:周报|本周总结|每周总结|本周汇总|综合周报|这周怎么样)' + _SUF, cleaned):
        return ('weekly', '')
    m_monitor_add = re.search(r'(?:添加资讯监控|新增资讯监控|监控关键词)\s+(.+)', cleaned)
    if m_monitor_add:
        return ('ops_monitor_add', m_monitor_add.group(1).strip())
    if re.search(_PRE + r'(?:资讯监控列表|新闻监控列表|监控了什么)' + _SUF, cleaned):
        return ('ops_monitor_list', '')
    if re.search(_PRE + r'(?:运行资讯监控|扫描资讯监控|立即扫描资讯监控|跑一下监控|扫描一下)' + _SUF, cleaned):
        return ('ops_monitor_run', '')
    # ── 提醒系统 v2.0: 重复提醒 + 自然语言时间 ──

    # 8.1 提醒管理: "我的提醒" / "提醒列表" / "查看提醒"
    if re.search(r'(?:我的|查看|列出)?提醒(?:列表|清单)?$', cleaned):
        return ('ops_life_remind', 'list')

    # 8.2 取消提醒: "取消提醒 #3" / "删除提醒3"
    m_cancel = re.search(r'(?:取消|删除)提醒\s*#?(\d+)', cleaned)
    if m_cancel:
        return ('ops_life_remind', f"cancel|||{m_cancel.group(1)}")

    # 8.3 重复提醒: "每天早上9点提醒我吃药"
    m_recur = re.search(
        r'(每天|每周[一二三四五六日天]|每小时|每月\d+[号日]?|工作日|每\d+分钟)'
        r'(?:.*?(\d{1,2}[点时:：]\d{0,2}分?))?'
        r'\s*提醒我\s+(.+)',
        cleaned,
    )
    if m_recur:
        freq = m_recur.group(1)  # "每天" / "每周一" / "每小时"
        time_part = m_recur.group(2) or ""  # "9点" / "15:30" / ""
        content = _clean_capture(m_recur.group(3))
        # 映射频率到 recurrence_rule
        rule = freq
        if freq == "每天":
            rule = "daily"
        elif freq == "每小时":
            rule = "hourly"
        elif freq == "工作日":
            rule = "weekdays"
        elif freq.startswith("每周"):
            rule = freq  # _calc_next_occurrence 直接支持 "每周一" 格式
        elif freq.startswith("每月"):
            rule = freq
        elif "分钟" in freq:
            rule = freq.replace("每", "").replace("分钟", "min")
        return ('ops_life_remind', f"recur|||{rule}|||{time_part}|||{content}")

    # 8.4 自然语言时间提醒: "明天下午3点提醒我开会" / "下周一提醒我交报告"
    m_time_remind = re.search(
        r'(.+?)提醒我\s+(.+)',
        cleaned,
    )
    if m_time_remind:
        time_text = m_time_remind.group(1).strip()
        content = _clean_capture(m_time_remind.group(2))
        # 排除纯数字分钟(已被下面的 m_remind 处理)
        if not re.match(r'^\d+\s*分钟后?$', time_text):
            return ('ops_life_remind', f"time|||{time_text}|||{content}")

    # 8.5 经典模式(兜底): "30分钟后提醒我开会" / "提醒我开会"
    m_remind = re.search(r'(\d+)\s*分钟后提醒我\s+(.+)', cleaned)
    if m_remind:
        return ('ops_life_remind', f'''{m_remind.group(1)}|||{m_remind.group(2).strip()}''')
    m_remind_default = re.search(r'提醒我\s+(.+)', cleaned)
    if m_remind_default:
        return ('ops_life_remind', f'''30|||{m_remind_default.group(1).strip()}''')
    m_project = re.search(r'(?:项目周报|生成项目周报)\s*(.*)', cleaned)
    if m_project and re.search('项目周报', cleaned):
        target = (m_project.group(1) or '.').strip() or '.'
        return ('ops_project', target)
    m_dev = re.search(r'(?:开发流程|执行开发流程|跑开发流程)\s*(.*)', cleaned)
    if m_dev and re.search('开发流程', cleaned):
        target = (m_dev.group(1) or '.').strip() or '.'
        return ('ops_dev', target)
    if re.search('(开始|自动|帮我|一键).{0,2}投资|找.{0,2}机会|自动交易|帮我(赚钱|炒股|交易)|今天买什么|有什么(机会|可以买)', cleaned):
        return ('auto_invest', cleaned)
    if re.search('扫描|扫一下|扫一扫|看看市场|市场扫描|全市场', cleaned):
        return ('scan', '')
    m = re.search(r'(?:分析|技术分析|看看|研究)\s*([A-Za-z]{1,5}(?:-USD)?)', cleaned)
    if m:
        return ('ta', m.group(1).upper())
    m = re.search(r'([A-Za-z]{1,5})\s*(?:信号|买卖|怎么样|能买吗|能不能买)', cleaned)
    if m:
        return ('signal', m.group(1).upper())
    m = re.search(r'([A-Za-z]{1,5})\s*(?:多少钱|股价|价格|行情)', cleaned)
    if m:
        return ('quote', m.group(1).upper())
    m = re.search(r'(?:查|看).{0,2}(?:行情|价格)\s*([A-Za-z]{1,5})?', cleaned)
    if m and m.group(1):
        return ('quote', m.group(1).upper())
    if re.search('市场概览|大盘|今天行情|行情怎么样|市场怎么样', cleaned):
        return ('market', '')
    if re.search('我的?(持仓|仓位|组合|资产)|看看(持仓|仓位)|投资组合', cleaned):
        return ('portfolio', '')
    if re.search('(IBKR|盈透|真实|实盘).{0,2}(持仓|仓位)', cleaned):
        return ('positions', '')
    if re.search('我的自选股|自选股列表|关注列表|自选股', cleaned):
        return ('watchlist', '')
    if re.search('绩效|战绩|成绩|表现|胜率|盈亏|收益率|夏普|回撤', cleaned):
        return ('performance', '')
    if re.search('复盘历史|过往复盘|复盘记录', cleaned):
        return ('review_history', '')
    if re.search('复盘|总结.{0,2}(今天|交易)|回顾|检讨|反思', cleaned):
        return ('review', '')
    if re.search('我买了什么|交易记录|交易历史', cleaned):
        return ('trades', '')
    if re.search('交易(日志)|日志|看看(记录|日志)', cleaned):
        return ('journal', '')
    if re.search('预测准确率|AI准确率|研判准确率|各?AI.{0,2}表现|预测.{0,2}准不准', cleaned):
        return ('accuracy', '')
    if re.search('权益曲线|收益曲线|资金曲线|净值曲线', cleaned):
        return ('equity', '')
    if re.search('目标进度|盈利目标|目标达成|目标完成', cleaned):
        return ('targets', '')
    if re.search('风控|风险(状态|管理)?|熔断', cleaned):
        return ('risk', '')
    if re.search('持仓监控|监控(状态)?|止损(状态)?|止盈', cleaned):
        return ('monitor', '')
    if re.search('交易系统|系统状态|全部状态', cleaned):
        return ('tradingsystem', '')
    if re.search('启动自动|开启自动|自动交易启动|开始自动', cleaned):
        return ('autotrader_start', '')
    if re.search('停止自动|关闭自动|自动交易停止', cleaned):
        return ('autotrader_stop', '')

    # ── 高级回测分析（优先于普通回测匹配） ──
    # 蒙特卡洛模拟: "蒙特卡洛 AAPL" / "蒙特卡洛模拟 苹果"
    m_mc = re.search(r'蒙特卡洛(?:模拟)?\s*([A-Za-z\-]{1,10}|\S{1,6})', cleaned)
    if m_mc:
        raw = m_mc.group(1).strip()
        sym = raw.upper() if re.fullmatch(r'[A-Za-z\-]+', raw) else ''
        if not sym:
            sym = _resolve_chinese_ticker(raw)
        if sym:
            return ('backtest', 'monte %s' % sym)
    # 参数优化: "参数优化 AAPL" / "优化参数 苹果"
    m_opt = re.search(r'(?:参数优化|优化参数)\s*([A-Za-z\-]{1,10}|\S{1,6})', cleaned)
    if m_opt:
        raw = m_opt.group(1).strip()
        sym = raw.upper() if re.fullmatch(r'[A-Za-z\-]+', raw) else ''
        if not sym:
            sym = _resolve_chinese_ticker(raw)
        if sym:
            return ('backtest', 'optimize %s' % sym)
    # 前进分析: "前进分析 AAPL" / "walk forward 苹果"
    m_wf = re.search(r'(?:前进分析|walk\s*forward)\s*([A-Za-z\-]{1,10}|\S{1,6})', cleaned)
    if m_wf:
        raw = m_wf.group(1).strip()
        sym = raw.upper() if re.fullmatch(r'[A-Za-z\-]+', raw) else ''
        if not sym:
            sym = _resolve_chinese_ticker(raw)
        if sym:
            return ('backtest', 'walkforward %s' % sym)

    m_bt = re.search(r'(?:回测|测试策略|backtest)\s*([A-Za-z\-]{1,10})?', cleaned)
    if m_bt:
        sym = (m_bt.group(1) or '').strip().upper()
        return ('backtest', sym)
    if re.search('再平衡|调仓|rebalance|配置组合|目标配置', cleaned):
        return ('rebalance', '')
    m = re.search(r'(?:投资|讨论|分析).{0,2}(?:一下|下)?\s*(.{2,})', cleaned)
    if m and re.search('投资|讨论', cleaned):
        topic = _clean_capture(m.group(1).strip())
        if len(topic) >= 2:
            return ('invest', topic)

    # ── 最终降级: "你是不是想说…" 模糊建议 (Gap 3) ──
    suggestion = _suggest_command(cleaned)
    if suggestion:
        action, keyword, label = suggestion
        return ('suggest', f'{action}|||{keyword}|||{label}')


class ChineseNLPMixin:
    """中文自然语言命令的 Bot 级方法 — 判断是否 @当前 bot + 分发到命令处理器"""

    @staticmethod
    def _is_directed_to_current_bot(text="", chat_type="", username=""):
        if chat_type == "private":
            return True
        if not username:
            return False
        uname = username.strip().lstrip("@").lower()
        if not uname or not text:
            return False
        return f"@{uname}" in text.lower()

    async def _dispatch_chinese_action(self, update = None, context = None, action_type="", action_arg=""):
        """分发中文自然语言命令到对应的命令处理器"""
        if not update or not action_type:
            return

        # 构造 context.args（按空格拆分，保持与 Telegram 命令行为一致）
        context.args = action_arg.split() if action_arg else []

        # 命令映射表 — 将 NLP 匹配结果路由到实际命令
        dispatch_map = {
            # ── 基础命令 ──
            "start": self.cmd_start,
            "clear": self.cmd_clear,
            "status": self.cmd_status,
            "config": self.cmd_config,
            "cost": self.cmd_cost,
            "context": self.cmd_context,
            "compact": self.cmd_compact,
            "news": self.cmd_news,
            "metrics": self.cmd_metrics,
            "lanes": self.cmd_lane,
            "memory": self.cmd_memory,
            "settings": self.cmd_settings,
            "draw": self.cmd_draw,
            # ── 执行场景 ──
            "ops_help": self.cmd_ops,
            "ops_brief": self.cmd_brief,
            "hot": self.cmd_hotpost,
            "post": self.cmd_post,
            "social_report": self.cmd_social_report,
            "xianyu_report": self.cmd_xianyu_report,
            "weekly": self.cmd_weekly,
            # ── 投资 & 交易 ──
            "invest": self.cmd_invest,
            "auto_invest": self.cmd_invest,
            "quote": self.cmd_quote,
            "market": self.cmd_market,
            "scan": self.cmd_scan,
            "ta": self.cmd_ta,
            "signal": self.cmd_signal,
            "portfolio": self.cmd_portfolio,
            "positions": self.cmd_ipositions,
            "performance": self.cmd_performance,
            "review": self.cmd_review,
            "review_history": self.cmd_review_history,
            "journal": self.cmd_journal,
            "accuracy": self.cmd_accuracy,
            "equity": self.cmd_equity,
            "targets": self.cmd_targets,
            "buy": self.cmd_buy,
            "sell": self.cmd_sell,
            "risk": self.cmd_risk,
            "monitor": self.cmd_monitor,
            "tradingsystem": self.cmd_tradingsystem,
            "backtest": self.cmd_backtest,
            "rebalance": self.cmd_rebalance,
            "watchlist": self.cmd_watchlist,
            "trades": self.cmd_trades,
            "chart": self.cmd_chart,
            "iorders": self.cmd_iorders,
            "iaccount": self.cmd_iaccount,
            # ── v2.0: 自然语言购物 ──
            "smart_shop": self._cmd_smart_shop,
            # ── 降价监控 ──
            "pricewatch_list": self.cmd_pricewatch,
            # ── 账单追踪 ──
            "bill_list": self.cmd_bill,
            # ── 社媒 ──
            "social_plan": self.cmd_social_plan,
            "social_repost": self.cmd_social_repost,
            "social_launch": self.cmd_social_launch,
            "social_persona": self.cmd_social_persona,
            "social_topic": self.cmd_topic,
            "social_xhs": self.cmd_xhs,
            "social_x": self.cmd_xpost,
            "social_post": self.cmd_post,
            "social_hotpost": self.cmd_hotpost,
            "social_calendar": self.cmd_social_calendar,
            "dualpost": self.cmd_post,  # fix: cmd_dual_post doesn't exist, route to cmd_post (双平台)
            # ── 语音/写作/发货 ──
            "voice": self.cmd_voice,
            "novel": self.cmd_novel,
            "ship": self.cmd_ship,
        }

        handler = dispatch_map.get(action_type)
        if handler:
            try:
                await handler(update, context)
            except Exception as e:
                logger.warning("[ChineseNLP] 分发 %s 失败: %s", action_type, e)
            return

        # 带参数的特殊命令
        try:
            if action_type == "express":
                try:
                    from src.tools.free_apis import query_express
                    result = await query_express(action_arg)
                    await update.message.reply_text(result if isinstance(result, str) else str(result))
                except ImportError:
                    await update.message.reply_text("快递查询功能暂未配置")
                except Exception as e:  # noqa: F841
                    await update.message.reply_text("查询失败，请稍后再试")
                return
            elif action_type == 'expense_add':
                user = update.effective_user
                chat_id = update.effective_chat.id if update.effective_chat else 0
                parts = action_arg.split("|||", 1)
                amount = float(parts[0])
                note = parts[1] if len(parts) > 1 else ""
                from src.execution.life_automation import add_expense
                result = add_expense(user.id, amount, note, chat_id=chat_id)
                if result.get("success"):
                    await update.message.reply_text(
                        f"✅ 已记录: ¥{amount} {note}\n💡 说「我的账单」查看汇总"
                    )
                else:
                    await update.message.reply_text("记账失败，请稍后再试")
                return
            elif action_type == 'expense_summary':
                user = update.effective_user
                from src.execution.life_automation import get_expense_summary
                summary = get_expense_summary(user.id)
                if not summary.get("success") or summary.get("total_count", 0) == 0:
                    await update.message.reply_text("📊 还没有记录，试试说「午饭 35」开始记账")
                    return
                lines = [f"📊 近{summary['days']}天支出 | 共 ¥{summary['total_amount']}"]
                if summary.get("categories"):
                    lines.append("")
                    for cat in summary["categories"][:5]:
                        lines.append(f"  {cat['name']}: ¥{cat['amount']} ({cat['count']}笔)")
                if summary.get("recent"):
                    lines.append("\n📝 最近记录:")
                    for r in summary["recent"]:
                        lines.append(f"  {r['time']} ¥{r['amount']} {r['note']}")
                await update.message.reply_text("\n".join(lines))
                return
            elif action_type == 'expense_undo':
                user = update.effective_user
                from src.execution.life_automation import delete_last_expense
                if delete_last_expense(user.id):
                    await update.message.reply_text("✅ 已删除最近一笔记录")
                else:
                    await update.message.reply_text("没有可删除的记录")
                return
            # ── 导出记账/闲鱼 ──
            elif action_type == 'export_expenses':
                context.args = ["expenses", action_arg]
                await self.cmd_export(update, context)
                return
            elif action_type == 'export_xianyu':
                context.args = ["xianyu", action_arg]
                await self.cmd_export(update, context)
                return
            # ── 收入记录 ──
            elif action_type == 'income_add':
                user = update.effective_user
                chat_id = update.effective_chat.id if update.effective_chat else 0
                parts = action_arg.split("|||", 1)
                amount = float(parts[0])
                note = parts[1] if len(parts) > 1 else ""
                from src.execution.life_automation import add_income
                result = add_income(user.id, amount, note, chat_id=chat_id)
                if result.get("success"):
                    cat = result.get("category", "其他")
                    await update.message.reply_text(
                        f"✅ 已记录收入: ¥{amount} {note}\n"
                        f"📂 分类: {cat}\n"
                        f"💡 说「本月账单」查看月度报告"
                    )
                else:
                    await update.message.reply_text(
                        result.get("error", "收入记录失败，请稍后再试")
                    )
                return
            # ── 设定月预算 ──
            elif action_type == 'budget_set':
                user = update.effective_user
                budget = float(action_arg)
                from src.execution.life_automation import set_monthly_budget
                result = set_monthly_budget(user.id, budget)
                if result.get("success"):
                    await update.message.reply_text(
                        f"✅ 月预算已设为 ¥{budget:,.0f}\n"
                        f"💡 每天 20:00 自动检查超支情况"
                    )
                else:
                    await update.message.reply_text(
                        result.get("error", "设定预算失败")
                    )
                return
            # ── 月度财务汇总 ──
            elif action_type == 'monthly_summary':
                user = update.effective_user
                from src.execution.life_automation import (
                    get_monthly_summary, format_monthly_report,
                )
                # 解析月份参数
                year_month = None
                if action_arg:
                    from datetime import datetime as _dt
                    try:
                        month_num = int(action_arg)
                        year = _dt.now().year
                        year_month = f"{year}-{month_num:02d}"
                    except (ValueError, TypeError) as e:  # noqa: F841
                        pass
                summary = get_monthly_summary(user.id, year_month=year_month)
                if not summary.get("success") or (
                    summary.get("total_expense", 0) == 0 and
                    summary.get("total_income", 0) == 0
                ):
                    await update.message.reply_text(
                        "📊 本月还没有收支记录\n"
                        "💡 试试说「午饭 35」记支出，「收入5000」记收入"
                    )
                    return
                report = format_monthly_report(summary)
                await update.message.reply_text(report)
                return
            # ── 预算检查 ──
            elif action_type == 'budget_check':
                user = update.effective_user
                from src.execution.life_automation import check_budget_alert
                is_over, msg = check_budget_alert(user.id)
                await update.message.reply_text(msg)
                return
            # ── 账单追踪 NLP 分发 ──
            elif action_type == 'bill_update_nlp':
                # "话费还剩30块" → 自动更新余额
                user = update.effective_user
                chat_id = update.effective_chat.id if update.effective_chat else 0
                parts = action_arg.split("|||", 1)
                bill_type_cn = parts[0]
                balance = float(parts[1]) if len(parts) > 1 else 0
                from src.execution.life_automation import (
                    resolve_bill_type, find_bill_by_type, update_bill_balance,
                    add_bill_account, BILL_TYPE_EMOJI, BILL_TYPE_LABEL,
                )
                acct_type = resolve_bill_type(bill_type_cn)
                if not acct_type:
                    await update.message.reply_text(f"❌ 不认识「{bill_type_cn}」类型")
                    return
                # 查找已有追踪
                existing = find_bill_by_type(user.id, acct_type)
                if existing:
                    result = update_bill_balance(existing["id"], balance, user_id=user.id)
                    if result.get("success"):
                        emoji = BILL_TYPE_EMOJI.get(acct_type, "📄")
                        label = BILL_TYPE_LABEL.get(acct_type, acct_type)
                        msg = f"✅ {emoji} {label}余额已更新: ¥{balance:.1f}"
                        if result.get("is_low"):
                            msg += f"\n⚠️ 低于阈值 ¥{result['threshold']:.0f}，请注意充值！"
                            # 发布 BILL_DUE 事件
                            try:
                                from src.core.event_bus import get_event_bus, EventType
                                import asyncio
                                bus = get_event_bus()
                                asyncio.ensure_future(bus.publish(
                                    EventType.BILL_DUE,
                                    {
                                        "user_id": str(user.id), "chat_id": str(chat_id),
                                        "account_type": acct_type,
                                        "account_name": existing.get("account_name", ""),
                                        "balance": balance,
                                        "threshold": result["threshold"],
                                    },
                                    source="nlp_bill_update",
                                ))
                            except Exception as e:
                                logger.debug("静默异常: %s", e)
                        await update.message.reply_text(msg)
                    else:
                        await update.message.reply_text(f"❌ 更新失败: {result.get('error', '')}")
                else:
                    # 没有追踪，自动创建一个
                    result = add_bill_account(
                        user_id=user.id, chat_id=chat_id,
                        account_type=acct_type, low_threshold=30,
                    )
                    if result.get("success"):
                        update_bill_balance(result["account_id"], balance, user_id=user.id)
                        emoji = BILL_TYPE_EMOJI.get(acct_type, "📄")
                        label = BILL_TYPE_LABEL.get(acct_type, acct_type)
                        await update.message.reply_text(
                            f"✅ 自动创建了{emoji} {label}追踪，余额: ¥{balance:.1f}\n"
                            f"⚠️ 默认低于 ¥30 提醒，可用 /bill 调整"
                        )
                    else:
                        await update.message.reply_text(f"❌ {result.get('error', '失败')}")
                return
            elif action_type == 'bill_add_nlp':
                # "帮我盯着话费" → 添加追踪
                user = update.effective_user
                chat_id = update.effective_chat.id if update.effective_chat else 0
                parts = action_arg.split("|||", 1)
                bill_type_cn = parts[0]
                threshold = float(parts[1]) if len(parts) > 1 else 30
                from src.execution.life_automation import (
                    resolve_bill_type, add_bill_account,
                    BILL_TYPE_EMOJI, BILL_TYPE_LABEL,
                )
                acct_type = resolve_bill_type(bill_type_cn)
                if not acct_type:
                    await update.message.reply_text(f"❌ 不认识「{bill_type_cn}」类型")
                    return
                result = add_bill_account(
                    user_id=user.id, chat_id=chat_id,
                    account_type=acct_type, low_threshold=threshold,
                )
                if result.get("success"):
                    emoji = BILL_TYPE_EMOJI.get(acct_type, "📄")
                    label = BILL_TYPE_LABEL.get(acct_type, acct_type)
                    await update.message.reply_text(
                        f"✅ {emoji} {label}追踪已添加\n"
                        f"⚠️ 低于 ¥{threshold:.0f} 时提醒\n\n"
                        f"💡 说「{label}还剩xx块」可更新余额"
                    )
                else:
                    await update.message.reply_text(f"❌ {result.get('error', '添加失败')}")
                return
            elif action_type == 'bill_query':
                # "查话费" → 查余额或提示添加
                user = update.effective_user
                from src.execution.life_automation import (
                    resolve_bill_type, find_bill_by_type,
                    BILL_TYPE_EMOJI, BILL_TYPE_LABEL,
                )
                acct_type = resolve_bill_type(action_arg)
                if not acct_type:
                    await update.message.reply_text(f"❌ 不认识「{action_arg}」类型")
                    return
                existing = find_bill_by_type(user.id, acct_type)
                emoji = BILL_TYPE_EMOJI.get(acct_type, "📄")
                label = BILL_TYPE_LABEL.get(acct_type, acct_type)
                if existing:
                    last_updated = existing.get("balance", 0)
                    balance = existing["balance"]
                    is_low = balance <= existing["low_threshold"]
                    msg = f"{emoji} {label}余额: ¥{balance:.1f}"
                    if is_low:
                        msg += " ⚠️ 低于阈值!"
                    msg += f"\n💡 说「{label}还剩xx块」可更新"
                    await update.message.reply_text(msg)
                else:
                    await update.message.reply_text(
                        f"📋 还没有追踪{emoji} {label}\n\n"
                        f"说「帮我盯着{label}」添加追踪"
                    )
                return
            elif action_type == "ops_email":
                context.args = ["email"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_task_top":
                context.args = ["task", "top"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_run":
                context.args = ["bounty", "run"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_scan":
                context.args = ["bounty", "scan"] + ([action_arg] if action_arg else [])
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_list":
                context.args = ["bounty", "list"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_top":
                context.args = ["bounty", "top"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_bounty_open":
                context.args = ["bounty", "open"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_tweet_plan":
                context.args = ["tweet", "plan", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_tweet_run":
                context.args = ["tweet", "run", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_docs_search":
                context.args = ["docs", "search", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_docs_index":
                context.args = ["docs", "index", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_meeting":
                context.args = ["meeting", action_arg] if action_arg else ["meeting"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_content":
                context.args = ["content", action_arg] if action_arg else ["content"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_monitor_add":
                context.args = ["monitor", "add", action_arg]
                await self.cmd_ops(update, context)
            elif action_type == "ops_monitor_list":
                context.args = ["monitor", "list"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_monitor_run":
                context.args = ["monitor", "run"]
                await self.cmd_ops(update, context)
            elif action_type == "xianyu_style_show":
                context.args = ["show"]
                await self.cmd_xianyu_style(update, context)
            elif action_type == "xianyu_style_faq_list":
                context.args = ["faq", "list"]
                await self.cmd_xianyu_style(update, context)
            elif action_type == "ops_life_remind":
                # v2.0: 提醒系统扩展 — 支持列表/取消/重复/自然语言时间/经典延迟
                from src.execution.life_automation import create_reminder, list_reminders, cancel_reminder
                chat_id = update.effective_chat.id if update.effective_chat else 0
                parts = action_arg.split("|||") if action_arg else []
                reply = ""

                if action_arg == "list":
                    # 列出所有待触发的提醒
                    reminders = list_reminders(status="pending")
                    if not reminders:
                        reply = "📋 暂无待触发的提醒"
                    else:
                        lines = ["📋 待触发的提醒:"]
                        for r in reminders:
                            lines.append(f"  #{r['id']} — {r['message']} (⏰ {r['remind_at'][:16]})")
                        reply = "\n".join(lines)

                elif parts[0] == "cancel" and len(parts) >= 2:
                    rid = int(parts[1])
                    ok = cancel_reminder(rid)
                    reply = f"✅ 提醒 #{rid} 已取消" if ok else f"❌ 取消失败"

                elif parts[0] == "recur" and len(parts) >= 4:
                    rule, time_part, content = parts[1], parts[2], parts[3]
                    result = await create_reminder(
                        message=content,
                        time_text=time_part or None,
                        recurrence_rule=rule,
                        user_chat_id=chat_id,
                    )
                    if result.get("success"):
                        reply = f"✅ 重复提醒已设置:\n📝 {content}\n🔄 {rule}\n⏰ 首次: {result['display']}"
                    else:
                        reply = f"❌ 设置失败: {result.get('error', '未知错误')}"

                elif parts[0] == "time" and len(parts) >= 3:
                    time_text, content = parts[1], parts[2]
                    result = await create_reminder(
                        message=content,
                        time_text=time_text,
                        user_chat_id=chat_id,
                    )
                    if result.get("success"):
                        reply = f"✅ 提醒已设置:\n📝 {content}\n⏰ {result['display']}"
                    else:
                        reply = f"❌ 设置失败: {result.get('error', '未知错误')}"

                else:
                    # 兼容旧格式: "30|||开会"
                    delay = int(parts[0]) if parts and parts[0].isdigit() else 30
                    content = parts[1] if len(parts) > 1 else action_arg
                    result = await create_reminder(
                        message=content,
                        delay_minutes=delay,
                        user_chat_id=chat_id,
                    )
                    if result.get("success"):
                        reply = f"✅ 提醒已设置:\n📝 {content}\n⏰ {result['display']}"
                    else:
                        reply = f"❌ 设置失败: {result.get('error', '未知错误')}"

                if reply and update.effective_message:
                    await update.effective_message.reply_text(reply)
            elif action_type == "ops_project":
                context.args = ["project", action_arg] if action_arg else ["project"]
                await self.cmd_ops(update, context)
            elif action_type == "ops_dev":
                context.args = ["dev", action_arg] if action_arg else ["dev"]
                await self.cmd_ops(update, context)
            elif action_type == "autotrader_start":
                context.args = ["start"]
                await self.cmd_autotrader(update, context)
            elif action_type == "autotrader_stop":
                context.args = ["stop"]
                await self.cmd_autotrader(update, context)
            # ── v2.0: 自然语言交易 (帮我买100股苹果) ──
            elif action_type == "buy":
                context.args = action_arg.split() if action_arg else []
                await self.cmd_buy(update, context)
            elif action_type == "sell":
                context.args = action_arg.split() if action_arg else []
                await self.cmd_sell(update, context)
            # ── v2.0: 自然语言购物 (帮我找便宜的AirPods) ──
            elif action_type == "smart_shop":
                await self._cmd_smart_shop(update, context, product=action_arg)
            # ── v2.5: 降价监控 (帮我盯着AirPods，降到800告诉我) ──
            elif action_type == "pricewatch_add":
                parts = action_arg.split("|||", 1)
                if len(parts) == 2:
                    keyword, price = parts[0].strip(), parts[1].strip()
                    context.args = ["add"] + keyword.split() + [price]
                    await self.cmd_pricewatch(update, context)
                else:
                    await update.message.reply_text(
                        "❓ 格式不对，试试: 帮我盯着AirPods，降到800告诉我"
                    )
            # ── v3.0: "你是不是想说…" 模糊建议 ──
            elif action_type == "suggest":
                parts = action_arg.split("|||")
                if len(parts) == 3:
                    suggested_action, keyword, label = parts
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton(f"✅ {label}", callback_data=f"nlp:{suggested_action}"),
                    ]])
                    await update.message.reply_text(
                        f"你是不是想说「{keyword}」？",
                        reply_markup=keyboard,
                    )
        except Exception as e:
            logger.warning("[ChineseNLP] 分发 %s(%s) 失败: %s", action_type, action_arg, e)
