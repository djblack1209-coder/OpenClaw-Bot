"""
ClawBot 社交媒体工具集 v2.0

支持：
- A/B 测试框架（多版本内容对比）
- 情感分析 v2.0 — snownlp (6k⭐) 中文 + textblob (9k⭐) 英文 + 词袋降级
- 多平台内容适配器
- 发布时间优化
- 互动率追踪

v2.0 变更 (2026-03-23):
  - 搬运 snownlp (6k⭐) 作为中文情感分析主力引擎 (贝叶斯分类器)
  - 搬运 textblob (9k⭐) 作为英文情感分析引擎 (NLTK 模式匹配)
  - 中英文自动检测分流
  - 原词袋词典保留为双重降级
"""

import hashlib
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from src.constants import TG_MSG_LIMIT
from src.message_format import strip_markdown
from src.utils import now_et

logger = logging.getLogger(__name__)

# ── snownlp / textblob 可选依赖 ──
_HAS_SNOWNLP = False
try:
    from snownlp import SnowNLP
    _HAS_SNOWNLP = True
    logger.debug("[social_tools] snownlp 已加载 (中文情感分析)")
except ImportError:
    SnowNLP = None  # type: ignore[assignment,misc]

_HAS_TEXTBLOB = False
try:
    from textblob import TextBlob
    _HAS_TEXTBLOB = True
    logger.debug("[social_tools] textblob 已加载 (英文情感分析)")
except ImportError:
    TextBlob = None  # type: ignore[assignment,misc]


# ============ 情感分析（零 API 调用） ============

# 中文情感词典（精简版）
_CN_POSITIVE = {
    "好", "棒", "赞", "优秀", "喜欢", "开心", "满意", "推荐", "不错", "厉害",
    "感谢", "完美", "强", "牛", "爱", "支持", "期待", "精彩", "成功", "涨",
    "突破", "利好", "盈利", "增长", "看多", "买入", "加仓",
}
_CN_NEGATIVE = {
    "差", "烂", "垃圾", "失望", "讨厌", "难过", "糟糕", "坑", "骗", "亏",
    "跌", "崩", "利空", "暴跌", "割肉", "止损", "爆仓", "清仓", "看空",
    "卖出", "减仓", "风险", "危险", "警告",
}
# 英文情感词典（精简版）
_EN_POSITIVE = {
    "good", "great", "excellent", "love", "amazing", "awesome", "happy",
    "bullish", "buy", "long", "profit", "gain", "growth", "breakout",
    "recommend", "perfect", "best", "wonderful", "fantastic",
}
_EN_NEGATIVE = {
    "bad", "terrible", "hate", "awful", "bearish", "sell", "short",
    "loss", "crash", "dump", "scam", "fraud", "risk", "danger",
    "worst", "horrible", "disappointing", "fail", "poor",
}

# 否定词
_NEGATORS = {"不", "没", "无", "非", "别", "未", "not", "no", "never", "don't", "isn't", "wasn't"}


@dataclass
class SentimentResult:
    """情感分析结果"""
    score: float          # -1.0 (极负面) 到 +1.0 (极正面)
    label: str            # positive / negative / neutral
    confidence: float     # 0-1
    positive_words: List[str] = field(default_factory=list)
    negative_words: List[str] = field(default_factory=list)


def _lexicon_sentiment(text: str) -> SentimentResult:
    """词袋情感分析降级（原有逻辑，零依赖）"""
    text_lower = text.lower()
    words = set(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text_lower))

    pos_found = []
    neg_found = []
    for w in words:
        if w in _CN_POSITIVE or w in _EN_POSITIVE:
            pos_found.append(w)
        elif w in _CN_NEGATIVE or w in _EN_NEGATIVE:
            neg_found.append(w)

    has_negator = bool(words & _NEGATORS)
    if has_negator and pos_found and not neg_found:
        neg_found = pos_found
        pos_found = []
    elif has_negator and neg_found and not pos_found:
        pos_found = neg_found
        neg_found = []

    total = len(pos_found) + len(neg_found)
    if total == 0:
        return SentimentResult(score=0, label="neutral", confidence=0.3)

    score = (len(pos_found) - len(neg_found)) / total
    confidence = min(0.9, 0.4 + total * 0.1)
    label = "positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral")
    return SentimentResult(
        score=round(score, 3), label=label, confidence=round(confidence, 2),
        positive_words=pos_found, negative_words=neg_found,
    )


def _detect_lang(text: str) -> str:
    """检测文本主要语言: 'zh' / 'en' / 'mixed'"""
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    en_chars = sum(1 for c in text if c.isascii() and c.isalpha())
    total = cn_chars + en_chars
    if total == 0:
        return "en"
    if cn_chars / total > 0.5:
        return "zh"
    elif en_chars / total > 0.7:
        return "en"
    return "mixed"


def analyze_sentiment(text: str) -> SentimentResult:
    """零 API 调用的情感分析（中英文混合支持）

    v2.0 三级降级:
      1. snownlp (6k⭐) — 中文贝叶斯分类器，精度远超词袋
      2. textblob (9k⭐) — 英文 NLTK 模式匹配
      3. 词袋计数 — 原有逻辑作为最终降级

    搬运来源: snownlp + textblob 最佳实践 (GitHub 多项目通用模式)
    """
    if not text:
        return SentimentResult(score=0, label="neutral", confidence=0)

    lang = _detect_lang(text)

    # ── 路径 1: snownlp (中文/混合) ──
    if lang in ("zh", "mixed") and _HAS_SNOWNLP:
        try:
            s = SnowNLP(text)
            # snownlp.sentiments 返回 0~1 (0=负, 1=正)
            raw_score = s.sentiments
            score = (raw_score - 0.5) * 2  # 映射到 -1 ~ +1
            confidence = abs(score) * 0.8 + 0.2  # 偏离中心越远越确信
            if score > 0.15:
                label = "positive"
            elif score < -0.15:
                label = "negative"
            else:
                label = "neutral"
            return SentimentResult(
                score=round(score, 3), label=label,
                confidence=round(min(confidence, 0.95), 2),
            )
        except Exception as e:
            logger.debug(f"[sentiment] snownlp 失败: {e}")

    # ── 路径 2: textblob (英文) ──
    if lang in ("en", "mixed") and _HAS_TEXTBLOB:
        try:
            blob = TextBlob(text)
            # TextBlob polarity: -1 ~ +1
            score = blob.sentiment.polarity
            confidence = abs(score) * 0.7 + 0.3
            if score > 0.1:
                label = "positive"
            elif score < -0.1:
                label = "negative"
            else:
                label = "neutral"
            return SentimentResult(
                score=round(score, 3), label=label,
                confidence=round(min(confidence, 0.95), 2),
            )
        except Exception as e:
            logger.debug(f"[sentiment] textblob 失败: {e}")

    # ── 路径 3: 词袋降级（原有逻辑）──
    return _lexicon_sentiment(text)


# ============ A/B 测试框架 ============

@dataclass
class ABVariant:
    """A/B 测试变体"""
    variant_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 追踪指标
    impressions: int = 0
    clicks: int = 0
    replies: int = 0
    positive_reactions: int = 0
    negative_reactions: int = 0

    @property
    def ctr(self) -> float:
        """点击率"""
        return self.clicks / max(self.impressions, 1)

    @property
    def engagement_rate(self) -> float:
        """互动率"""
        return (self.clicks + self.replies + self.positive_reactions) / max(self.impressions, 1)

    @property
    def sentiment_score(self) -> float:
        """情感得分"""
        total = self.positive_reactions + self.negative_reactions
        if total == 0:
            return 0
        return (self.positive_reactions - self.negative_reactions) / total


@dataclass
class ABTest:
    """A/B 测试"""
    test_id: str
    name: str
    variants: List[ABVariant]
    created_at: str = field(default_factory=lambda: now_et().isoformat())
    status: str = "active"  # active / paused / completed
    winner_id: Optional[str] = None
    min_impressions: int = 30  # 每个变体最少曝光数才能判定胜者

    def pick_variant(self) -> ABVariant:
        """选择变体（Thompson Sampling — 比简单随机更智能）"""
        if len(self.variants) == 1:
            return self.variants[0]

        # Thompson Sampling: 用 Beta 分布采样
        best_score = -1
        best_variant = self.variants[0]
        for v in self.variants:
            # alpha = 正面信号 + 1（点赞/点击）
            # beta = 负面信号 + 1（差评；未互动不算失败，避免高曝光低点击被永久惩罚）
            alpha = v.positive_reactions + v.clicks + 1
            beta_param = v.negative_reactions + 1
            sample = random.betavariate(alpha, beta_param)
            if sample > best_score:
                best_score = sample
                best_variant = v
        return best_variant

    def check_winner(self) -> Optional[str]:
        """检查是否有统计显著的胜者"""
        if any(v.impressions < self.min_impressions for v in self.variants):
            return None

        # 简单规则：互动率最高且领先第二名 20% 以上
        sorted_variants = sorted(self.variants, key=lambda v: -v.engagement_rate)
        if len(sorted_variants) < 2:
            return sorted_variants[0].variant_id

        best = sorted_variants[0]
        second = sorted_variants[1]
        if second.engagement_rate == 0 or best.engagement_rate / second.engagement_rate > 1.2:
            self.winner_id = best.variant_id
            self.status = "completed"
            return best.variant_id
        return None


class ABTestManager:
    """A/B 测试管理器"""

    def __init__(self, data_dir: Optional[str] = None):
        self._tests: Dict[str, ABTest] = {}
        if data_dir:
            self._data_path = Path(data_dir) / "ab_tests.json"
        else:
            self._data_path = Path(__file__).parent.parent / "data" / "ab_tests.json"
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def create_test(self, name: str, contents: List[str],
                    metadata: Optional[List[Dict]] = None) -> ABTest:
        """创建 A/B 测试"""
        test_id = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:8]
        variants = []
        for i, content in enumerate(contents):
            vid = chr(65 + i)  # A, B, C, ...
            meta = metadata[i] if metadata and i < len(metadata) else {}
            variants.append(ABVariant(variant_id=vid, content=content, metadata=meta))

        test = ABTest(test_id=test_id, name=name, variants=variants)
        self._tests[test_id] = test
        self._save()
        logger.info(f"[ABTest] 创建测试 '{name}' ({test_id}): {len(variants)} 个变体")
        return test

    def get_content(self, test_id: str) -> Tuple[str, str]:
        """获取测试内容（自动选择变体）

        Returns: (variant_id, content)
        """
        test = self._tests.get(test_id)
        if not test or test.status != "active":
            return ("", "")
        variant = test.pick_variant()
        variant.impressions += 1
        self._save()
        return (variant.variant_id, variant.content)

    def record_engagement(self, test_id: str, variant_id: str,
                          event: str = "click"):
        """记录互动事件"""
        test = self._tests.get(test_id)
        if not test:
            return
        for v in test.variants:
            if v.variant_id == variant_id:
                if event == "click":
                    v.clicks += 1
                elif event == "reply":
                    v.replies += 1
                elif event == "positive":
                    v.positive_reactions += 1
                elif event == "negative":
                    v.negative_reactions += 1
                elif event == "publish":
                    # 发布事件 — 计为一次曝光（已在 get_content 中 +1）
                    # 额外记录为 click 以便统计发布成功率
                    v.clicks += 1
                break
        test.check_winner()
        self._save()

    def get_results(self, test_id: str) -> Optional[Dict[str, Any]]:
        """获取测试结果"""
        test = self._tests.get(test_id)
        if not test:
            return None
        return {
            "test_id": test.test_id,
            "name": test.name,
            "status": test.status,
            "winner": test.winner_id,
            "variants": [
                {
                    "id": v.variant_id,
                    "impressions": v.impressions,
                    "clicks": v.clicks,
                    "ctr": round(v.ctr * 100, 1),
                    "engagement_rate": round(v.engagement_rate * 100, 1),
                    "sentiment": round(v.sentiment_score, 2),
                    "content_preview": v.content[:80],
                }
                for v in test.variants
            ],
        }

    def list_tests(self, status: Optional[str] = None) -> List[Dict]:
        tests = self._tests.values()
        if status:
            tests = [t for t in tests if t.status == status]
        return [
            {"test_id": t.test_id, "name": t.name, "status": t.status,
             "variants": len(t.variants), "winner": t.winner_id}
            for t in tests
        ]

    def get_active_tests(self) -> list:
        """获取所有活跃的 A/B 测试实例"""
        return [t for t in self._tests.values() if t.status == "active"]

    def _save(self):
        try:
            data = {}
            for tid, test in self._tests.items():
                data[tid] = {
                    "test_id": test.test_id, "name": test.name,
                    "status": test.status, "winner_id": test.winner_id,
                    "created_at": test.created_at,
                    "min_impressions": test.min_impressions,
                    "variants": [
                        {
                            "variant_id": v.variant_id, "content": v.content,
                            "metadata": v.metadata, "impressions": v.impressions,
                            "clicks": v.clicks, "replies": v.replies,
                            "positive_reactions": v.positive_reactions,
                            "negative_reactions": v.negative_reactions,
                        }
                        for v in test.variants
                    ],
                }
            with open(self._data_path, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"[ABTest] 保存失败: {e}")

    def _load(self):
        if not self._data_path.exists():
            return
        try:
            with open(self._data_path) as f:
                data = json.load(f)
            for tid, td in data.items():
                variants = [ABVariant(**v) for v in td.get("variants", [])]
                self._tests[tid] = ABTest(
                    test_id=td["test_id"], name=td["name"],
                    variants=variants, status=td.get("status", "active"),
                    winner_id=td.get("winner_id"),
                    created_at=td.get("created_at", ""),
                    min_impressions=td.get("min_impressions", 30),
                )
        except Exception as e:
            logger.debug(f"[ABTest] 加载失败: {e}")


# ============ 多平台内容适配器 ============

class ContentAdapter:
    """多平台内容适配器 — 将同一内容适配到不同平台格式"""

    PLATFORM_LIMITS = {
        "telegram": {"max_chars": TG_MSG_LIMIT, "supports_markdown": True, "supports_html": True},
        "twitter": {"max_chars": 280, "supports_markdown": False, "supports_html": False},
        "weibo": {"max_chars": 2000, "supports_markdown": False, "supports_html": False},
        "discord": {"max_chars": 2000, "supports_markdown": True, "supports_html": False},
        "wechat": {"max_chars": 600, "supports_markdown": False, "supports_html": False},
    }

    @classmethod
    def adapt(cls, content: str, platform: str, add_hashtags: bool = True) -> str:
        """适配内容到指定平台"""
        limits = cls.PLATFORM_LIMITS.get(platform, {"max_chars": 2000})
        max_chars = limits["max_chars"]

        # 去除不支持的格式
        if not limits.get("supports_markdown"):
            content = strip_markdown(content)

        # 截断
        if len(content) > max_chars:
            # 为省略号和 hashtag 留空间
            reserve = 50 if add_hashtags else 5
            content = content[:max_chars - reserve] + "..."

        return content


# ============ 发布时间优化器 ============

class PostTimeOptimizer:
    """基于历史互动数据推荐最佳发布时间（带 JSON 持久化）"""

    def __init__(self, data_dir: Optional[str] = None):
        import threading
        # 默认最佳时段（基于通用社交媒体研究）
        self._default_hours = {
            "telegram": [9, 12, 18, 21],
            "twitter": [8, 12, 17, 20],
            "weibo": [8, 12, 18, 22],
        }
        self._engagement_by_hour: Dict[int, List[float]] = {}
        # 线程锁：保护跨线程访问（APScheduler 线程写入 + asyncio 主线程读取）(HI-457)
        self._data_lock = threading.Lock()
        # 持久化路径：优先使用传入目录，否则用包级 data/ 目录
        if data_dir:
            self._data_path = Path(data_dir) / "post_time_optimizer.json"
        else:
            self._data_path = Path(__file__).parent.parent / "data" / "post_time_optimizer.json"
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        # 启动时从磁盘加载历史数据
        self._load()

    def record_engagement(self, hour: int, engagement_rate: float):
        """记录某小时的互动率"""
        with self._data_lock:
            if hour not in self._engagement_by_hour:
                self._engagement_by_hour[hour] = []
            self._engagement_by_hour[hour].append(engagement_rate)
            # 只保留最近 100 条
            if len(self._engagement_by_hour[hour]) > 100:
                self._engagement_by_hour[hour] = self._engagement_by_hour[hour][-50:]
            # 在锁内拍快照，确保序列化数据一致（HI-457 修复）
            snapshot = {str(h): list(rates) for h, rates in self._engagement_by_hour.items()}
        # 用快照写磁盘（无需持锁，避免 I/O 阻塞其他线程）
        self._save(snapshot)

    def best_hours(self, platform: str = "telegram", top_n: int = 3) -> List[int]:
        """推荐最佳发布时间"""
        with self._data_lock:
            if not self._engagement_by_hour:
                return self._default_hours.get(platform, [9, 12, 18])[:top_n]

            avg_by_hour = {}
            for hour, rates in self._engagement_by_hour.items():
                avg_by_hour[hour] = sum(rates) / len(rates)

        sorted_hours = sorted(avg_by_hour.items(), key=lambda x: -x[1])
        return [h for h, _ in sorted_hours[:top_n]]

    def _save(self, snapshot: Optional[Dict[str, list]] = None):
        """将互动数据写入 JSON 文件。优先使用传入的快照，否则在锁内拍新快照"""
        try:
            if snapshot is None:
                with self._data_lock:
                    snapshot = {str(h): list(rates) for h, rates in self._engagement_by_hour.items()}
            with open(self._data_path, "w") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("[PostTimeOptimizer] 保存失败: %s", e)

    def _load(self):
        """从 JSON 文件加载历史互动数据"""
        if not self._data_path.exists():
            return
        try:
            with open(self._data_path) as f:
                data = json.load(f)
            # JSON key 是字符串，还原为整数
            self._engagement_by_hour = {int(h): rates for h, rates in data.items()}
        except Exception as e:
            logger.debug("[PostTimeOptimizer] 加载失败: %s", e)


# ── PostTimeOptimizer 全局单例 ──
_post_time_optimizer_instance: Optional[PostTimeOptimizer] = None
_post_time_optimizer_lock = __import__("threading").Lock()


def get_post_time_optimizer(data_dir: Optional[str] = None) -> PostTimeOptimizer:
    """获取 PostTimeOptimizer 全局单例，避免每次调用新建实例导致数据丢失"""
    global _post_time_optimizer_instance
    if _post_time_optimizer_instance is None:
        with _post_time_optimizer_lock:
            # 双重检查锁防止重复创建
            if _post_time_optimizer_instance is None:
                _post_time_optimizer_instance = PostTimeOptimizer(data_dir=data_dir)
    return _post_time_optimizer_instance
