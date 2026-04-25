"""
黑五/全球折扣关键词扫描器

用户输入关键词（如 "VPS"），系统搜索全球供应商的黑五优惠。
使用 Tavily/Jina 进行网页搜索，SQLite 记录已推送的优惠去重。

用法:
    from src.shopping.blackfriday_scanner import scan_blackfriday_deals
    deals = await scan_blackfriday_deals("VPS")

> 最后更新: 2026-04-25
"""

import hashlib
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────
# 去重数据库路径
_DB_DIR = Path(os.getenv(
    "BLACKFRIDAY_DB_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "data"),
))
_DB_PATH = _DB_DIR / "blackfriday_seen.db"

# 去重有效期（秒）：同一条 deal 7 天内不重复推送
DEDUP_TTL_SECONDS = 7 * 24 * 3600

# 已知的黑五/折扣聚合站（用于定向搜索）
_BF_AGGREGATOR_SITES = [
    "blackfriday.com",
    "slickdeals.net",
    "reddit.com/r/blackfriday",
    "dealsea.com",
    "lowendbox.com",       # VPS 专用
    "lowendtalk.com",      # VPS 论坛
    "serverhunter.com",    # 服务器折扣
    "webhostingcat.com",   # 主机折扣
]


# ── 数据模型 ──────────────────────────────────────────

@dataclass
class BlackFridayDeal:
    """一条全球折扣信息"""
    vendor: str          # 供应商/品牌名
    deal_title: str      # 优惠标题
    price: str           # 价格描述（可能是 "$2.99/mo" 等非纯数字格式）
    discount_pct: str    # 折扣描述（如 "70% off"、"半价"）
    url: str             # 来源链接
    expires: str         # 过期时间描述（可能为空）
    source: str = ""     # 搜索来源标记（tavily/jina）

    @property
    def hash_key(self) -> str:
        """去重用的 hash（标题+URL 域名）"""
        # 用标题+URL的域名做 hash，避免同一个优惠不同链接重复
        from urllib.parse import urlparse
        domain = ""
        try:
            domain = urlparse(self.url).netloc
        except Exception:
            pass
        raw = f"{self.deal_title.lower().strip()}|{domain}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def to_message(self) -> str:
        """格式化为推送消息"""
        lines = [f"🏷️ {self.vendor}"]
        lines.append(f"   {self.deal_title}")
        if self.price:
            lines.append(f"   💲 {self.price}")
        if self.discount_pct:
            lines.append(f"   🔥 {self.discount_pct}")
        if self.expires:
            lines.append(f"   ⏰ {self.expires}")
        if self.url:
            lines.append(f"   🔗 {self.url}")
        return "\n".join(lines)


# ── SQLite 去重数据库 ─────────────────────────────────

def _ensure_db() -> sqlite3.Connection:
    """确保去重数据库存在并返回连接"""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_deals (
            hash_key TEXT PRIMARY KEY,
            deal_title TEXT,
            keyword TEXT,
            seen_at REAL
        )
    """)
    conn.commit()
    return conn


def _is_seen(hash_key: str) -> bool:
    """检查 deal 是否在去重窗口内已推送过"""
    try:
        conn = _ensure_db()
        cutoff = time.time() - DEDUP_TTL_SECONDS
        row = conn.execute(
            "SELECT 1 FROM seen_deals WHERE hash_key = ? AND seen_at > ?",
            (hash_key, cutoff),
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        logger.warning("去重查询失败: %s", e)
        return False


def _mark_seen(deals: list[BlackFridayDeal], keyword: str) -> None:
    """批量标记已推送"""
    if not deals:
        return
    try:
        conn = _ensure_db()
        now = time.time()
        conn.executemany(
            "INSERT OR REPLACE INTO seen_deals (hash_key, deal_title, keyword, seen_at) VALUES (?, ?, ?, ?)",
            [(d.hash_key, d.deal_title[:200], keyword, now) for d in deals],
        )
        conn.commit()
        # 顺便清理过期记录
        cutoff = now - DEDUP_TTL_SECONDS
        conn.execute("DELETE FROM seen_deals WHERE seen_at < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("标记已推送失败: %s", e)


# ── 搜索实现 ──────────────────────────────────────────

async def _search_via_tavily(keyword: str) -> list[dict]:
    """通过 Tavily 搜索全球黑五折扣

    Returns:
        原始搜索结果列表，每项包含 title/url/content
    """
    try:
        from src.tools.tavily_search import _HAS_TAVILY, _get_client, _run_sync

        if not _HAS_TAVILY:
            return []

        client = _get_client()
        if not client:
            return []

        # 构造搜索查询：关键词 + 黑五/折扣上下文
        query = f"{keyword} Black Friday deals 2026 discount coupon"
        result = await _run_sync(
            client.search,
            query=query,
            max_results=8,
            include_raw_content=False,
        )

        if not result or "results" not in result:
            return []

        items = []
        for r in result.get("results", []):
            items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            })
        logger.info("[BlackFriday] Tavily 搜索 '%s' 返回 %d 条", keyword, len(items))
        return items

    except ImportError:
        logger.debug("[BlackFriday] tavily_search 不可用")
    except Exception as e:
        logger.warning("[BlackFriday] Tavily 搜索异常: %s", e)
    return []


async def _search_via_jina(keyword: str) -> list[dict]:
    """通过 Jina Reader 搜索折扣（Tavily 降级方案）

    Returns:
        简单的搜索结果列表
    """
    try:
        from src.tools.jina_reader import jina_search

        query = f"{keyword} Black Friday deals discount 2026"
        raw = await jina_search(query, max_results=5)
        if not raw or len(raw) < 50:
            return []

        # Jina 返回的是纯文本，封装为统一格式
        return [{"title": f"{keyword} deals", "url": "", "content": raw[:3000]}]

    except ImportError:
        logger.debug("[BlackFriday] jina_reader 不可用")
    except Exception as e:
        logger.warning("[BlackFriday] Jina 搜索异常: %s", e)
    return []


async def _extract_deals_with_llm(keyword: str, raw_results: list[dict]) -> list[BlackFridayDeal]:
    """用 LLM 从搜索结果中提取结构化的折扣信息

    把搜索到的原始文本交给 LLM，让它提取出供应商、价格、折扣等字段。
    """
    if not raw_results:
        return []

    # 拼接搜索结果文本（限制长度）
    context_parts = []
    for r in raw_results[:8]:
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")[:500]
        context_parts.append(f"[{title}]\n{url}\n{content}")
    context = "\n\n---\n\n".join(context_parts)
    if len(context) > 4000:
        context = context[:4000]

    try:
        from src.constants import FAMILY_FAST
        from src.litellm_router import free_pool

        if not free_pool:
            return _fallback_parse(keyword, raw_results)

        prompt = (
            f"从以下搜索结果中提取关于「{keyword}」的 Black Friday / 折扣优惠信息。\n\n"
            "要求：\n"
            "1. 只提取真实的折扣优惠，忽略广告和无关内容\n"
            "2. 每条优惠包含：vendor(供应商名), deal_title(优惠标题), price(价格), "
            "discount_pct(折扣幅度), url(链接), expires(过期时间)\n"
            '3. 输出 JSON: {"deals":[{...}]}\n'
            "4. 最多提取 10 条，按折扣力度排序\n"
            "5. 如果搜索结果中没有明确的折扣信息，返回空列表\n\n"
            f"搜索结果：\n{context}"
        )

        resp = await free_pool.acompletion(
            model_family=FAMILY_FAST,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.2,
        )

        content_text = resp.choices[0].message.content if resp and resp.choices else ""
        if not content_text:
            return _fallback_parse(keyword, raw_results)

        import json_repair
        data = json_repair.loads(content_text)
        if not isinstance(data, dict):
            return _fallback_parse(keyword, raw_results)

        deals_raw = data.get("deals", [])
        if not isinstance(deals_raw, list):
            return _fallback_parse(keyword, raw_results)

        deals = []
        for item in deals_raw[:10]:
            if not isinstance(item, dict):
                continue
            vendor = (item.get("vendor") or "").strip()
            title = (item.get("deal_title") or "").strip()
            if not title:
                continue
            deals.append(BlackFridayDeal(
                vendor=vendor or "Unknown",
                deal_title=title,
                price=(item.get("price") or "").strip(),
                discount_pct=(item.get("discount_pct") or "").strip(),
                url=(item.get("url") or "").strip(),
                expires=(item.get("expires") or "").strip(),
                source="llm_extract",
            ))
        return deals

    except ImportError:
        logger.debug("[BlackFriday] LLM 依赖不可用，降级到简单解析")
    except Exception as e:
        logger.warning("[BlackFriday] LLM 提取折扣失败: %s", e)

    return _fallback_parse(keyword, raw_results)


def _fallback_parse(keyword: str, raw_results: list[dict]) -> list[BlackFridayDeal]:
    """LLM 不可用时的简单降级解析 — 直接把搜索结果转为 Deal 条目"""
    deals = []
    for r in raw_results[:8]:
        title = r.get("title", "").strip()
        url = r.get("url", "").strip()
        content = r.get("content", "").strip()[:200]
        if not title:
            continue
        # 只保留标题/内容中包含关键词的结果
        combined = (title + " " + content).lower()
        if keyword.lower() not in combined:
            continue
        deals.append(BlackFridayDeal(
            vendor="",
            deal_title=title,
            price="",
            discount_pct="",
            url=url,
            expires="",
            source="raw_search",
        ))
    return deals


# ── 主入口 ────────────────────────────────────────────

async def scan_blackfriday_deals(keyword: str) -> list[BlackFridayDeal]:
    """扫描全球黑五折扣 — 主入口

    流程:
    1. 用 Tavily（或降级 Jina）搜索关键词相关的全球折扣
    2. 用 LLM 提取结构化折扣信息
    3. 通过 SQLite 数据库去重，过滤已推送的
    4. 标记新 deal 为已推送，返回结果

    Args:
        keyword: 搜索关键词，如 "VPS"、"GPU"、"域名"

    Returns:
        去重后的折扣列表（新的、未推送过的）
    """
    if not keyword or not keyword.strip():
        return []

    keyword = keyword.strip()
    logger.info("[BlackFriday] 开始扫描: '%s'", keyword)

    # 第一步：搜索（Tavily 优先，降级 Jina）
    raw_results = await _search_via_tavily(keyword)
    if not raw_results:
        raw_results = await _search_via_jina(keyword)

    if not raw_results:
        logger.info("[BlackFriday] 搜索无结果: '%s'", keyword)
        return []

    # 第二步：LLM 提取结构化数据
    deals = await _extract_deals_with_llm(keyword, raw_results)

    if not deals:
        logger.info("[BlackFriday] 未提取到有效折扣: '%s'", keyword)
        return []

    # 第三步：去重
    new_deals = [d for d in deals if not _is_seen(d.hash_key)]
    logger.info("[BlackFriday] '%s': 提取 %d 条，去重后 %d 条新",
                keyword, len(deals), len(new_deals))

    # 第四步：标记已推送
    if new_deals:
        _mark_seen(new_deals, keyword)

    return new_deals


def format_deals_message(keyword: str, deals: list[BlackFridayDeal]) -> str:
    """将折扣列表格式化为用户可读的消息

    Args:
        keyword: 搜索关键词
        deals: 折扣列表

    Returns:
        格式化的文本消息
    """
    if not deals:
        return (
            f"🔍 未找到「{keyword}」相关的黑五/折扣优惠\n\n"
            "💡 建议：\n"
            "- 换个关键词试试（如 VPS → cloud hosting）\n"
            "- 英文关键词搜索效果更好"
        )

    header = (
        f"🛍️ 「{keyword}」全球折扣速报 ({len(deals)} 条)\n"
        f"{'━' * 25}\n\n"
    )
    body = "\n\n".join(d.to_message() for d in deals)
    footer = f"\n\n{'━' * 25}\n💡 同一条优惠 7 天内不会重复推送"

    return header + body + footer
