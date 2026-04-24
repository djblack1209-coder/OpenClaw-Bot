"""
Execution — 赏金猎人模块
从 execution_hub.py 提取的 GitHub/Web 赏金扫描、评估、管理功能。

参考: https://github.com/nichochar/bounty-hunter (GitHub bounty 自动化)
"""
import json
import logging
import sqlite3
from typing import Any

from json_repair import loads as jloads

from src.execution._ai import ai_pool
from src.execution._db import get_conn
from src.execution._utils import extract_json_object
from src.utils import now_et, scrub_secrets

logger = logging.getLogger(__name__)


def _ensure_bounty_table(db_path: str):
    """确保赏金表存在"""
    try:
        with get_conn(db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS bounty_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT UNIQUE,
                reward_range TEXT DEFAULT '',
                difficulty TEXT DEFAULT 'medium',
                keywords TEXT DEFAULT '',
                status TEXT DEFAULT 'new',
                score REAL DEFAULT 0,
                evaluation TEXT DEFAULT '',
                found_at TEXT,
                updated_at TEXT
            )""")
    except Exception as e:
        logger.error(f"[Bounty] 表创建失败: {scrub_secrets(str(e))}")


def _upsert_lead(conn, lead: dict):
    """插入或更新赏金线索"""
    now = now_et().isoformat()
    try:
        conn.execute(
            """INSERT INTO bounty_leads (source, title, url, reward_range, difficulty, keywords, found_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET
                 reward_range=excluded.reward_range,
                 updated_at=?""",
            (lead.get("source", ""), lead.get("title", ""), lead.get("url", ""),
             lead.get("reward_range", ""), lead.get("difficulty", "medium"),
             json.dumps(lead.get("keywords", []), ensure_ascii=False),
             now, now, now)
        )
    except sqlite3.IntegrityError as e:
        logger.debug("记录已存在(重复忽略): %s", e)
    except Exception as e:
        logger.warning(f"[Bounty] upsert failed: {scrub_secrets(str(e))}")


async def _scan_github_bounties(keywords: list[str]) -> list[dict]:
    """通过 AI 搜索 GitHub bounty issues"""
    kw_str = ", ".join(keywords[:5])
    prompt = (
        f"搜索 GitHub 上与以下关键词相关的 bounty/reward issues: {kw_str}\n"
        "返回 JSON 数组，每项包含: title, url, reward_range, difficulty(easy/medium/hard)\n"
        '格式: [{"title":"...", "url":"https://github.com/...", "reward_range":"$50-200", "difficulty":"medium"}]'
    )
    try:
        result = await ai_pool.call(prompt)
        if result.get("success"):
            raw = result.get("raw", "")
            import re
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                items = jloads(match.group())
                if isinstance(items, list):
                    for item in items:
                        item["source"] = "github"
                    return items
    except Exception as e:
        logger.error(f"[Bounty] GitHub scan failed: {scrub_secrets(str(e))}")
    return []


async def _scan_web_bounties(keywords: list[str]) -> list[dict]:
    """通过 AI 搜索 Web 上的 bounty 机会"""
    kw_str = ", ".join(keywords[:5])
    prompt = (
        f"搜索互联网上与以下技能相关的 bug bounty / 开发赏金机会: {kw_str}\n"
        "包括 Gitcoin, Immunefi, HackerOne 等平台。\n"
        "返回 JSON 数组，每项包含: title, url, reward_range, difficulty, source\n"
    )
    try:
        result = await ai_pool.call(prompt)
        if result.get("success"):
            raw = result.get("raw", "")
            import re
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                items = jloads(match.group())
                if isinstance(items, list):
                    return items
    except Exception as e:
        logger.error(f"[Bounty] Web scan failed: {scrub_secrets(str(e))}")
    return []


async def scan_bounties(
    keywords: list[str] | None = None,
    db_path: str = "",
) -> dict[str, Any]:
    """扫描 GitHub + Web 赏金机会"""
    if not keywords:
        keywords = ["python", "typescript", "ai", "blockchain", "security"]

    _ensure_bounty_table(db_path)

    github_leads = await _scan_github_bounties(keywords)
    web_leads = await _scan_web_bounties(keywords)
    all_leads = github_leads + web_leads

    saved = 0
    try:
        with get_conn(db_path) as conn:
            for lead in all_leads:
                lead["keywords"] = keywords
                _upsert_lead(conn, lead)
                saved += 1
    except Exception as e:
        logger.error(f"[Bounty] batch save failed: {scrub_secrets(str(e))}")

    return {
        "scanned": len(all_leads),
        "saved": saved,
        "github": len(github_leads),
        "web": len(web_leads),
    }


def list_bounty_leads(
    status: str | None = None,
    limit: int = 20,
    db_path: str = "",
) -> list[dict]:
    """列出赏金线索"""
    _ensure_bounty_table(db_path)
    try:
        with get_conn(db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM bounty_leads WHERE status=? ORDER BY score DESC, found_at DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM bounty_leads ORDER BY score DESC, found_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            cols = [d[0] for d in conn.execute("SELECT * FROM bounty_leads LIMIT 0").description]
            return [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        logger.error(f"[Bounty] list failed: {scrub_secrets(str(e))}")
        return []


async def evaluate_bounty_lead(lead_id: int, db_path: str = "") -> dict:
    """AI 评估单个赏金线索的可行性"""
    _ensure_bounty_table(db_path)
    try:
        with get_conn(db_path) as conn:
            row = conn.execute("SELECT * FROM bounty_leads WHERE id=?", (lead_id,)).fetchone()
            if not row:
                return {"error": "Lead not found"}
            cols = [d[0] for d in conn.execute("SELECT * FROM bounty_leads LIMIT 0").description]
            lead = dict(zip(cols, row))

        prompt = (
            f"评估这个赏金任务的可行性:\n"
            f"标题: {lead['title']}\n"
            f"来源: {lead['source']}\n"
            f"奖金: {lead['reward_range']}\n"
            f"难度: {lead['difficulty']}\n"
            f"URL: {lead['url']}\n\n"
            "请评估: 1) 预计耗时 2) 技术难度 3) 性价比评分(1-10) 4) 建议是否接取\n"
            '返回 JSON: {"hours": 5, "score": 7, "recommend": true, "reason": "..."}'
        )
        result = await ai_pool.call(prompt)
        if result.get("success"):
            parsed = extract_json_object(result.get("raw", ""))
            if parsed:
                with get_conn(db_path) as conn:
                    conn.execute(
                        "UPDATE bounty_leads SET score=?, evaluation=?, updated_at=? WHERE id=?",
                        (parsed.get("score", 0), json.dumps(parsed, ensure_ascii=False),
                         now_et().isoformat(), lead_id)
                    )
                return parsed
        return {"error": "AI evaluation failed"}
    except Exception as e:
        logger.error(f"[Bounty] evaluate failed: {scrub_secrets(str(e))}")
        return {"error": str(e)}


async def run_bounty_hunter(db_path: str = "") -> dict[str, Any]:
    """一键运行赏金猎人: 扫描 → 评估 → 推荐"""
    scan_result = await scan_bounties(db_path=db_path)
    leads = list_bounty_leads(status="new", limit=10, db_path=db_path)

    evaluated = 0
    recommended = []
    for lead in leads[:5]:  # 评估前5个
        eval_result = await evaluate_bounty_lead(lead["id"], db_path=db_path)
        if eval_result.get("recommend"):
            recommended.append({**lead, "evaluation": eval_result})
            evaluated += 1

    return {
        "scan": scan_result,
        "evaluated": evaluated,
        "recommended": recommended,
    }
