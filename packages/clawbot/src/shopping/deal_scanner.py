"""
黑五折扣搜集引擎 — 主动扫描全网热门折扣并推送通知

复用现有 price_engine 的 SMZDM 爬取能力，新增：
1. 热门分类定时扫描（数码/家电/美妆/个护/食品）
2. 降价幅度过滤（只推送 30%+ 折扣的好 Deal）
3. 多渠道推送（Telegram + 微信）
4. 历史去重（同一商品 24 小时内不重复推送）

数据源：
- 什么值得买 (SMZDM) — 热门好价专区 + 分类搜索
- 京东 (JD) — 现有爬取能力

调度：
- 挂载到项目现有的 APScheduler 调度器
- 默认每 4 小时扫描一次
- 黑五/双11 期间可缩短到每 1 小时

> 最后更新: 2026-04-23
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from src.constants import DEFAULT_USER_AGENT
from src.shopping.price_engine import (
    search_smzdm,
)

logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────
# 扫描分类关键词（覆盖黑五热门品类）
DEAL_CATEGORIES = [
    # 数码
    {"name": "数码", "keywords": ["iPhone", "iPad", "MacBook", "AirPods", "Switch", "PS5", "显示器"]},
    # 家电
    {"name": "家电", "keywords": ["洗衣机", "空调", "冰箱", "扫地机器人", "投影仪", "空气净化器"]},
    # 个护美妆
    {"name": "个护", "keywords": ["戴森", "飞利浦", "欧莱雅", "兰蔻", "雅诗兰黛"]},
    # 食品
    {"name": "食品", "keywords": ["咖啡", "坚果", "巧克力", "牛排", "零食"]},
]

# 折扣阈值（只推送折扣力度大于此值的商品）
MIN_DISCOUNT_PCT = 30  # 至少打 7 折

# 推送限制
MAX_DEALS_PER_SCAN = 10  # 每次扫描最多推送条数
DEDUP_HOURS = 24  # 同一商品 24 小时内不重复推送

# 历史记录文件
_HISTORY_FILE = Path(os.getenv(
    "DEAL_HISTORY_PATH",
    str(Path(__file__).resolve().parent.parent.parent / "data" / "deal_history.json")
))

# ── 数据模型 ──────────────────────────────────────────


@dataclass
class DealItem:
    """一条折扣商品信息"""
    title: str
    price: float
    original_price: float  # 原价（用于计算折扣率）
    discount_pct: int  # 折扣率（如 35 表示降了 35%）
    platform: str
    url: str
    category: str
    source: str = "smzdm"
    found_at: str = ""  # ISO 时间戳

    def __post_init__(self):
        if not self.found_at:
            self.found_at = datetime.now().isoformat()

    @property
    def hash_key(self) -> str:
        """去重用的 hash（标题+平台）"""
        raw = f"{self.title}|{self.platform}".lower()
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_message(self) -> str:
        """格式化为推送消息"""
        discount_tag = f"🔥 -{self.discount_pct}%" if self.discount_pct >= 50 else f"💰 -{self.discount_pct}%"
        return (
            f"{discount_tag} [{self.category}]\n"
            f"📦 {self.title}\n"
            f"💲 ¥{self.price:.0f}（原价 ¥{self.original_price:.0f}）\n"
            f"🏪 {self.platform}\n"
            f"🔗 {self.url}"
        )


# ── 历史去重 ──────────────────────────────────────────


class DealHistory:
    """已推送 Deal 的历史记录，用于 24 小时去重"""

    def __init__(self):
        self._history: dict[str, float] = {}  # hash_key → timestamp
        self._load()

    def _load(self):
        """从磁盘加载历史"""
        if _HISTORY_FILE.exists():
            try:
                with open(_HISTORY_FILE) as f:
                    self._history = json.load(f)
            except Exception:
                self._history = {}
        # 清理过期记录
        self._cleanup()

    def _save(self):
        """持久化到磁盘"""
        try:
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_HISTORY_FILE, "w") as f:
                json.dump(self._history, f)
        except Exception as e:
            logger.warning("保存 Deal 历史失败: %s", e)

    def _cleanup(self):
        """清理超过 24 小时的记录"""
        cutoff = time.time() - DEDUP_HOURS * 3600
        self._history = {k: v for k, v in self._history.items() if v > cutoff}

    def is_new(self, deal: DealItem) -> bool:
        """检查是否是新 Deal（24 小时内未推送过）"""
        return deal.hash_key not in self._history

    def mark_sent(self, deal: DealItem):
        """标记已推送"""
        self._history[deal.hash_key] = time.time()
        self._save()


# 模块级单例
_history = DealHistory()

# ── SMZDM 热门好价抓取 ────────────────────────────────


async def _fetch_smzdm_hot_deals(limit: int = 20) -> list[DealItem]:
    """抓取 SMZDM 热门好价排行（不需要关键词，直接抓热门）

    数据源: https://www.smzdm.com/fenlei/ 各分类热门
    """
    deals: list[DealItem] = []
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            # SMZDM 好价排行 — 按热度排序
            resp = await client.get(
                "https://www.smzdm.com/fenlei/",
                headers=headers,
            )
            if resp.status_code != 200:
                logger.warning("SMZDM 热门页状态码: %d", resp.status_code)
                return deals

            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.select(".feed-row-wide, .list_feed_row")[:limit]

            for item in items:
                deal = _parse_smzdm_deal(item)
                if deal and deal.discount_pct >= MIN_DISCOUNT_PCT:
                    deals.append(deal)

    except Exception as e:
        logger.warning("SMZDM 热门抓取失败: %s", e)

    return deals


async def _fetch_smzdm_category_deals(keywords: list[str], category: str) -> list[DealItem]:
    """按关键词搜索 SMZDM 折扣商品"""
    deals: list[DealItem] = []

    for kw in keywords:
        try:
            results = await search_smzdm(kw, limit=5)
            for r in results:
                # 检查是否标记为好价/值/低价
                if r.is_deal or r.historical_low > 0:
                    # 估算折扣率
                    discount_pct = 0
                    original = r.historical_low if r.historical_low > r.price else r.price * 1.3
                    if original > 0 and r.price > 0:
                        discount_pct = int((1 - r.price / original) * 100)

                    if discount_pct >= MIN_DISCOUNT_PCT:
                        deals.append(DealItem(
                            title=r.title,
                            price=r.price,
                            original_price=original,
                            discount_pct=discount_pct,
                            platform=r.platform,
                            url=r.url,
                            category=category,
                            source="smzdm",
                        ))
            # 礼貌延迟，避免请求过快
            await asyncio.sleep(1)
        except Exception as e:
            logger.debug("SMZDM 搜索 '%s' 失败: %s", kw, e)

    return deals


def _parse_smzdm_deal(item) -> DealItem | None:
    """从 SMZDM 列表项解析折扣信息"""
    try:
        # 标题
        title_el = item.select_one("h5 a, .feed-block-title a, a.feed-nowrap")
        if not title_el:
            return None
        title = title_el.text.strip()
        url = title_el.get("href", "")

        # 价格
        price_el = item.select_one(".z-highlight, .red-price, .feed-block-text-top span")
        if not price_el:
            return None
        price_text = price_el.text.strip()
        price = _extract_price_num(price_text)
        if price <= 0:
            return None

        # 平台
        mall_el = item.select_one(".feed-block-extras a, .search-result-mall")
        platform = mall_el.text.strip() if mall_el else "未知"

        # 折扣率（从文案中提取，如"比日常低35%"）
        discount_pct = 0
        text_all = item.get_text()
        # 匹配 "降XX%" / "低XX%" / "XX折" / "满减后XX元"
        pct_match = re.search(r'(?:降|低|省|减)\s*(\d{1,3})\s*%', text_all)
        if pct_match:
            discount_pct = int(pct_match.group(1))

        zhe_match = re.search(r'(\d(?:\.\d)?)\s*折', text_all)
        if zhe_match and not pct_match:
            zhe = float(zhe_match.group(1))
            if 1 <= zhe <= 9:
                discount_pct = int((10 - zhe) * 10)

        # 估算原价
        original = price / (1 - discount_pct / 100) if discount_pct > 0 else price * 1.3

        # 分类推断
        category = _infer_category(title)

        return DealItem(
            title=title,
            price=price,
            original_price=round(original, 0),
            discount_pct=discount_pct,
            platform=platform,
            url=url,
            category=category,
        )

    except Exception as e:
        logger.debug("解析 SMZDM Deal 失败: %s", e)
        return None


def _extract_price_num(text: str) -> float:
    """从文本中提取价格数字"""
    match = re.search(r'[\d,]+\.?\d*', text.replace(',', ''))
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass
    return 0.0


def _infer_category(title: str) -> str:
    """根据标题推断商品分类"""
    title_lower = title.lower()
    categories = {
        "数码": ["iphone", "ipad", "macbook", "airpods", "switch", "ps5", "显示器", "耳机", "手机", "平板", "电脑", "相机"],
        "家电": ["洗衣机", "空调", "冰箱", "扫地", "投影", "净化器", "吸尘", "烤箱", "微波"],
        "个护": ["戴森", "飞利浦", "欧莱雅", "兰蔻", "雅诗兰黛", "面膜", "护肤", "洗发"],
        "食品": ["咖啡", "坚果", "巧克力", "牛排", "零食", "牛奶", "啤酒", "茶"],
        "服饰": ["nike", "adidas", "优衣库", "lululemon", "外套", "运动鞋"],
        "居家": ["床垫", "枕头", "收纳", "清洁", "拖把"],
    }
    for cat, keywords in categories.items():
        for kw in keywords:
            if kw in title_lower:
                return cat
    return "其他"


# ── 扫描主函数 ────────────────────────────────────────


async def scan_deals(
    categories: list[dict] | None = None,
    min_discount: int = MIN_DISCOUNT_PCT,
) -> list[DealItem]:
    """扫描全网折扣 — 返回去重后的新 Deal 列表

    Args:
        categories: 自定义分类，默认用 DEAL_CATEGORIES
        min_discount: 最小折扣率，默认 30%

    Returns:
        去重后的新 DealItem 列表（已过滤历史）
    """
    cats = categories or DEAL_CATEGORIES
    all_deals: list[DealItem] = []

    logger.info("🔍 开始扫描折扣... (%d 个分类)", len(cats))

    # 1. 扫 SMZDM 热门
    hot_deals = await _fetch_smzdm_hot_deals(limit=30)
    all_deals.extend(hot_deals)
    logger.info("SMZDM 热门: %d 条符合条件", len(hot_deals))

    # 2. 按分类关键词搜索
    for cat in cats:
        cat_deals = await _fetch_smzdm_category_deals(cat["keywords"], cat["name"])
        all_deals.extend(cat_deals)
        logger.info("分类 [%s]: %d 条", cat["name"], len(cat_deals))

    # 3. 按折扣率排序
    all_deals.sort(key=lambda d: d.discount_pct, reverse=True)

    # 4. 去重（同一商品只保留折扣最大的）
    seen_hashes = set()
    unique_deals = []
    for deal in all_deals:
        if deal.hash_key not in seen_hashes and deal.discount_pct >= min_discount:
            seen_hashes.add(deal.hash_key)
            unique_deals.append(deal)

    # 5. 过滤已推送的
    new_deals = [d for d in unique_deals if _history.is_new(d)]

    logger.info("📊 扫描完成: 总 %d → 去重 %d → 新 %d",
                len(all_deals), len(unique_deals), len(new_deals))

    return new_deals[:MAX_DEALS_PER_SCAN]


# ── 推送 ──────────────────────────────────────────────


async def push_deals_telegram(deals: list[DealItem], chat_id: int, bot_token: str):
    """推送折扣列表到 Telegram"""
    if not deals:
        return

    # 汇总消息
    header = f"🛒 折扣速报 ({len(deals)} 条)\n{'━' * 20}\n\n"
    body = "\n\n".join(d.to_message() for d in deals)
    message = header + body

    # Telegram 消息长度限制 4096
    if len(message) > 4000:
        message = message[:3950] + "\n\n... (更多折扣见下次推送)"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code == 200:
                # 标记已推送
                for d in deals:
                    _history.mark_sent(d)
                logger.info("✅ Telegram 推送 %d 条折扣", len(deals))
            else:
                logger.warning("Telegram 推送失败: %s", resp.text[:200])
    except Exception as e:
        logger.error("Telegram 推送异常: %s", e)


async def push_deals_wechat(deals: list[DealItem]):
    """推送折扣列表到微信"""
    if not deals:
        return

    try:
        from src.wechat_bridge import is_wechat_notify_enabled, send_to_wechat
        if not is_wechat_notify_enabled():
            return

        header = f"🛒 折扣速报 ({len(deals)} 条)\n\n"
        body = "\n\n".join(d.to_message() for d in deals[:5])  # 微信每条消息不宜太长
        message = header + body

        ok = await send_to_wechat(message)
        if ok:
            for d in deals[:5]:
                _history.mark_sent(d)
            logger.info("✅ 微信推送 %d 条折扣", min(len(deals), 5))
    except Exception as e:
        logger.warning("微信推送失败: %s", e)


# ── 调度入口 ──────────────────────────────────────────


async def scheduled_deal_scan():
    """定时任务入口 — 被 APScheduler 调用"""
    logger.info("⏰ 定时折扣扫描启动")

    deals = await scan_deals()

    if not deals:
        logger.info("本轮无新折扣")
        return

    # 推送到 Telegram
    notify_token = os.getenv("NOTIFY_TG_TOKEN", "")
    notify_chat = os.getenv("NOTIFY_TG_CHAT_ID", "")
    if notify_token and notify_chat:
        await push_deals_telegram(deals, int(notify_chat), notify_token)

    # 推送到微信
    await push_deals_wechat(deals)

    logger.info("🏁 折扣扫描完成: 推送了 %d 条", len(deals))


# ── 手动触发 ──────────────────────────────────────────


async def manual_deal_scan(query: str = "") -> str:
    """手动触发折扣扫描 — 供 Bot 命令调用

    Args:
        query: 可选关键词，为空则扫描全分类

    Returns:
        格式化的结果文本
    """
    if query:
        # 指定关键词搜索
        deals = await _fetch_smzdm_category_deals([query], _infer_category(query))
        deals = [d for d in deals if _history.is_new(d)]
        deals.sort(key=lambda d: d.discount_pct, reverse=True)
        deals = deals[:MAX_DEALS_PER_SCAN]
    else:
        deals = await scan_deals()

    if not deals:
        return "🔍 暂未发现符合条件的折扣（需降价 30% 以上）\n\n💡 试试指定商品: /deals iPhone"

    header = f"🛒 找到 {len(deals)} 条好价\n{'━' * 20}\n\n"
    body = "\n\n".join(d.to_message() for d in deals)
    return header + body
