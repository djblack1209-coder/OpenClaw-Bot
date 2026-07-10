"""Intel Brief SQLite 存储工具。"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).with_name("intel_brief_schema.sql")


def _normalize_name(name: str) -> str:
    """把用户输入姓名规范成用于复用抓取结果的 key。"""
    compact = re.sub(r"\s+", " ", str(name or "").strip())
    return compact.casefold()


def _display_name(name: str) -> str:
    """保留用户输入的可读姓名，同时去掉多余空白。"""
    return re.sub(r"\s+", " ", str(name or "").strip())


def initialize_intel_db(db_path: str | Path) -> None:
    """初始化 Intel Brief 独立数据库。"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(path) as conn:
        conn.executescript(schema)
        conn.commit()


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
    }


def get_source_health(db_path: str | Path, source_name: str) -> dict[str, Any]:
    """读取单个数据源健康状态；不存在时返回空 dict。"""
    initialize_intel_db(db_path)
    normalized = str(source_name or "").strip().lower().replace("-", "_")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT source_name, last_success_at, last_failure_at, last_failure_reason, failure_count, updated_at
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
