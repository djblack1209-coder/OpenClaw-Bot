"""Intel Brief SQLite 存储工具。"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).with_name("intel_brief_schema.sql")
_SCHEMA_VERSION = 4
_INITIALIZED_DATABASES: dict[str, int] = {}
_INITIALIZE_LOCK = threading.Lock()


def _normalize_name(name: str) -> str:
    """把用户输入姓名规范成用于复用抓取结果的 key。"""
    compact = re.sub(r"\s+", " ", str(name or "").strip())
    return compact.casefold()


def _display_name(name: str) -> str:
    """保留用户输入的可读姓名，同时去掉多余空白。"""
    return re.sub(r"\s+", " ", str(name or "").strip())


def _migrate_content_delivery_attempts(conn: sqlite3.Connection) -> None:
    """把旧逐内容投递记录升级为基于稳定事件键的结构。"""
    columns = {str(row[1]): row for row in conn.execute("PRAGMA table_info(content_delivery_attempts)")}
    content_item = columns.get("content_item_id")
    if "event_key" in columns and content_item is not None and int(content_item[3]) == 0:
        return

    legacy_table = "content_delivery_attempts_legacy_v3"
    conn.execute("DROP INDEX IF EXISTS idx_delivery_attempts_state")
    conn.execute(f"ALTER TABLE content_delivery_attempts RENAME TO {legacy_table}")
    conn.execute(
        """
        CREATE TABLE content_delivery_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER NOT NULL,
            content_item_id INTEGER,
            event_key TEXT NOT NULL,
            brief_id INTEGER,
            state TEXT NOT NULL CHECK (state IN ('pending', 'sent', 'failed', 'unknown')),
            attempt_count INTEGER NOT NULL DEFAULT 1,
            last_error TEXT,
            attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (subscriber_id, event_key),
            FOREIGN KEY (subscriber_id) REFERENCES subscribers(id),
            FOREIGN KEY (content_item_id) REFERENCES content_items(id),
            FOREIGN KEY (brief_id) REFERENCES intel_briefs(id)
        )
        """
    )
    event_key_expr = "NULLIF(legacy.event_key, '')" if "event_key" in columns else "NULL"
    rows = conn.execute(
        f"""
        SELECT
            legacy.subscriber_id,
            legacy.content_item_id,
            COALESCE(
                {event_key_expr},
                NULLIF(items.event_key, ''),
                'legacy-content-item:' || legacy.content_item_id,
                'legacy-attempt:' || legacy.id
            ),
            legacy.brief_id,
            legacy.state,
            legacy.attempt_count,
            legacy.last_error,
            legacy.attempted_at,
            legacy.updated_at
        FROM {legacy_table} AS legacy
        LEFT JOIN content_items AS items ON items.id=legacy.content_item_id
        ORDER BY legacy.id
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            INSERT INTO content_delivery_attempts (
                subscriber_id, content_item_id, event_key, brief_id, state,
                attempt_count, last_error, attempted_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subscriber_id, event_key) DO UPDATE SET
                content_item_id=COALESCE(content_delivery_attempts.content_item_id, excluded.content_item_id),
                brief_id=COALESCE(excluded.brief_id, content_delivery_attempts.brief_id),
                state=CASE
                    WHEN excluded.state='sent' THEN 'sent'
                    WHEN excluded.state='unknown' AND content_delivery_attempts.state!='sent' THEN 'unknown'
                    WHEN content_delivery_attempts.state NOT IN ('sent', 'unknown') THEN excluded.state
                    ELSE content_delivery_attempts.state
                END,
                attempt_count=MAX(content_delivery_attempts.attempt_count, excluded.attempt_count),
                last_error=COALESCE(excluded.last_error, content_delivery_attempts.last_error),
                attempted_at=MIN(content_delivery_attempts.attempted_at, excluded.attempted_at),
                updated_at=MAX(content_delivery_attempts.updated_at, excluded.updated_at)
            """,
            row,
        )
    conn.execute(f"DROP TABLE {legacy_table}")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_delivery_attempts_state
        ON content_delivery_attempts (subscriber_id, state, updated_at DESC)
        """
    )


def initialize_intel_db(db_path: str | Path) -> None:
    """以幂等增量迁移初始化 Intel Brief 独立数据库。"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = str(path.resolve())
    inode = path.stat().st_ino if path.exists() else -1
    if _INITIALIZED_DATABASES.get(resolved) == inode and inode >= 0:
        return
    with _INITIALIZE_LOCK:
        inode = path.stat().st_ino if path.exists() else -1
        if _INITIALIZED_DATABASES.get(resolved) == inode and inode >= 0:
            return
        schema = _SCHEMA_PATH.read_text(encoding="utf-8")
        with sqlite3.connect(path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            previous_schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            conn.executescript(schema)
            conn.execute("BEGIN IMMEDIATE")
            _migrate_content_delivery_attempts(conn)
            delivery_columns = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(delivery_preferences)").fetchall()
            }
            if "content_language" not in delivery_columns:
                conn.execute("ALTER TABLE delivery_preferences ADD COLUMN content_language TEXT NOT NULL DEFAULT 'zh'")
            if previous_schema_version < 3:
                conn.execute(
                    """
                    UPDATE delivery_preferences
                    SET frequency=CASE WHEN frequency='weekly' THEN 'weekly' ELSE 'daily' END,
                        delivery_time='08:30',
                        timezone='Asia/Singapore',
                        updated_at=CURRENT_TIMESTAMP
                    """
                )
            source_health_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(source_health)").fetchall()}
            source_health_additions = {
                "last_status": "TEXT NOT NULL DEFAULT ''",
                "last_attempt_at": "TEXT",
                "latency_ms": "INTEGER NOT NULL DEFAULT 0",
                "item_count": "INTEGER NOT NULL DEFAULT 0",
                "worker": "TEXT NOT NULL DEFAULT ''",
                "fallback_used": "INTEGER NOT NULL DEFAULT 0",
                "consecutive_failures": "INTEGER NOT NULL DEFAULT 0",
            }
            for column, declaration in source_health_additions.items():
                if column not in source_health_columns:
                    conn.execute(f"ALTER TABLE source_health ADD COLUMN {column} {declaration}")
            conn.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (1, 'legacy_schema')")
            conn.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (2, 'intel_brief_v2')")
            conn.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (3, 'delivery_claim_lease')")
            conn.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (4, 'delivery_event_key')")
            conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            conn.commit()
        _INITIALIZED_DATABASES[resolved] = path.stat().st_ino


def _canonical_json(payload: Any) -> str:
    """生成稳定 JSON，供哈希、缓存和审计复用。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _content_hash(payload: Any) -> str:
    """计算不含密钥的结构化内容哈希。"""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def save_intel_brief(
    db_path: str | Path,
    *,
    brief_date: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """保存完整结构化简报，并返回稳定公开引用。"""
    initialize_intel_db(db_path)
    payload_text = _canonical_json(payload)
    content_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    public_ref = hashlib.sha256(f"{brief_date}\0{content_hash}".encode()).hexdigest()[:12]
    item_count = len(payload.get("items", [])) if isinstance(payload.get("items"), list) else 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT INTO intel_briefs (public_ref, brief_date, content_hash, source_payload, item_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(brief_date, content_hash) DO UPDATE SET
                source_payload=excluded.source_payload,
                item_count=excluded.item_count
            """,
            (public_ref, brief_date, content_hash, payload_text, item_count),
        )
        row = conn.execute(
            """
            SELECT id, public_ref, brief_date, content_hash, source_payload, item_count, created_at
            FROM intel_briefs WHERE brief_date=? AND content_hash=?
            """,
            (brief_date, content_hash),
        ).fetchone()
        conn.commit()
    if row is None:
        raise RuntimeError("结构化简报保存失败")
    return {
        "id": int(row[0]),
        "public_ref": str(row[1]),
        "brief_date": str(row[2]),
        "content_hash": str(row[3]),
        "payload": json.loads(str(row[4])),
        "item_count": int(row[5]),
        "created_at": str(row[6]),
    }


def save_intel_brief_localization(
    db_path: str | Path,
    *,
    brief_id: int,
    language: str,
    translator_version: str,
    status: str,
    payload: dict[str, Any],
) -> None:
    """保存指定简报语言版本，重复生成时原位更新。"""
    if language not in {"zh", "en"}:
        raise ValueError("language 仅支持 zh/en")
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT INTO intel_brief_localizations (
                brief_id, language, translator_version, status, localized_payload
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(brief_id, language, translator_version) DO UPDATE SET
                status=excluded.status,
                localized_payload=excluded.localized_payload,
                updated_at=CURRENT_TIMESTAMP
            """,
            (brief_id, language, translator_version, status, _canonical_json(payload)),
        )
        conn.commit()


def get_intel_brief(
    db_path: str | Path,
    *,
    public_ref: str,
    language: str | None = None,
) -> dict[str, Any]:
    """按公开引用读取简报；有对应语言缓存时优先返回缓存。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM intel_briefs WHERE public_ref=?",
            (str(public_ref or "").strip(),),
        ).fetchone()
        if row is None:
            return {}
        payload = json.loads(str(row["source_payload"]))
        localization_status = "source"
        translator_version = ""
        if language in {"zh", "en"}:
            localized = conn.execute(
                """
                SELECT localized_payload, status, translator_version
                FROM intel_brief_localizations
                WHERE brief_id=? AND language=?
                ORDER BY updated_at DESC, id DESC LIMIT 1
                """,
                (int(row["id"]), language),
            ).fetchone()
            if localized is not None:
                payload = json.loads(str(localized["localized_payload"]))
                localization_status = str(localized["status"])
                translator_version = str(localized["translator_version"])
    return {
        "id": int(row["id"]),
        "public_ref": str(row["public_ref"]),
        "brief_date": str(row["brief_date"]),
        "content_hash": str(row["content_hash"]),
        "item_count": int(row["item_count"]),
        "payload": payload,
        "language": language or "source",
        "localization_status": localization_status,
        "translator_version": translator_version,
    }


def record_delivery_artifact(
    db_path: str | Path,
    *,
    delivery_log_id: int | None,
    subscriber_id: int,
    brief_id: int,
    language: str,
    render_mode: str,
    message_ids: list[str],
    envelope: dict[str, Any],
    media_asset_key: str = "",
    delivery_state: str = "sent",
) -> int:
    """记录可完整回放的投递产物。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.execute(
            """
            INSERT INTO delivery_artifacts (
                delivery_log_id, subscriber_id, brief_id, language, render_mode,
                message_ids, envelope_json, media_asset_key, delivery_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delivery_log_id,
                subscriber_id,
                brief_id,
                language,
                render_mode,
                _canonical_json(message_ids),
                _canonical_json(envelope),
                media_asset_key or None,
                delivery_state,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_latest_delivery_artifact(
    db_path: str | Path,
    *,
    subscriber_id: int,
) -> dict[str, Any]:
    """读取订阅者最近一次完整投递产物。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT da.*, ib.public_ref, ib.brief_date
            FROM delivery_artifacts da
            JOIN intel_briefs ib ON ib.id=da.brief_id
            WHERE da.subscriber_id=? AND da.delivery_state='sent'
            ORDER BY da.created_at DESC, da.id DESC LIMIT 1
            """,
            (subscriber_id,),
        ).fetchone()
    if row is None:
        return {}
    return {
        "id": int(row["id"]),
        "brief_id": int(row["brief_id"]),
        "public_ref": str(row["public_ref"]),
        "brief_date": str(row["brief_date"]),
        "language": str(row["language"]),
        "render_mode": str(row["render_mode"]),
        "message_ids": json.loads(str(row["message_ids"])),
        "envelope": json.loads(str(row["envelope_json"])),
        "media_asset_key": str(row["media_asset_key"] or ""),
        "created_at": str(row["created_at"]),
    }


def has_successful_delivery_for_date(
    db_path: str | Path,
    *,
    subscriber_id: int,
    brief_date: str,
) -> bool:
    """判断订阅者在某个业务日期是否已经成功收到简报。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM delivery_artifacts da
            JOIN intel_briefs ib ON ib.id=da.brief_id
            WHERE da.subscriber_id=? AND ib.brief_date=? AND da.delivery_state='sent'
            LIMIT 1
            """,
            (subscriber_id, brief_date),
        ).fetchone()
    return row is not None


def claim_delivery(
    db_path: str | Path,
    *,
    subscriber_id: int,
    brief_id: int,
    brief_date: str,
    lease_seconds: int = 900,
) -> dict[str, Any]:
    """原子抢占某订阅者当天简报的外发权，并允许接管过期租约。"""
    initialize_intel_db(db_path)
    token = secrets.token_hex(16)
    lease = max(30, min(int(lease_seconds), 86_400))
    lease_modifier = f"+{lease} seconds"
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO delivery_claims (
                subscriber_id, brief_id, brief_date, claim_token, state, lease_expires_at
            ) VALUES (?, ?, ?, ?, 'claimed', datetime('now', ?))
            """,
            (subscriber_id, brief_id, brief_date, token, lease_modifier),
        ).rowcount
        recovered = False
        retried = False
        if not inserted:
            prior = conn.execute(
                """
                SELECT state,
                       state='claimed' AND COALESCE(lease_expires_at, '1970-01-01 00:00:00') <= CURRENT_TIMESTAMP
                           AS lease_expired
                FROM delivery_claims
                WHERE subscriber_id=? AND brief_date=?
                """,
                (subscriber_id, brief_date),
            ).fetchone()
            recovered = bool(prior is not None and prior["state"] == "claimed" and prior["lease_expired"])
            retried = bool(prior is not None and prior["state"] == "failed")
            updated = conn.execute(
                """
                UPDATE delivery_claims
                SET brief_id=?, claim_token=?, state='claimed',
                    lease_expires_at=datetime('now', ?),
                    attempt_count=attempt_count + 1,
                    last_error=NULL,
                    claimed_at=CURRENT_TIMESTAMP,
                    finalized_at=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE subscriber_id=? AND brief_date=?
                  AND (
                    state='failed'
                    OR (
                        state='claimed'
                        AND COALESCE(lease_expires_at, '1970-01-01 00:00:00') <= CURRENT_TIMESTAMP
                    )
                  )
                """,
                (brief_id, token, lease_modifier, subscriber_id, brief_date),
            ).rowcount
            acquired = bool(updated)
        else:
            acquired = True
        row = conn.execute(
            """
            SELECT state, lease_expires_at, attempt_count
            FROM delivery_claims
            WHERE subscriber_id=? AND brief_date=?
            """,
            (subscriber_id, brief_date),
        ).fetchone()
        conn.commit()
    state = str(row["state"] if row is not None else "")
    if acquired:
        reason = "stale_lease_recovered" if recovered else ("failed_attempt_retried" if retried else "claimed")
    else:
        reason = "already_finalized" if state in {"sent", "unknown"} else "claim_in_progress"
    return {
        "acquired": acquired,
        "claim_token": token if acquired else "",
        "state": state,
        "reason": reason,
        "lease_expires_at": str(row["lease_expires_at"] or "") if row is not None else "",
        "attempt_count": int(row["attempt_count"] or 0) if row is not None else 0,
    }


def finalize_delivery_claim(
    db_path: str | Path,
    *,
    subscriber_id: int,
    brief_date: str,
    claim_token: str,
    state: str,
    error: str = "",
) -> bool:
    """仅允许当前租约持有者终结 claim，防止旧进程覆盖新租约。"""
    if state not in {"sent", "failed", "unknown"}:
        raise ValueError("非法 claim 终态")
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout=30000")
        cursor = conn.execute(
            """
            UPDATE delivery_claims
            SET state=?, lease_expires_at=NULL, last_error=?,
                finalized_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE subscriber_id=? AND brief_date=?
              AND claim_token=? AND state='claimed'
            """,
            (state, error[:500] or None, subscriber_id, brief_date, claim_token),
        )
        conn.commit()
        return bool(cursor.rowcount)


def get_translation_cache(db_path: str | Path, cache_key: str) -> dict[str, Any]:
    """读取字段级翻译缓存。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM content_translation_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()
    return dict(row) if row is not None else {}


def put_translation_cache(
    db_path: str | Path,
    *,
    cache_key: str,
    source_language: str,
    target_language: str,
    translator_version: str,
    status: str,
    source_text: str,
    translated_text: str,
) -> None:
    """写入字段级翻译缓存，不保存任何模型密钥。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO content_translation_cache (
                cache_key, source_language, target_language, translator_version,
                status, source_text_hash, translated_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                status=excluded.status,
                translated_text=excluded.translated_text,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                cache_key,
                source_language,
                target_language,
                translator_version,
                status,
                hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                translated_text,
            ),
        )
        conn.commit()


def get_telegram_media_asset(db_path: str | Path, asset_key: str) -> dict[str, Any]:
    """读取仍有效的 Telegram 媒体引用。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM telegram_media_assets
            WHERE asset_key=? AND invalidated_at IS NULL
            """,
            (asset_key,),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE telegram_media_assets SET last_used_at=CURRENT_TIMESTAMP WHERE asset_key=?",
                (asset_key,),
            )
            conn.commit()
    return dict(row) if row is not None else {}


def put_telegram_media_asset(
    db_path: str | Path,
    *,
    asset_key: str,
    file_id: str,
    file_unique_id: str,
    mime_type: str,
    byte_size: int,
    content_hash: str,
) -> None:
    """保存同一 Bot 可复用的 Telegram file_id。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO telegram_media_assets (
                asset_key, file_id, file_unique_id, mime_type, byte_size, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_key) DO UPDATE SET
                file_id=excluded.file_id,
                file_unique_id=excluded.file_unique_id,
                mime_type=excluded.mime_type,
                byte_size=excluded.byte_size,
                content_hash=excluded.content_hash,
                invalidated_at=NULL,
                last_used_at=CURRENT_TIMESTAMP
            """,
            (asset_key, file_id, file_unique_id or None, mime_type, int(byte_size), content_hash),
        )
        conn.commit()


def invalidate_telegram_media_asset(db_path: str | Path, asset_key: str) -> None:
    """标记失效 file_id，后续投递会重新上传。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE telegram_media_assets SET invalidated_at=CURRENT_TIMESTAMP WHERE asset_key=?",
            (asset_key,),
        )
        conn.commit()


def delivered_event_keys(
    db_path: str | Path,
    *,
    subscriber_id: int,
    event_keys: list[str],
) -> set[str]:
    """查询订阅者已成功或结果未知的事件键，防止跨日重复。"""
    cleaned = sorted({str(key).strip() for key in event_keys if str(key).strip()})
    if not cleaned:
        return set()
    initialize_intel_db(db_path)
    placeholders = ",".join("?" for _ in cleaned)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT event_key FROM content_delivery_attempts
            WHERE subscriber_id=? AND state IN ('sent', 'unknown')
              AND event_key IN ({placeholders})
            """,
            (subscriber_id, *cleaned),
        ).fetchall()
    return {str(row[0]) for row in rows}


def record_content_delivery_attempts(
    db_path: str | Path,
    *,
    subscriber_id: int,
    brief_id: int | None,
    event_keys: list[str],
    state: str,
    error: str = "",
) -> None:
    """批量记录逐条投递状态；sent/unknown 后不会自动重发。"""
    if state not in {"pending", "sent", "failed", "unknown"}:
        raise ValueError("非法投递状态")
    cleaned = sorted({str(key).strip() for key in event_keys if str(key).strip()})
    if not cleaned:
        return
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for event_key in cleaned:
            conn.execute(
                """
                INSERT INTO content_delivery_attempts (
                    subscriber_id, event_key, brief_id, state, last_error
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(subscriber_id, event_key) DO UPDATE SET
                    brief_id=excluded.brief_id,
                    state=excluded.state,
                    attempt_count=content_delivery_attempts.attempt_count + 1,
                    last_error=excluded.last_error,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (subscriber_id, event_key, brief_id, state, error[:500] or None),
            )
        conn.commit()


def persist_content_pipeline_run(
    db_path: str | Path,
    *,
    run_key: str,
    brief_date: str,
    items: list[Any],
    pipeline_result: Any,
    source_coverage: dict[str, Any] | None = None,
    baseline_only: bool = False,
) -> int:
    """持久化内容事实、观察和逐候选决定，支持完整来源追溯。"""
    initialize_intel_db(db_path)
    coverage = source_coverage or {}
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO brief_runs (
                run_key, brief_date, status, baseline_only,
                fresh_sources, cached_sources, failed_sources, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(run_key) DO UPDATE SET
                status=excluded.status,
                baseline_only=excluded.baseline_only,
                fresh_sources=excluded.fresh_sources,
                cached_sources=excluded.cached_sources,
                failed_sources=excluded.failed_sources,
                completed_at=CURRENT_TIMESTAMP
            """,
            (
                run_key,
                brief_date,
                "success" if getattr(pipeline_result, "selected", ()) else "empty",
                1 if baseline_only else 0,
                _canonical_json(coverage.get("fresh_sources", [])),
                _canonical_json(coverage.get("cached_sources", [])),
                _canonical_json(coverage.get("failed_sources", [])),
            ),
        )
        brief_run_id = int(conn.execute("SELECT id FROM brief_runs WHERE run_key=?", (run_key,)).fetchone()[0])
        content_ids: dict[str, int] = {}
        for item in items:
            payload = item.to_dict()
            conn.execute(
                """
                INSERT INTO content_items (
                    source_name, content_kind, source_item_id, event_key, entity_key,
                    category, provider, title, summary, source_url, event_at,
                    published_at, observed_at, date_confidence, payload_json,
                    evidence_path, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_name, event_key) DO UPDATE SET
                    title=excluded.title,
                    summary=excluded.summary,
                    source_url=excluded.source_url,
                    event_at=excluded.event_at,
                    published_at=excluded.published_at,
                    observed_at=excluded.observed_at,
                    date_confidence=excluded.date_confidence,
                    payload_json=excluded.payload_json,
                    evidence_path=excluded.evidence_path,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    payload["source_name"],
                    payload["content_kind"],
                    payload["source_item_id"],
                    payload["event_key"],
                    payload["entity_key"],
                    payload["category"],
                    payload["provider"],
                    payload["title"],
                    payload["summary"],
                    payload["source_url"],
                    payload["event_at"] or None,
                    payload["published_at"] or None,
                    payload["observed_at"],
                    payload["date_confidence"],
                    _canonical_json(payload.get("payload", {})),
                    payload["evidence_path"],
                ),
            )
            row = conn.execute(
                "SELECT id FROM content_items WHERE source_name=? AND event_key=?",
                (payload["source_name"], payload["event_key"]),
            ).fetchone()
            if row is None:
                raise RuntimeError("内容事实保存失败")
            content_id = int(row[0])
            content_ids[payload["event_key"]] = content_id
            conn.execute(
                """
                INSERT OR IGNORE INTO content_observations (
                    run_key, content_item_id, observed_at, raw_hash
                ) VALUES (?, ?, ?, ?)
                """,
                (run_key, content_id, payload["observed_at"], _content_hash(payload)),
            )

        selected = {
            entry.item.event_key: (index, entry.score)
            for index, entry in enumerate(getattr(pipeline_result, "selected", ()), 1)
        }
        eligible = {entry.item.event_key: entry.score for entry in getattr(pipeline_result, "eligible", ())}
        rejected = {
            entry.item.event_key: (entry.reason, entry.detail) for entry in getattr(pipeline_result, "rejected", ())
        }
        excluded = {
            entry.item.event_key: (entry.reason, entry.detail) for entry in getattr(pipeline_result, "excluded", ())
        }
        for event_key, content_id in content_ids.items():
            if event_key in selected:
                rank, score = selected[event_key]
                eligible_flag, decision, reason = 1, "selected", "selected_by_score_and_quota"
            elif event_key in excluded:
                rank, score = None, eligible.get(event_key, 0)
                eligible_flag, decision = 1, "excluded"
                reason = ":".join(value for value in excluded[event_key] if value)
            else:
                rank, score = None, eligible.get(event_key, 0)
                eligible_flag, decision = 0, "rejected"
                reason = ":".join(value for value in rejected.get(event_key, ("not_selected", "")) if value)
            event_item = next(item for item in items if item.event_key == event_key)
            freshness_at = event_item.freshness_at
            age_hours = None
            if freshness_at is not None:
                observed = event_item.observed_at
                age_hours = max(0.0, (observed - freshness_at).total_seconds() / 3600)
            conn.execute(
                """
                INSERT INTO brief_candidates (
                    brief_run_id, content_item_id, eligible, decision,
                    age_hours, score, rank_position, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(brief_run_id, content_item_id) DO UPDATE SET
                    eligible=excluded.eligible,
                    decision=excluded.decision,
                    age_hours=excluded.age_hours,
                    score=excluded.score,
                    rank_position=excluded.rank_position,
                    reason=excluded.reason
                """,
                (
                    brief_run_id,
                    content_id,
                    eligible_flag,
                    decision,
                    age_hours,
                    float(score),
                    rank,
                    reason,
                ),
            )
        conn.commit()
    return brief_run_id


def _ensure_subscriber(
    conn: sqlite3.Connection,
    user_id: str,
    channel_type: str,
    channel_user_id: str,
) -> int:
    """确保订阅者存在并返回内部 id。"""
    conn.execute(
        """
        INSERT INTO subscribers (user_id, channel_type, channel_user_id, status, updated_at)
        VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            channel_type=excluded.channel_type,
            channel_user_id=excluded.channel_user_id,
            status='active',
            updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, channel_type, channel_user_id),
    )
    row = conn.execute("SELECT id FROM subscribers WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        raise RuntimeError("订阅者写入失败")
    return int(row[0])


def subscribe_tracking_target(
    db_path: str | Path,
    user_id: str,
    channel_type: str,
    channel_user_id: str,
    target_name: str,
    source_channel: str = "telegram",
) -> dict[str, Any]:
    """订阅开放输入的人物/公众姓名，并记录审计日志。

    同一姓名统一落到 tracking_targets，用 active_subscription_count 支撑后续按目标限流。
    """
    initialize_intel_db(db_path)
    display_name = _display_name(target_name)
    normalized_name = _normalize_name(display_name)
    if not normalized_name:
        raise ValueError("追踪姓名不能为空")

    with sqlite3.connect(db_path) as conn:
        subscriber_id = _ensure_subscriber(conn, user_id, channel_type, channel_user_id)
        conn.execute(
            """
            INSERT INTO tracking_targets (name, normalized_name, active_subscription_count, status)
            VALUES (?, ?, 0, 'active')
            ON CONFLICT(normalized_name) DO UPDATE SET status='active'
            """,
            (display_name, normalized_name),
        )
        target_row = conn.execute(
            "SELECT id FROM tracking_targets WHERE normalized_name=?",
            (normalized_name,),
        ).fetchone()
        if target_row is None:
            raise RuntimeError("追踪目标写入失败")
        target_id = int(target_row[0])

        conn.execute(
            """
            INSERT INTO tracking_subscriptions (subscriber_id, target_id, status)
            VALUES (?, ?, 'active')
            ON CONFLICT(subscriber_id, target_id) DO UPDATE SET status='active'
            """,
            (subscriber_id, target_id),
        )
        conn.execute(
            """
            INSERT INTO tracking_audit_log (subscriber_user_id, target_name, source_channel)
            VALUES (?, ?, ?)
            """,
            (user_id, display_name, source_channel),
        )
        active_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM tracking_subscriptions
            WHERE target_id=? AND status='active'
            """,
            (target_id,),
        ).fetchone()[0]
        conn.execute(
            """
            UPDATE tracking_targets
            SET active_subscription_count=?, status='active'
            WHERE id=?
            """,
            (int(active_count), target_id),
        )
        conn.commit()

    return {
        "target_id": target_id,
        "name": display_name,
        "normalized_name": normalized_name,
        "active_subscription_count": int(active_count),
    }


def _row_to_source_health(row: sqlite3.Row | tuple[Any, ...] | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "source_name": str(row[0] or ""),
        "last_success_at": str(row[1] or ""),
        "last_failure_at": str(row[2] or ""),
        "last_failure_reason": str(row[3] or ""),
        "failure_count": int(row[4] or 0),
        "updated_at": str(row[5] or ""),
        "last_status": str(row[6] or "") if len(row) > 6 else "",
        "last_attempt_at": str(row[7] or "") if len(row) > 7 else "",
        "latency_ms": int(row[8] or 0) if len(row) > 8 else 0,
        "item_count": int(row[9] or 0) if len(row) > 9 else 0,
        "worker": str(row[10] or "") if len(row) > 10 else "",
        "fallback_used": bool(row[11]) if len(row) > 11 else False,
        "consecutive_failures": int(row[12] or 0) if len(row) > 12 else int(row[4] or 0),
    }


def get_source_health(db_path: str | Path, source_name: str) -> dict[str, Any]:
    """读取单个数据源健康状态；不存在时返回空 dict。"""
    initialize_intel_db(db_path)
    normalized = str(source_name or "").strip().lower().replace("-", "_")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT source_name, last_success_at, last_failure_at, last_failure_reason,
                   failure_count, updated_at, last_status, last_attempt_at, latency_ms,
                   item_count, worker, fallback_used, consecutive_failures
            FROM source_health
            WHERE source_name=?
            """,
            (normalized,),
        ).fetchone()
    return _row_to_source_health(row)


def record_source_health(
    db_path: str | Path,
    source_name: str,
    status: str,
    *,
    failure_reason: str = "",
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Upsert source_health after a source/worker attempt.

    `success` resets failure_count so recovery is visible; every non-success
    status increments the consecutive failure counter and stores the latest
    reason. This helper only writes the Intel Brief SQLite DB and does not touch
    external services.
    """
    initialize_intel_db(db_path)
    normalized = str(source_name or "").strip().lower().replace("-", "_")
    if not normalized:
        raise ValueError("source_name is required")
    timestamp = observed_at or "CURRENT_TIMESTAMP"
    is_success = str(status or "").strip().lower() == "success"

    with sqlite3.connect(db_path) as conn:
        if is_success:
            if observed_at:
                conn.execute(
                    """
                    INSERT INTO source_health (
                        source_name, last_success_at, last_failure_reason, failure_count, updated_at
                    ) VALUES (?, ?, NULL, 0, ?)
                    ON CONFLICT(source_name) DO UPDATE SET
                        last_success_at=excluded.last_success_at,
                        last_failure_reason=NULL,
                        failure_count=0,
                        updated_at=excluded.updated_at
                    """,
                    (normalized, timestamp, timestamp),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO source_health (
                        source_name, last_success_at, last_failure_reason, failure_count, updated_at
                    ) VALUES (?, CURRENT_TIMESTAMP, NULL, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_name) DO UPDATE SET
                        last_success_at=CURRENT_TIMESTAMP,
                        last_failure_reason=NULL,
                        failure_count=0,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (normalized,),
                )
        else:
            if observed_at:
                conn.execute(
                    """
                    INSERT INTO source_health (
                        source_name, last_failure_at, last_failure_reason, failure_count, updated_at
                    ) VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(source_name) DO UPDATE SET
                        last_failure_at=excluded.last_failure_at,
                        last_failure_reason=excluded.last_failure_reason,
                        failure_count=source_health.failure_count + 1,
                        updated_at=excluded.updated_at
                    """,
                    (normalized, timestamp, failure_reason, timestamp),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO source_health (
                        source_name, last_failure_at, last_failure_reason, failure_count, updated_at
                    ) VALUES (?, CURRENT_TIMESTAMP, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_name) DO UPDATE SET
                        last_failure_at=CURRENT_TIMESTAMP,
                        last_failure_reason=excluded.last_failure_reason,
                        failure_count=source_health.failure_count + 1,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (normalized, failure_reason),
                )
        conn.commit()
    return get_source_health(db_path, normalized)


def record_source_attempt(
    db_path: str | Path,
    *,
    run_key: str,
    source_name: str,
    attempted_at: str,
    status: str,
    latency_ms: int = 0,
    item_count: int = 0,
    worker: str = "",
    fallback_used: bool = False,
    failure_reason: str = "",
) -> None:
    """把最终来源尝试写入中央库，并同步来源健康快照。"""
    initialize_intel_db(db_path)
    normalized = str(source_name or "").strip().lower().replace("-", "_")
    if not normalized:
        raise ValueError("source_name is required")
    normalized_status = str(status or "failed").strip().lower()
    successful = normalized_status == "success"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO source_attempts (
                run_key, source_name, attempted_at, status, latency_ms,
                item_count, worker, fallback_used, failure_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_key, source_name) DO UPDATE SET
                attempted_at=excluded.attempted_at,
                status=excluded.status,
                latency_ms=excluded.latency_ms,
                item_count=excluded.item_count,
                worker=excluded.worker,
                fallback_used=excluded.fallback_used,
                failure_reason=excluded.failure_reason
            """,
            (
                run_key,
                normalized,
                attempted_at,
                normalized_status,
                max(0, int(latency_ms)),
                max(0, int(item_count)),
                str(worker or "")[:200],
                1 if fallback_used else 0,
                str(failure_reason or "")[:500],
            ),
        )
        conn.execute(
            """
            INSERT INTO source_health (
                source_name, last_success_at, last_failure_at, last_failure_reason,
                failure_count, updated_at, last_status, last_attempt_at, latency_ms,
                item_count, worker, fallback_used, consecutive_failures
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name) DO UPDATE SET
                last_success_at=CASE WHEN excluded.last_status='success'
                    THEN excluded.last_success_at ELSE source_health.last_success_at END,
                last_failure_at=CASE WHEN excluded.last_status!='success'
                    THEN excluded.last_failure_at ELSE source_health.last_failure_at END,
                last_failure_reason=CASE WHEN excluded.last_status='success'
                    THEN NULL ELSE excluded.last_failure_reason END,
                failure_count=CASE WHEN excluded.last_status='success'
                    THEN 0 ELSE source_health.failure_count + 1 END,
                updated_at=excluded.updated_at,
                last_status=excluded.last_status,
                last_attempt_at=excluded.last_attempt_at,
                latency_ms=excluded.latency_ms,
                item_count=excluded.item_count,
                worker=excluded.worker,
                fallback_used=excluded.fallback_used,
                consecutive_failures=CASE WHEN excluded.last_status='success'
                    THEN 0 ELSE source_health.consecutive_failures + 1 END
            """,
            (
                normalized,
                attempted_at if successful else None,
                None if successful else attempted_at,
                None if successful else str(failure_reason or "")[:500],
                0 if successful else 1,
                attempted_at,
                normalized_status,
                attempted_at,
                max(0, int(latency_ms)),
                max(0, int(item_count)),
                str(worker or "")[:200],
                1 if fallback_used else 0,
                0 if successful else 1,
            ),
        )
        conn.commit()


def put_source_last_good(
    db_path: str | Path,
    *,
    source_name: str,
    captured_at: str,
    expires_at: str,
    payload: dict[str, Any],
) -> None:
    """保存来源最后一次有效响应，供短时降级使用。"""
    initialize_intel_db(db_path)
    payload_text = _canonical_json(payload)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO source_last_good (
                source_name, captured_at, expires_at, payload_json, payload_hash
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_name) DO UPDATE SET
                captured_at=excluded.captured_at,
                expires_at=excluded.expires_at,
                payload_json=excluded.payload_json,
                payload_hash=excluded.payload_hash,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                str(source_name or "").strip().lower().replace("-", "_"),
                captured_at,
                expires_at,
                payload_text,
                hashlib.sha256(payload_text.encode("utf-8")).hexdigest(),
            ),
        )
        conn.commit()


def get_source_last_good(
    db_path: str | Path,
    *,
    source_name: str,
    now: str,
) -> dict[str, Any]:
    """读取仍在 TTL 内的最后有效响应。"""
    initialize_intel_db(db_path)
    normalized = str(source_name or "").strip().lower().replace("-", "_")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT captured_at, expires_at, payload_json, payload_hash
            FROM source_last_good
            WHERE source_name=? AND expires_at>=?
            """,
            (normalized, now),
        ).fetchone()
    if row is None:
        return {}
    return {
        "source_name": normalized,
        "captured_at": str(row["captured_at"]),
        "expires_at": str(row["expires_at"]),
        "payload": json.loads(str(row["payload_json"])),
        "payload_hash": str(row["payload_hash"]),
    }


def get_content_pipeline_state(db_path: str | Path, state_key: str) -> str:
    """读取内容管道水位。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT state_value FROM content_pipeline_state WHERE state_key=?",
            (state_key,),
        ).fetchone()
    return str(row[0]) if row is not None else ""


def set_content_pipeline_state(db_path: str | Path, state_key: str, state_value: str) -> None:
    """幂等更新内容管道水位。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO content_pipeline_state (state_key, state_value)
            VALUES (?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                state_value=excluded.state_value,
                updated_at=CURRENT_TIMESTAMP
            """,
            (state_key, state_value),
        )
        conn.commit()


def get_content_observation_counts_for_run(
    db_path: str | Path,
    *,
    run_key: str,
    source_names: list[str] | tuple[str, ...],
) -> dict[str, int]:
    """按运行和来源统计已持久化观察数，供基线完成条件审计。"""
    initialize_intel_db(db_path)
    normalized_sources = sorted(
        {
            str(source_name or "").strip().lower().replace("-", "_")
            for source_name in source_names
            if str(source_name or "").strip()
        }
    )
    if not normalized_sources:
        return {}
    placeholders = ", ".join("?" for _ in normalized_sources)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT ci.source_name, COUNT(co.id)
            FROM content_observations co
            JOIN content_items ci ON ci.id=co.content_item_id
            WHERE co.run_key=? AND ci.source_name IN ({placeholders})
            GROUP BY ci.source_name
            ORDER BY ci.source_name
            """,
            (run_key, *normalized_sources),
        ).fetchall()
    observed = {str(row[0]): int(row[1]) for row in rows}
    return {source_name: observed.get(source_name, 0) for source_name in normalized_sources}


def get_active_tracking_terms(db_path: str | Path) -> list[str]:
    """返回至少有一个有效订阅者关注的追踪词。"""
    initialize_intel_db(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM tracking_targets
            WHERE status='active' AND active_subscription_count>0
            ORDER BY active_subscription_count DESC, normalized_name ASC
            """
        ).fetchall()
    return [str(row[0]) for row in rows if str(row[0] or "").strip()]


def get_recent_entity_observations(
    db_path: str | Path,
    *,
    source_name: str,
    since: str,
) -> dict[str, str]:
    """读取近期入选或基线实体的最后观察时间，供跨运行冷却使用。"""
    initialize_intel_db(db_path)
    normalized = str(source_name or "").strip().lower().replace("-", "_")
    if not normalized:
        return {}
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT ci.entity_key, MAX(co.observed_at)
            FROM content_items ci
            JOIN content_observations co ON co.content_item_id=ci.id
            JOIN brief_candidates bc ON bc.content_item_id=ci.id
            JOIN brief_runs br ON br.id=bc.brief_run_id
            WHERE ci.source_name=? AND co.observed_at>=?
              AND (
                bc.decision='selected'
                OR (br.baseline_only=1 AND bc.reason='baseline_only')
              )
            GROUP BY ci.entity_key
            ORDER BY ci.entity_key
            """,
            (normalized, since),
        ).fetchall()
    return {str(row[0]): str(row[1]) for row in rows if str(row[0] or "").strip()}


def get_baseline_event_keys(
    db_path: str | Path,
    *,
    source_names: list[str] | tuple[str, ...],
) -> list[str]:
    """读取已建立基线的事件键，防止旧事件在基线结束后首次入选。"""
    initialize_intel_db(db_path)
    normalized_sources = sorted(
        {
            str(source_name or "").strip().lower().replace("-", "_")
            for source_name in source_names
            if str(source_name or "").strip()
        }
    )
    if not normalized_sources:
        return []
    placeholders = ", ".join("?" for _ in normalized_sources)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT DISTINCT ci.event_key
            FROM content_items ci
            JOIN brief_candidates bc ON bc.content_item_id=ci.id
            JOIN brief_runs br ON br.id=bc.brief_run_id
            WHERE br.baseline_only=1
              AND bc.reason='baseline_only'
              AND ci.source_name IN ({placeholders})
            ORDER BY ci.event_key
            """,
            normalized_sources,
        ).fetchall()
    return [str(row[0]) for row in rows if str(row[0] or "").strip()]
