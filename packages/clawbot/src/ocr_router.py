"""
OCR 场景路由器 — 识别图片类型，分发到对应业务处理链

核心逻辑：
  OCR 文字 → 关键词/模式匹配 → 场景分类 → 专属处理器

场景：
  financial  — 财报/K线/持仓截图 → 提取指标 → 对比 → 交易信号
  ecommerce  — 竞品截图/商品页/价格表 → 竞品分析 → 定价建议
  general    — 通用文字提取（默认）
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OcrScene(Enum):
    FINANCIAL = "financial"
    ECOMMERCE = "ecommerce"
    GENERAL = "general"


@dataclass
class SceneMatch:
    scene: OcrScene
    confidence: float          # 0.0 ~ 1.0
    matched_signals: list[str] # 命中的关键词/模式
    summary: str               # 一句话说明为什么匹配


# ── 信号词库 ──────────────────────────────────────────

_FINANCIAL_KEYWORDS = {
    # 财务指标
    "营收", "净利润", "毛利率", "净利率", "ROE", "ROA", "EPS", "PE", "PB",
    "市盈率", "市净率", "每股收益", "总资产", "净资产", "负债率",
    "revenue", "profit", "margin", "earnings", "dividend",
    # 行情/交易
    "涨幅", "跌幅", "成交量", "成交额", "换手率", "振幅", "开盘", "收盘",
    "最高", "最低", "均线", "MACD", "KDJ", "RSI", "布林",
    "买入", "卖出", "持仓", "仓位", "止损", "止盈", "盈亏",
    # 平台/来源
    "同花顺", "东方财富", "雪球", "富途", "老虎", "IBKR", "盈透",
    "Robinhood", "TradingView", "Bloomberg",
    # 财报结构
    "资产负债表", "利润表", "现金流量表", "季报", "年报", "半年报",
    "Q1", "Q2", "Q3", "Q4", "FY20", "FY21", "FY22", "FY23", "FY24", "FY25",
}

_FINANCIAL_PATTERNS = [
    r"[+-]?\d+\.?\d*%",                    # 百分比 +12.5%
    r"(?:¥|＄|\$|USD|CNY)\s*[\d,.]+",      # 金额 ¥1,234
    r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}",   # 日期
    r"(?:股票|基金|ETF|期货|期权)\s*[:：]",  # 品种标签
    r"(?:买|卖|持)\s*\d+\s*(?:股|手|份)",   # 交易量
    r"(?:涨停|跌停|涨幅|跌幅)\s*[:：]?\s*[+-]?\d", # 涨跌
]

_ECOMMERCE_KEYWORDS = {
    # 平台
    "闲鱼", "淘宝", "拼多多", "京东", "抖音", "小红书", "1688",
    "咸鱼", "转转", "得物", "唯品会",
    # 商品/交易
    "包邮", "到手价", "券后价", "原价", "折扣", "优惠券", "满减",
    "已售", "销量", "月销", "评价", "好评", "差评", "退货",
    "库存", "规格", "SKU", "sku",
    # 竞品分析
    "竞品", "同款", "对标", "比价", "价格区间", "定价",
    "利润率", "成本", "进货价", "批发价",
    # 商品描述
    "全新", "二手", "9成新", "95新", "99新", "自用",
    "发货", "快递", "顺丰", "运费",
}

_ECOMMERCE_PATTERNS = [
    r"(?:¥|￥)\s*\d+\.?\d*",               # 价格 ¥99.9
    r"\d+\.?\d*\s*元",                      # xx元
    r"月销\s*\d+",                           # 月销量
    r"已售\s*\d+",                           # 已售量
    r"(?:好评|差评)\s*\d+",                  # 评价数
    r"(?:库存|剩余)\s*\d+",                  # 库存
    r"(?:包邮|运费\s*\d+)",                  # 运费
]


def _count_signals(text: str, keywords: set, patterns: list) -> tuple[int, list[str]]:
    """统计命中的信号数量和具体命中项"""
    matched = []
    text_lower = text.lower()

    for kw in keywords:
        if kw.lower() in text_lower:
            matched.append(kw)

    for pat in patterns:
        if re.search(pat, text):
            matched.append(f"pattern:{pat[:20]}")

    return len(matched), matched


def classify_ocr_scene(ocr_text: str, caption: str = "") -> SceneMatch:
    """
    根据 OCR 文字内容和用户 caption 判断所属业务场景。

    优先级：
    1. caption 中的显式意图（用户说了"分析财报"就是 financial）
    2. OCR 文字中的信号密度
    3. 默认 general
    """
    combined = f"{caption} {ocr_text}"

    # 1. Caption 显式意图检测
    caption_lower = caption.lower()

    financial_intents = ["财报", "分析", "交易", "持仓", "行情", "K线", "k线", "股票", "基金"]
    ecommerce_intents = ["竞品", "比价", "定价", "闲鱼", "淘宝", "商品", "对标", "同款"]

    for intent in financial_intents:
        if intent in caption_lower:
            return SceneMatch(
                scene=OcrScene.FINANCIAL,
                confidence=0.95,
                matched_signals=[f"caption:{intent}"],
                summary=f"用户明确提到「{intent}」，进入交易分析模式"
            )

    for intent in ecommerce_intents:
        if intent in caption_lower:
            return SceneMatch(
                scene=OcrScene.ECOMMERCE,
                confidence=0.95,
                matched_signals=[f"caption:{intent}"],
                summary=f"用户明确提到「{intent}」，进入电商竞品分析模式"
            )

    # 2. OCR 文字信号密度
    fin_count, fin_matched = _count_signals(combined, _FINANCIAL_KEYWORDS, _FINANCIAL_PATTERNS)
    eco_count, eco_matched = _count_signals(combined, _ECOMMERCE_KEYWORDS, _ECOMMERCE_PATTERNS)

    # 信号密度阈值：至少命中 3 个信号才算匹配
    MIN_SIGNALS = 3

    if fin_count >= MIN_SIGNALS and fin_count > eco_count:
        confidence = min(0.5 + fin_count * 0.05, 0.9)
        return SceneMatch(
            scene=OcrScene.FINANCIAL,
            confidence=confidence,
            matched_signals=fin_matched[:10],
            summary=f"检测到 {fin_count} 个财务/交易信号，进入交易分析模式"
        )

    if eco_count >= MIN_SIGNALS and eco_count > fin_count:
        confidence = min(0.5 + eco_count * 0.05, 0.9)
        return SceneMatch(
            scene=OcrScene.ECOMMERCE,
            confidence=confidence,
            matched_signals=eco_matched[:10],
            summary=f"检测到 {eco_count} 个电商/竞品信号，进入竞品分析模式"
        )

    # 3. 默认
    return SceneMatch(
        scene=OcrScene.GENERAL,
        confidence=1.0,
        matched_signals=[],
        summary="通用文字提取"
    )
