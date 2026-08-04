"""闲鱼对话上下文管理 — SQLite 持久化"""

import hashlib
import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

from src.db_utils import get_conn as _get_db_conn
from src.utils import now_et

logger = logging.getLogger(__name__)

# 订单通知状态
NOTIFY_NONE = 0  # 未通知
NOTIFY_ORDER = 1  # 已发下单通知
NOTIFY_SHIPMENT = 2  # 已发发货提醒

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DB_PATH = os.path.join(DB_DIR, "xianyu_chat.db")


class XianyuContextManager:
    def __init__(self, max_history: int = 80, db_path: str = DB_PATH):
        self.max_history = max_history
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        """获取 SQLite 连接 (委托给全局连接工厂)"""
        with _get_db_conn(self.db_path) as conn:
            yield conn

    def _init_db(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TEXT DEFAULT (datetime('now'))
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_chat ON messages(chat_id)")
            c.execute("""CREATE TABLE IF NOT EXISTS bargain_counts (
                chat_id TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                updated TEXT DEFAULT (datetime('now'))
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS items (
                item_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated TEXT DEFAULT (datetime('now'))
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                user_id TEXT,
                item_id TEXT,
                status TEXT NOT NULL,
                ts TEXT DEFAULT (datetime('now')),
                notified INTEGER DEFAULT 0
            )""")
            # 新增利润相关字段（兼容已有表）
            try:
                c.execute("ALTER TABLE orders ADD COLUMN amount REAL DEFAULT 0")
            except Exception as e:
                logger.debug("静默异常: %s", e)  # 字段已存在
            try:
                c.execute("ALTER TABLE orders ADD COLUMN cost REAL DEFAULT 0")
            except Exception as e:
                logger.debug("静默异常: %s", e)
            try:
                c.execute("ALTER TABLE orders ADD COLUMN commission_rate REAL DEFAULT 0.06")
            except Exception as e:
                logger.debug("静默异常: %s", e)  # 字段已存在
            # 底价表
            c.execute("""CREATE TABLE IF NOT EXISTS floor_prices (
                item_id TEXT PRIMARY KEY,
                floor_price REAL NOT NULL,
                updated TEXT DEFAULT (datetime('now'))
            )""")
            # 咨询追踪表
            c.execute("""CREATE TABLE IF NOT EXISTS consultations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT DEFAULT '',
                item_id TEXT DEFAULT '',
                first_msg TEXT DEFAULT '',
                first_ts TEXT DEFAULT (datetime('now')),
                last_ts TEXT DEFAULT (datetime('now')),
                msg_count INTEGER DEFAULT 1,
                converted INTEGER DEFAULT 0,
                UNIQUE(chat_id, item_id)
            )""")
            # 回复配置表 — 卖家自定义 AI 回复风格 / FAQ / 商品规则
            c.execute("""CREATE TABLE IF NOT EXISTS reply_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_type TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now')),
                UNIQUE(config_type, key)
            )""")
            # CC中转自动发货审计表：记录已付款 webhook、消息发送和人工补发状态。
            c.execute("""CREATE TABLE IF NOT EXISTS cc_shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                chat_id TEXT DEFAULT '',
                buyer_id TEXT DEFAULT '',
                item_id TEXT DEFAULT '',
                status TEXT NOT NULL,
                delivery_message TEXT DEFAULT '',
                error TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT DEFAULT '',
                resolve_note TEXT DEFAULT '',
                buyer_chain_status TEXT DEFAULT '',
                buyer_chain_verified_at TEXT DEFAULT '',
                buyer_chain_note TEXT DEFAULT '',
                xianyu_confirm_status TEXT DEFAULT '',
                xianyu_confirm_at TEXT DEFAULT '',
                xianyu_confirm_error TEXT DEFAULT '',
                xianyu_relist_status TEXT DEFAULT '',
                xianyu_relist_at TEXT DEFAULT '',
                xianyu_relist_error TEXT DEFAULT '',
                UNIQUE(order_id)
            )""")
            self._ensure_columns(
                c,
                "cc_shipments",
                {
                    "buyer_chain_status": "TEXT DEFAULT ''",
                    "buyer_chain_verified_at": "TEXT DEFAULT ''",
                    "buyer_chain_note": "TEXT DEFAULT ''",
                    "xianyu_confirm_status": "TEXT DEFAULT ''",
                    "xianyu_confirm_at": "TEXT DEFAULT ''",
                    "xianyu_confirm_error": "TEXT DEFAULT ''",
                    "xianyu_relist_status": "TEXT DEFAULT ''",
                    "xianyu_relist_at": "TEXT DEFAULT ''",
                    "xianyu_relist_error": "TEXT DEFAULT ''",
                },
            )
            # CC中转商品映射表：闲鱼 item_id → CC中转套餐/plan_id，避免多商品上架后错发卡密。
            c.execute("""CREATE TABLE IF NOT EXISTS cc_item_mappings (
                item_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                title TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )""")
            # CC中转严格门审计摘要表：只保存脱敏后的同单闭环证据，避免进程重启丢失验收状态。
            c.execute("""CREATE TABLE IF NOT EXISTS cc_strict_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT DEFAULT 'strict',
                ok INTEGER DEFAULT 0,
                exit_code INTEGER DEFAULT 0,
                same_order_ready INTEGER DEFAULT 0,
                same_order_matched INTEGER DEFAULT 0,
                real_orders INTEGER DEFAULT 0,
                summary_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )""")

    @staticmethod
    def _ensure_columns(conn, table: str, columns: dict[str, str]) -> None:
        """给已存在的 SQLite 表补列，保证老库平滑升级。"""
        existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    # ---- messages ----
    def add_message(self, chat_id: str, user_id: str, item_id: str, role: str, content: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO messages(chat_id,user_id,item_id,role,content) VALUES(?,?,?,?,?)",
                (chat_id, user_id, item_id, role, content),
            )
            c.execute(
                "DELETE FROM messages WHERE chat_id=? AND id NOT IN "
                "(SELECT id FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?)",
                (chat_id, chat_id, self.max_history),
            )

    def get_context(self, chat_id: str) -> list[dict[str, str]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id ASC LIMIT ?",
                (chat_id, self.max_history),
            ).fetchall()
        msgs = [{"role": r, "content": ct} for r, ct in rows]
        bc = self.get_bargain_count(chat_id)
        if bc > 0:
            msgs.append({"role": "system", "content": f"议价次数: {bc}"})
        return msgs

    # ---- bargain ----
    def incr_bargain(self, chat_id: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO bargain_counts(chat_id,count) VALUES(?,1) "
                "ON CONFLICT(chat_id) DO UPDATE SET count=count+1, updated=datetime('now')",
                (chat_id,),
            )

    def get_bargain_count(self, chat_id: str) -> int:
        with self._conn() as c:
            row = c.execute("SELECT count FROM bargain_counts WHERE chat_id=?", (chat_id,)).fetchone()
        return row[0] if row else 0

    # ---- items ----
    def save_item(self, item_id: str, data: dict):
        with self._conn() as c:
            c.execute(
                "INSERT INTO items(item_id,data) VALUES(?,?) "
                "ON CONFLICT(item_id) DO UPDATE SET data=?, updated=datetime('now')",
                (item_id, json.dumps(data, ensure_ascii=False), json.dumps(data, ensure_ascii=False)),
            )

    def get_item(self, item_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT data FROM items WHERE item_id=?", (item_id,)).fetchone()
        return json.loads(row[0]) if row else None

    # ---- orders ----
    def record_order(
        self, chat_id: str, user_id: str, item_id: str, status: str, amount: float = 0.0, cost: float = 0.0
    ):
        with self._conn() as c:
            c.execute(
                "INSERT INTO orders(chat_id,user_id,item_id,status,amount,cost) VALUES(?,?,?,?,?,?)",
                (chat_id, user_id, item_id, status, amount, cost),
            )

    def get_unnotified_orders(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id,chat_id,user_id,item_id,status,ts FROM orders WHERE notified=?", (NOTIFY_NONE,)
            ).fetchall()
        return [
            {"id": r[0], "chat_id": r[1], "user_id": r[2], "item_id": r[3], "status": r[4], "ts": r[5]} for r in rows
        ]

    def mark_notified(self, order_id: int):
        with self._conn() as c:
            c.execute("UPDATE orders SET notified=? WHERE id=?", (NOTIFY_ORDER, order_id))

    def upsert_cc_item_mapping(
        self,
        item_id: str,
        plan_id: str,
        title: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        """保存闲鱼商品到 CC中转套餐的映射，返回脱敏后的配置行。"""
        normalized_item_id = (item_id or "").strip()
        normalized_plan_id = (plan_id or "").strip()
        if not normalized_item_id:
            raise ValueError("商品 ID 不能为空")
        if not normalized_plan_id:
            raise ValueError("套餐/planId 不能为空")
        safe_title = (title or "").strip()[:120]
        enabled_int = 1 if enabled else 0
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO cc_item_mappings(item_id,plan_id,title,enabled)
                VALUES(?,?,?,?)
                ON CONFLICT(item_id) DO UPDATE SET
                    plan_id=excluded.plan_id,
                    title=excluded.title,
                    enabled=excluded.enabled,
                    updated_at=datetime('now')
                """,
                (normalized_item_id, normalized_plan_id, safe_title, enabled_int),
            )
        return self.get_cc_item_mapping(normalized_item_id, enabled_only=False) or {
            "item_id": normalized_item_id,
            "plan_id": normalized_plan_id,
            "title": safe_title,
            "enabled": bool(enabled_int),
        }

    @staticmethod
    def _cc_item_mapping_lookup_keys(item_id: str) -> list[str]:
        """生成商品映射查询键，兼容闲鱼短链后缀分享码。"""
        raw = (item_id or "").strip()
        if not raw:
            return []
        keys = [raw]
        first_token = raw.split()[0].strip() if raw.split() else ""
        if first_token and first_token not in keys:
            keys.append(first_token)
        # Markdown 分享文本可能保留括号里的第二个链接，这里提取可见 URL 作为兜底键。
        for match in re.finditer(r"https?://[^\s\]\)「」<>\"']+", raw, re.IGNORECASE):
            candidate = match.group(0).rstrip("，。；;,.")
            if candidate and candidate not in keys:
                keys.append(candidate)
        return keys

    @staticmethod
    def _escape_sql_like(value: str) -> str:
        """转义 SQLite LIKE 通配符，避免短链中的特殊字符扩大匹配范围。"""
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _row_to_cc_item_mapping(self, row) -> dict[str, Any] | None:
        """把 SQLite 行转成商品映射字典。"""
        if not row:
            return None
        return {
            "item_id": row[0],
            "plan_id": row[1],
            "title": row[2] or "",
            "enabled": bool(row[3]),
            "created_at": row[4],
            "updated_at": row[5],
        }

    def get_cc_item_mapping(self, item_id: str, enabled_only: bool = True) -> dict[str, Any] | None:
        """读取单个闲鱼商品映射；短链接有分享码/无分享码都能命中。"""
        lookup_keys = self._cc_item_mapping_lookup_keys(item_id)
        if not lookup_keys:
            return None
        enabled_sql = "AND enabled=1" if enabled_only else ""
        with self._conn() as c:
            for lookup_key in lookup_keys:
                row = c.execute(
                    f"""
                    SELECT item_id,plan_id,title,enabled,created_at,updated_at
                    FROM cc_item_mappings
                    WHERE item_id=? {enabled_sql}
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (lookup_key,),
                ).fetchone()
                mapped = self._row_to_cc_item_mapping(row)
                if mapped:
                    return mapped

            for lookup_key in lookup_keys:
                if not lookup_key.lower().startswith(("http://", "https://")):
                    continue
                like_key = self._escape_sql_like(lookup_key)
                row = c.execute(
                    f"""
                    SELECT item_id,plan_id,title,enabled,created_at,updated_at
                    FROM cc_item_mappings
                    WHERE (item_id LIKE ? ESCAPE '\\' OR item_id LIKE ? ESCAPE '\\') {enabled_sql}
                    ORDER BY enabled DESC, updated_at DESC
                    LIMIT 1
                    """,
                    (f"{like_key} %", f"%({like_key})%"),
                ).fetchone()
                mapped = self._row_to_cc_item_mapping(row)
                if mapped:
                    return mapped
        return None

    def list_cc_item_mappings(self, include_disabled: bool = True) -> list[dict[str, Any]]:
        """列出闲鱼商品到 CC中转套餐的映射，用于本机 GUI 管理。"""
        with self._conn() as c:
            if include_disabled:
                rows = c.execute(
                    """
                    SELECT item_id,plan_id,title,enabled,created_at,updated_at
                    FROM cc_item_mappings
                    ORDER BY updated_at DESC, item_id ASC
                    """
                ).fetchall()
            else:
                rows = c.execute(
                    """
                    SELECT item_id,plan_id,title,enabled,created_at,updated_at
                    FROM cc_item_mappings
                    WHERE enabled=1
                    ORDER BY updated_at DESC, item_id ASC
                    """
                ).fetchall()
        return [
            {
                "item_id": row[0],
                "plan_id": row[1],
                "title": row[2] or "",
                "enabled": bool(row[3]),
                "created_at": row[4],
                "updated_at": row[5],
            }
            for row in rows
        ]

    def delete_cc_item_mapping(self, item_id: str) -> bool:
        """删除闲鱼商品映射，返回是否命中记录。"""
        normalized_item_id = (item_id or "").strip()
        if not normalized_item_id:
            return False
        with self._conn() as c:
            cur = c.execute("DELETE FROM cc_item_mappings WHERE item_id=?", (normalized_item_id,))
        return cur.rowcount > 0

    def record_cc_shipment(
        self,
        order_id: str,
        buyer_id: str = "",
        item_id: str = "",
        chat_id: str = "",
        status: str = "",
        delivery_message: str = "",
        error: str = "",
    ) -> None:
        """记录 CC中转自动发货状态，供本机管理面板排查和人工补发。"""
        safe_error = (error or "")[:500]
        safe_message = delivery_message or ""
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO cc_shipments(order_id,buyer_id,item_id,chat_id,status,delivery_message,error)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(order_id) DO UPDATE SET
                    buyer_id=excluded.buyer_id,
                    item_id=excluded.item_id,
                    chat_id=excluded.chat_id,
                    status=excluded.status,
                    delivery_message=excluded.delivery_message,
                    error=excluded.error,
                    updated_at=datetime('now')
                WHERE cc_shipments.status NOT IN (
                    'message_sent', 'message_send_inflight', 'message_send_uncertain'
                )
                """,
                (order_id, buyer_id, item_id, chat_id, status, safe_message, safe_error),
            )

    def claim_cc_auto_ship_order(
        self,
        order_id: str,
        buyer_id: str = "",
        item_id: str = "",
    ) -> dict[str, Any] | None:
        """原子领取真实订单的 webhook 分配权；同一订单只允许一个执行者。"""
        normalized_order_id = str(order_id or "").strip()
        if not normalized_order_id:
            return None
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            cur = c.execute(
                """
                INSERT INTO cc_shipments(order_id,buyer_id,item_id,status,error)
                VALUES(?,?,?,'webhook_inflight','卡密分配处理中；异常退出时必须人工核对，禁止自动重试')
                ON CONFLICT(order_id) DO UPDATE SET
                    buyer_id=excluded.buyer_id,
                    item_id=excluded.item_id,
                    status='webhook_inflight',
                    error=excluded.error,
                    updated_at=datetime('now')
                WHERE cc_shipments.status='operator_paused'
                """,
                (normalized_order_id, str(buyer_id or ""), str(item_id or "")),
            )
            if cur.rowcount <= 0:
                return None
        return self.get_cc_shipment_by_order_id(normalized_order_id, include_message=True)

    @staticmethod
    def _mask_delivery_preview(message: str) -> str:
        """生成脱敏话术预览，避免列表/状态接口展示完整兑换码。"""
        text = (message or "")[:160]
        return re.sub(r"\b(CC-[A-Z0-9][A-Z0-9-]{4,40})\b", "CC-****-****", text)

    def list_cc_shipments(
        self,
        status: str = "",
        limit: int = 50,
        include_message: bool = False,
    ) -> list[dict[str, Any]]:
        """列出 CC中转自动发货记录；默认只返回话术预览，避免无意展示完整卡密。"""
        limit = max(1, min(int(limit), 200))
        with self._conn() as c:
            if status:
                rows = c.execute(
                    """
                    SELECT id,order_id,chat_id,buyer_id,item_id,status,delivery_message,error,
                           created_at,updated_at,resolved_at,resolve_note,
                           buyer_chain_status,buyer_chain_verified_at,buyer_chain_note,
                           xianyu_confirm_status,xianyu_confirm_at,xianyu_confirm_error,
                           xianyu_relist_status,xianyu_relist_at,xianyu_relist_error
                    FROM cc_shipments WHERE status=? ORDER BY id DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    """
                    SELECT id,order_id,chat_id,buyer_id,item_id,status,delivery_message,error,
                           created_at,updated_at,resolved_at,resolve_note,
                           buyer_chain_status,buyer_chain_verified_at,buyer_chain_note,
                           xianyu_confirm_status,xianyu_confirm_at,xianyu_confirm_error,
                           xianyu_relist_status,xianyu_relist_at,xianyu_relist_error
                    FROM cc_shipments ORDER BY id DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        result = []
        for row in rows:
            message = row[6] or ""
            item = {
                "id": row[0],
                "order_id": row[1],
                "chat_id": row[2],
                "buyer_id": row[3],
                "item_id": row[4],
                "status": row[5],
                "delivery_preview": self._mask_delivery_preview(message),
                "error": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "resolved_at": row[10],
                "resolve_note": row[11],
                "buyer_chain_status": row[12],
                "buyer_chain_verified_at": row[13],
                "buyer_chain_note": row[14],
                "xianyu_confirm_status": row[15],
                "xianyu_confirm_at": row[16],
                "xianyu_confirm_error": row[17],
                "xianyu_relist_status": row[18],
                "xianyu_relist_at": row[19],
                "xianyu_relist_error": row[20],
            }
            if include_message:
                item["delivery_message"] = message
            result.append(item)
        return result

    def get_cc_shipment(self, shipment_id: int, include_message: bool = False) -> dict[str, Any] | None:
        """按 ID 读取一条 CC中转发货记录；默认不返回完整卡密话术。"""
        with self._conn() as c:
            row = c.execute(
                """
                SELECT id,order_id,chat_id,buyer_id,item_id,status,delivery_message,error,
                       created_at,updated_at,resolved_at,resolve_note,
                       buyer_chain_status,buyer_chain_verified_at,buyer_chain_note,
                       xianyu_confirm_status,xianyu_confirm_at,xianyu_confirm_error,
                       xianyu_relist_status,xianyu_relist_at,xianyu_relist_error
                FROM cc_shipments WHERE id=?
                """,
                (int(shipment_id),),
            ).fetchone()
        if not row:
            return None
        message = row[6] or ""
        item = {
            "id": row[0],
            "order_id": row[1],
            "chat_id": row[2],
            "buyer_id": row[3],
            "item_id": row[4],
            "status": row[5],
            "delivery_preview": self._mask_delivery_preview(message),
            "error": row[7],
            "created_at": row[8],
            "updated_at": row[9],
            "resolved_at": row[10],
            "resolve_note": row[11],
            "buyer_chain_status": row[12],
            "buyer_chain_verified_at": row[13],
            "buyer_chain_note": row[14],
            "xianyu_confirm_status": row[15],
            "xianyu_confirm_at": row[16],
            "xianyu_confirm_error": row[17],
            "xianyu_relist_status": row[18],
            "xianyu_relist_at": row[19],
            "xianyu_relist_error": row[20],
        }
        if include_message:
            item["delivery_message"] = message
        return item

    def get_cc_shipment_by_order_id(self, order_id: str, include_message: bool = False) -> dict[str, Any] | None:
        """按闲鱼订单号读取履约记录；用于重复订单事件幂等保护。"""
        normalized_order_id = (order_id or "").strip()
        if not normalized_order_id:
            return None
        with self._conn() as c:
            row = c.execute(
                """
                SELECT id,order_id,chat_id,buyer_id,item_id,status,delivery_message,error,
                       created_at,updated_at,resolved_at,resolve_note,
                       buyer_chain_status,buyer_chain_verified_at,buyer_chain_note,
                       xianyu_confirm_status,xianyu_confirm_at,xianyu_confirm_error,
                       xianyu_relist_status,xianyu_relist_at,xianyu_relist_error
                FROM cc_shipments WHERE order_id=?
                """,
                (normalized_order_id,),
            ).fetchone()
        if not row:
            return None
        message = row[6] or ""
        item = {
            "id": row[0],
            "order_id": row[1],
            "chat_id": row[2],
            "buyer_id": row[3],
            "item_id": row[4],
            "status": row[5],
            "delivery_preview": self._mask_delivery_preview(message),
            "error": row[7],
            "created_at": row[8],
            "updated_at": row[9],
            "resolved_at": row[10],
            "resolve_note": row[11],
            "buyer_chain_status": row[12],
            "buyer_chain_verified_at": row[13],
            "buyer_chain_note": row[14],
            "xianyu_confirm_status": row[15],
            "xianyu_confirm_at": row[16],
            "xianyu_confirm_error": row[17],
            "xianyu_relist_status": row[18],
            "xianyu_relist_at": row[19],
            "xianyu_relist_error": row[20],
        }
        if include_message:
            item["delivery_message"] = message
        return item

    def claim_cc_shipment_send(
        self,
        shipment_id: int,
        expected_statuses: tuple[str, ...],
    ) -> dict[str, Any] | None:
        """原子领取指定发货记录；未命中预期状态时失败关闭。"""
        statuses = tuple(str(status or "").strip() for status in expected_statuses if str(status or "").strip())
        if not statuses:
            return None
        placeholders = ",".join("?" for _ in statuses)
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            cur = c.execute(
                f"""
                UPDATE cc_shipments
                SET status='message_send_inflight',
                    error='消息发送处理中；异常退出时必须人工核对，禁止自动重试',
                    updated_at=datetime('now')
                WHERE id=? AND status IN ({placeholders})
                """,
                (int(shipment_id), *statuses),
            )
            if cur.rowcount <= 0:
                return None
        return self.get_cc_shipment(int(shipment_id), include_message=True)

    def complete_cc_shipment_send(
        self,
        shipment_id: int,
        order_id: str,
        buyer_id: str,
        item_id: str,
        chat_id: str,
        status: str,
        error: str = "",
    ) -> bool:
        """仅允许发送执行态落为成功或结果不确定，避免并发覆盖。"""
        safe_status = str(status or "").strip()
        if safe_status not in {"message_sent", "message_send_uncertain"}:
            raise ValueError("发送完成状态只能是 message_sent 或 message_send_uncertain")
        with self._conn() as c:
            try:
                cur = c.execute(
                    """
                    UPDATE cc_shipments
                    SET order_id=?, buyer_id=?, item_id=?, chat_id=?, status=?,
                        error=?, updated_at=datetime('now')
                    WHERE id=? AND status='message_send_inflight'
                    """,
                    (
                        str(order_id or "").strip(),
                        str(buyer_id or ""),
                        str(item_id or ""),
                        str(chat_id or ""),
                        safe_status,
                        str(error or "")[:500],
                        int(shipment_id),
                    ),
                )
                return cur.rowcount > 0
            except Exception as e:
                logger.warning("完成 CC中转消息发送状态失败: %s", e)
                return False

    def claim_next_cc_browser_delivery(
        self,
        statuses: tuple[str, ...] = ("manual_delivery_ready", "message_send_failed"),
        timeout_seconds: int = 300,
    ) -> dict[str, Any] | None:
        """原子领取一条浏览器待发送话术，避免多个发送器重复发同一张卡密。"""
        safe_statuses = tuple(str(status or "").strip() for status in statuses if str(status or "").strip())
        if not safe_statuses:
            return None
        safe_timeout = max(30, min(int(timeout_seconds or 300), 3600))
        placeholders = ",".join("?" for _ in safe_statuses)
        delivery_columns = """
            id,order_id,chat_id,buyer_id,item_id,status,delivery_message,error,
            created_at,updated_at,resolved_at,resolve_note,
            buyer_chain_status,buyer_chain_verified_at,buyer_chain_note,
            xianyu_confirm_status,xianyu_confirm_at,xianyu_confirm_error,
            xianyu_relist_status,xianyu_relist_at,xianyu_relist_error
        """
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                """
                UPDATE cc_shipments
                SET status='message_send_failed',
                    error=CASE
                        WHEN COALESCE(error,'')='' THEN '浏览器发送超时，已自动退回重试队列'
                        ELSE error
                    END,
                    updated_at=datetime('now')
                WHERE status='browser_delivery_claimed'
                  AND updated_at <= datetime('now', ?)
                """,
                (f"-{safe_timeout} seconds",),
            )
            row = c.execute(
                f"""
                SELECT {delivery_columns}
                FROM cc_shipments
                WHERE status IN ({placeholders})
                  AND TRIM(COALESCE(delivery_message,'')) != ''
                ORDER BY
                  CASE status
                    WHEN 'manual_delivery_ready' THEN 0
                    WHEN 'message_send_failed' THEN 1
                    ELSE 2
                  END,
                  id DESC
                LIMIT 1
                """,
                safe_statuses,
            ).fetchone()
            if not row:
                return None
            shipment_id = int(row[0])
            cur = c.execute(
                f"""
                UPDATE cc_shipments
                SET status='browser_delivery_claimed',
                    error='',
                    updated_at=datetime('now')
                WHERE id=?
                  AND status IN ({placeholders})
                """,
                (shipment_id, *safe_statuses),
            )
            if cur.rowcount <= 0:
                return None
            row = c.execute(
                f"""
                SELECT {delivery_columns}
                FROM cc_shipments
                WHERE id=?
                """,
                (shipment_id,),
            ).fetchone()
        if not row:
            return None
        message = row[6] or ""
        item = {
            "id": row[0],
            "order_id": row[1],
            "chat_id": row[2],
            "buyer_id": row[3],
            "item_id": row[4],
            "status": row[5],
            "delivery_preview": self._mask_delivery_preview(message),
            "error": row[7],
            "created_at": row[8],
            "updated_at": row[9],
            "resolved_at": row[10],
            "resolve_note": row[11],
            "buyer_chain_status": row[12],
            "buyer_chain_verified_at": row[13],
            "buyer_chain_note": row[14],
            "xianyu_confirm_status": row[15],
            "xianyu_confirm_at": row[16],
            "xianyu_confirm_error": row[17],
            "xianyu_relist_status": row[18],
            "xianyu_relist_at": row[19],
            "xianyu_relist_error": row[20],
            "delivery_message": message,
        }
        return item

    def mark_cc_shipment_xianyu_confirm(
        self,
        order_id: str,
        status: str,
        error: str = "",
    ) -> bool:
        """记录闲鱼侧“确认发货/去发货”的结果，不改变卡密发货状态。"""
        normalized_order_id = (order_id or "").strip()
        if not normalized_order_id:
            return False
        safe_status = (status or "")[:80]
        safe_error = (error or "")[:500]
        confirmed_at = "datetime('now')" if safe_status == "confirmed" else "xianyu_confirm_at"
        with self._conn() as c:
            cur = c.execute(
                f"""
                UPDATE cc_shipments
                SET xianyu_confirm_status=?,
                    xianyu_confirm_at={confirmed_at},
                    xianyu_confirm_error=?,
                    updated_at=datetime('now')
                WHERE order_id=?
                """,
                (safe_status, safe_error, normalized_order_id),
            )
        return cur.rowcount > 0

    def mark_cc_shipment_xianyu_relist(
        self,
        order_id: str,
        status: str,
        error: str = "",
    ) -> bool:
        """记录闲鱼商品恢复上架结果，不修改发货和兑换状态。"""
        normalized_order_id = (order_id or "").strip()
        if not normalized_order_id:
            return False
        safe_status = (status or "")[:80]
        safe_error = (error or "")[:500]
        relisted_at = "datetime('now')" if safe_status == "relisted" else "xianyu_relist_at"
        with self._conn() as c:
            cur = c.execute(
                f"""
                UPDATE cc_shipments
                SET xianyu_relist_status=?,
                    xianyu_relist_at={relisted_at},
                    xianyu_relist_error=?,
                    updated_at=datetime('now')
                WHERE order_id=?
                """,
                (safe_status, safe_error, normalized_order_id),
            )
        return cur.rowcount > 0

    def update_cc_shipment_delivery_state(
        self,
        shipment_id: int,
        order_id: str,
        buyer_id: str,
        item_id: str,
        chat_id: str,
        status: str,
        error: str = "",
    ) -> bool:
        """把已分配待发送记录绑定到真实订单并更新状态。"""
        safe_error = (error or "")[:500]
        with self._conn() as c:
            try:
                cur = c.execute(
                    """
                    UPDATE cc_shipments
                    SET order_id=?, buyer_id=?, item_id=?, chat_id=?, status=?,
                        error=?, updated_at=datetime('now')
                    WHERE id=?
                    """,
                    (
                        (order_id or "").strip(),
                        buyer_id or "",
                        item_id or "",
                        chat_id or "",
                        status or "",
                        safe_error,
                        int(shipment_id),
                    ),
                )
                return cur.rowcount > 0
            except Exception as e:
                logger.warning("更新 CC中转履约记录状态失败: %s", e)
                return False

    def adopt_cc_shipment_real_order(
        self,
        old_order_id: str,
        new_order_id: str,
        buyer_id: str = "",
        item_id: str = "",
        chat_id: str = "",
    ) -> bool:
        """把已发卡的浏览器临时订单接管为真实闲鱼订单哈希。"""
        safe_old = (old_order_id or "").strip()
        safe_new = (new_order_id or "").strip()
        if not safe_old or not safe_new or safe_old == safe_new:
            return False
        with self._conn() as c:
            try:
                cur = c.execute(
                    """
                    UPDATE cc_shipments
                    SET order_id=?,
                        buyer_id=CASE WHEN ?<>'' THEN ? ELSE buyer_id END,
                        item_id=CASE WHEN ?<>'' THEN ? ELSE item_id END,
                        chat_id=CASE WHEN ?<>'' THEN ? ELSE chat_id END,
                        updated_at=datetime('now')
                    WHERE order_id=?
                      AND status='message_sent'
                    """,
                    (
                        safe_new,
                        buyer_id or "",
                        buyer_id or "",
                        item_id or "",
                        item_id or "",
                        chat_id or "",
                        chat_id or "",
                        safe_old,
                    ),
                )
                return cur.rowcount > 0
            except Exception as e:
                logger.warning("接管 CC中转真实订单号失败: %s", e)
                return False

    def mark_cc_shipment_send_failed(self, shipment_id: int, error: str = "") -> bool:
        """浏览器领取话术后未能发送时，退回失败队列供后续人工或自动重试。"""
        safe_error = (error or "浏览器助手未能发送发货话术")[:500]
        with self._conn() as c:
            cur = c.execute(
                """
                UPDATE cc_shipments
                SET status='message_send_failed',
                    error=?,
                    updated_at=datetime('now')
                WHERE id=?
                  AND status IN ('browser_delivery_claimed','manual_delivery_ready','message_send_failed')
                """,
                (safe_error, int(shipment_id)),
            )
        return cur.rowcount > 0

    def cc_shipment_summary(self) -> dict[str, Any]:
        """汇总 CC中转自动发货状态，用于老板首页看板。"""
        failure_statuses = {
            "browser_delivery_claimed",
            "webhook_inflight",
            "message_send_inflight",
            "message_send_uncertain",
            "message_send_failed",
            "webhook_failed",
            "missing_delivery_message",
            "exception",
            "manual_delivery_ready",
        }
        with self._conn() as c:
            rows = c.execute("SELECT status, COUNT(*) FROM cc_shipments GROUP BY status").fetchall()
            verified = c.execute("SELECT COUNT(*) FROM cc_shipments WHERE buyer_chain_status='verified'").fetchone()[0]
            xianyu_confirmed = c.execute(
                "SELECT COUNT(*) FROM cc_shipments WHERE xianyu_confirm_status='confirmed'"
            ).fetchone()[0]
            xianyu_confirm_failed = c.execute(
                "SELECT COUNT(*) FROM cc_shipments WHERE xianyu_confirm_status='failed'"
            ).fetchone()[0]
            xianyu_confirm_pending = c.execute(
                """
                SELECT COUNT(*) FROM cc_shipments
                WHERE status='message_sent'
                  AND COALESCE(xianyu_confirm_status,'') NOT IN ('confirmed','skipped')
                """
            ).fetchone()[0]
            xianyu_confirm_page_pending = c.execute(
                """
                SELECT COUNT(*) FROM cc_shipments
                WHERE status='message_sent'
                  AND (order_id LIKE 'xy_manual_%' OR order_id LIKE 'xy_browser_%')
                  AND COALESCE(xianyu_confirm_status,'') NOT IN ('confirmed','skipped')
                """
            ).fetchone()[0]
        by_status = {str(row[0]): int(row[1]) for row in rows}
        pending_rescue = sum(by_status.get(status, 0) for status in failure_statuses)
        return {
            "total": sum(by_status.values()),
            "sent": by_status.get("message_sent", 0),
            "browser_delivery_claimed": by_status.get("browser_delivery_claimed", 0),
            "message_send_inflight": by_status.get("message_send_inflight", 0),
            "message_send_uncertain": by_status.get("message_send_uncertain", 0),
            "message_send_failed": by_status.get("message_send_failed", 0),
            "pending_rescue": pending_rescue,
            "resolved": by_status.get("manually_resolved", 0),
            "buyer_chain_verified": int(verified or 0),
            "xianyu_confirm_pending": int(xianyu_confirm_pending or 0),
            "xianyu_confirm_page_pending": int(xianyu_confirm_page_pending or 0),
            "xianyu_confirmed": int(xianyu_confirmed or 0),
            "xianyu_confirm_failed": int(xianyu_confirm_failed or 0),
            "by_status": by_status,
            "latest": self.list_cc_shipments(limit=5, include_message=False),
        }

    def cc_final_sale_gate_summary(self) -> dict[str, Any]:
        """汇总正式售卖前真实闲鱼实单验收门，不泄露卡密和买家完整信息。"""
        failure_statuses = (
            "browser_delivery_claimed",
            "webhook_inflight",
            "message_send_inflight",
            "message_send_uncertain",
            "message_send_failed",
            "webhook_failed",
            "missing_delivery_message",
            "exception",
            "manual_delivery_ready",
        )
        with self._conn() as c:
            sent_real_orders = c.execute(
                "SELECT COUNT(*) FROM cc_shipments WHERE status='message_sent' AND order_id LIKE 'xy_oid_%'"
            ).fetchone()[0]
            buyer_chain_verified = c.execute(
                "SELECT COUNT(*) FROM cc_shipments WHERE buyer_chain_status='verified' AND order_id LIKE 'xy_oid_%'"
            ).fetchone()[0]
            pending_rescue = c.execute(
                f"SELECT COUNT(*) FROM cc_shipments WHERE status IN ({','.join('?' for _ in failure_statuses)})",
                failure_statuses,
            ).fetchone()[0]
            latest = c.execute(
                """
                SELECT id, order_id, status, created_at, updated_at
                FROM cc_shipments
                ORDER BY id DESC
                LIMIT 5
                """
            ).fetchall()
        local_ready = int(sent_real_orders or 0) > 0 and int(pending_rescue or 0) == 0
        return {
            "local_ready": local_ready,
            "sent_real_orders": int(sent_real_orders or 0),
            "buyer_chain_verified_orders": int(buyer_chain_verified or 0),
            "pending_rescue": int(pending_rescue or 0),
            "strict_audit_command": "node scripts/cc_zhongzhuan_readiness_audit.mjs --require-real-order",
            "buyer_chain_required": {
                "same_xy_order_redeemed": True,
                "redeemed_redemptions_delta_gt_0": True,
                "active_api_tokens_delta_gt_0": True,
                "model_call_logs_delta_gt_0": True,
            },
            "latest": [
                {
                    "id": row[0],
                    "order_id_prefix": str(row[1] or "")[:10],
                    "status": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                }
                for row in latest
            ],
        }

    def mark_cc_shipments_buyer_chain_verified(self, matches: list[dict[str, Any]]) -> int:
        """按订单哈希把已完成兑换/API/调模型的闲鱼发货记录标记为闭环完成。"""
        wanted_hashes = {
            str(item.get("orderIdHash") or "").strip()
            for item in matches
            if isinstance(item, dict) and item.get("ready") and item.get("orderIdHash")
        }
        wanted_hashes.discard("")
        if not wanted_hashes:
            return 0

        with self._conn() as c:
            rows = c.execute("SELECT id, order_id FROM cc_shipments WHERE order_id LIKE 'xy_oid_%'").fetchall()
            matched_ids = [
                int(row[0]) for row in rows if hashlib.sha256(str(row[1] or "").encode()).hexdigest() in wanted_hashes
            ]
            if not matched_ids:
                return 0
            placeholders = ",".join("?" for _ in matched_ids)
            cur = c.execute(
                f"""
                UPDATE cc_shipments
                SET buyer_chain_status='verified',
                    buyer_chain_verified_at=datetime('now'),
                    buyer_chain_note='strict_audit_ready',
                    updated_at=datetime('now')
                WHERE id IN ({placeholders})
                """,
                matched_ids,
            )
        return int(cur.rowcount or 0)

    def record_cc_strict_audit(self, audit: dict[str, Any]) -> dict[str, Any]:
        """持久化最近一次严格门审计摘要；不保存 stdout、stderr、token、卡密或 API Key。"""
        summary = audit.get("summary") if isinstance(audit, dict) else {}
        if not isinstance(summary, dict):
            summary = {}
        safe_summary = {
            "same_order_ready": int(summary.get("same_order_ready") or 0),
            "same_order_matched": int(summary.get("same_order_matched") or 0),
            "real_orders": int(summary.get("real_orders") or 0),
            "redeemed_delta": int(summary.get("redeemed_delta") or 0),
            "active_token_delta": int(summary.get("active_token_delta") or 0),
            "model_log_delta": int(summary.get("model_log_delta") or 0),
            "same_order_latest": summary.get("same_order_latest") or [],
        }
        with self._conn() as c:
            cur = c.execute(
                """
                INSERT INTO cc_strict_audits(
                    mode, ok, exit_code, same_order_ready,
                    same_order_matched, real_orders, summary_json
                )
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    str(audit.get("mode") or "strict")[:20],
                    1 if audit.get("ok") else 0,
                    int(audit.get("exit_code") or 0),
                    safe_summary["same_order_ready"],
                    safe_summary["same_order_matched"],
                    safe_summary["real_orders"],
                    json.dumps(safe_summary, ensure_ascii=False),
                ),
            )
            audit_id = cur.lastrowid
        verified_count = self.mark_cc_shipments_buyer_chain_verified(safe_summary.get("same_order_latest") or [])
        latest = self.latest_cc_strict_audit() or {}
        latest["id"] = audit_id
        latest["marked_buyer_chain_verified"] = verified_count
        return latest

    def latest_cc_strict_audit(self) -> dict[str, Any] | None:
        """读取最近一次严格门审计摘要，用于 GUI/后台恢复状态。"""
        with self._conn() as c:
            row = c.execute(
                """
                SELECT id,mode,ok,exit_code,same_order_ready,
                       same_order_matched,real_orders,summary_json,created_at
                FROM cc_strict_audits
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        try:
            summary = json.loads(row[7] or "{}")
        except Exception as e:
            logger.debug("读取严格门摘要 JSON 失败: %s", e)
            summary = {}
        return {
            "id": row[0],
            "mode": row[1],
            "ok": bool(row[2]),
            "exit_code": row[3],
            "same_order_ready": int(row[4] or 0),
            "same_order_matched": int(row[5] or 0),
            "real_orders": int(row[6] or 0),
            "summary": summary,
            "updated_at": row[8],
            "source": "sqlite",
        }

    def resolve_cc_shipment(self, shipment_id: int, note: str = "") -> bool:
        """人工确认补发/处理完成，返回是否命中记录。"""
        with self._conn() as c:
            cur = c.execute(
                """
                UPDATE cc_shipments
                SET status='manually_resolved',
                    resolved_at=datetime('now'),
                    resolve_note=?,
                    updated_at=datetime('now')
                WHERE id=?
                """,
                ((note or "")[:500], shipment_id),
            )
        return cur.rowcount > 0

    # ---- consultations ----
    def track_consultation(self, chat_id: str, user_id: str, user_name: str, item_id: str, message: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO consultations(chat_id,user_id,user_name,item_id,first_msg) VALUES(?,?,?,?,?) "
                "ON CONFLICT(chat_id,item_id) DO UPDATE SET msg_count=msg_count+1, last_ts=datetime('now')",
                (chat_id, user_id, user_name, item_id, message[:200]),
            )

    def mark_converted(self, chat_id: str, item_id: str = ""):
        with self._conn() as c:
            if item_id:
                c.execute("UPDATE consultations SET converted=1 WHERE chat_id=? AND item_id=?", (chat_id, item_id))
            else:
                c.execute("UPDATE consultations SET converted=1 WHERE chat_id=?", (chat_id,))

    def get_latest_chat_id(self, user_id: str) -> str | None:
        """根据用户ID获取最近一次咨询的 chat_id"""
        with self._conn() as c:
            row = c.execute(
                "SELECT chat_id FROM consultations WHERE user_id=? ORDER BY last_ts DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            return row[0] if row else None

    # ---- floor prices (底价) ----
    def set_floor_price(self, item_id: str, floor_price: float):
        """设置商品底价"""
        with self._conn() as c:
            c.execute(
                "INSERT INTO floor_prices(item_id,floor_price) VALUES(?,?) "
                "ON CONFLICT(item_id) DO UPDATE SET floor_price=?, updated=datetime('now')",
                (item_id, floor_price, floor_price),
            )

    def get_floor_price(self, item_id: str) -> float | None:
        """获取商品底价，未设置返回 None"""
        with self._conn() as c:
            row = c.execute("SELECT floor_price FROM floor_prices WHERE item_id=?", (item_id,)).fetchone()
        return row[0] if row else None

    def remove_floor_price(self, item_id: str) -> bool:
        """移除商品底价，返回是否有记录被删除"""
        with self._conn() as c:
            cur = c.execute("DELETE FROM floor_prices WHERE item_id=?", (item_id,))
        return cur.rowcount > 0

    def list_floor_prices(self) -> list[dict]:
        """列出所有已设底价的商品"""
        with self._conn() as c:
            rows = c.execute("SELECT item_id, floor_price, updated FROM floor_prices ORDER BY updated DESC").fetchall()
        return [{"item_id": r[0], "floor_price": r[1], "updated": r[2]} for r in rows]

    def get_recent_item_id(self, user_id: str) -> str | None:
        """获取该用户最近一次会话的商品ID"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT item_id FROM messages WHERE user_id=? AND item_id IS NOT NULL AND item_id != '' ORDER BY ts DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return row[0] if row else None

    def daily_stats(self, date: str = "") -> dict[str, Any]:
        """获取某天的统计数据，默认今天"""
        if not date:
            date = now_et().strftime("%Y-%m-%d")
        with self._conn() as c:
            # 咨询数
            consult_total = c.execute(
                "SELECT COUNT(DISTINCT chat_id) FROM consultations WHERE first_ts LIKE ?", (f"{date}%",)
            ).fetchone()[0]
            # 下单数
            order_total = c.execute("SELECT COUNT(*) FROM orders WHERE ts LIKE ?", (f"{date}%",)).fetchone()[0]
            # 付款数
            paid_total = c.execute(
                "SELECT COUNT(*) FROM orders WHERE ts LIKE ? AND status LIKE '%付款%'", (f"{date}%",)
            ).fetchone()[0]
            # 消息总数
            msg_total = c.execute(
                "SELECT COUNT(*) FROM messages WHERE ts LIKE ? AND role='user'", (f"{date}%",)
            ).fetchone()[0]
            # 转化数
            converted = c.execute(
                "SELECT COUNT(*) FROM consultations WHERE first_ts LIKE ? AND converted=1", (f"{date}%",)
            ).fetchone()[0]
        rate = f"{converted / consult_total * 100:.1f}%" if consult_total > 0 else "0%"
        return {
            "date": date,
            "consultations": consult_total,
            "messages": msg_total,
            "orders": order_total,
            "paid": paid_total,
            "converted": converted,
            "conversion_rate": rate,
        }

    # ---- 发货超时提醒 ----
    def get_pending_shipments(self, hours_threshold: int = 4) -> list:
        """查询超过指定小时未发货的订单"""
        # 使用 now_et() 统一时区基准，与 daily_stats 保持一致
        cutoff = (now_et() - timedelta(hours=hours_threshold)).strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, chat_id, item_id, status, ts FROM orders WHERE status='paid' AND ts < ? AND notified < ?",
                (cutoff, NOTIFY_SHIPMENT),
            ).fetchall()
        return [{"id": r[0], "chat_id": r[1], "item_id": r[2], "status": r[3], "ts": r[4]} for r in rows]

    def mark_shipment_reminded(self, order_id: int):
        """标记订单已发送发货提醒"""
        with self._conn() as c:
            c.execute("UPDATE orders SET notified = ? WHERE id = ?", (NOTIFY_SHIPMENT, order_id))

    # ---- 利润核算 ----
    def get_profit_summary(self, days: int = 30) -> dict:
        """获取近N天的利润汇总（扣除平台佣金）"""
        with self._conn() as c:
            rows = c.execute(
                "SELECT amount, cost, COALESCE(commission_rate, 0.06) FROM orders "
                "WHERE status IN ('paid','completed') AND ts > datetime('now', '-' || ? || ' days')",
                (days,),
            ).fetchall()
        total_orders = len(rows)
        total_revenue = 0.0
        total_cost = 0.0
        total_commission = 0.0
        total_profit = 0.0
        for amount, cost, commission_rate in rows:
            amount = amount or 0
            cost = cost or 0
            commission_rate = commission_rate if commission_rate is not None else 0.06
            commission = amount * commission_rate
            total_revenue += amount
            total_cost += cost
            total_commission += commission
            total_profit += amount * (1 - commission_rate) - cost
        return {
            "orders": total_orders,
            "revenue": round(total_revenue, 2),
            "cost": round(total_cost, 2),
            "total_commission": round(total_commission, 2),
            "profit": round(total_profit, 2),
            "days": days,
        }

    def get_all_orders(self, days: int = 30) -> list:
        """获取所有订单明细 — 用于 Excel 导出

        Returns:
            list[dict]: 每条订单包含 date, item_name, buyer, status, amount, cost, commission_rate
        """
        try:
            with self._conn() as c:
                rows = c.execute(
                    "SELECT o.ts, o.item_id, o.user_id, o.status, "
                    "o.amount, o.cost, COALESCE(o.commission_rate, 0.06), "
                    "COALESCE(i.data, '{}') "
                    "FROM orders o "
                    "LEFT JOIN items i ON o.item_id = i.item_id "
                    "WHERE o.ts > datetime('now', '-' || ? || ' days') "
                    "ORDER BY o.ts DESC",
                    (days,),
                ).fetchall()
            result = []
            for r in rows:
                # 从 items 表的 JSON 提取商品标题
                try:
                    item_name = json.loads(r[7]).get("title", r[1] or "")
                except Exception as e:  # noqa: F841
                    item_name = r[1] or ""
                result.append(
                    {
                        "date": r[0] or "",
                        "item_name": item_name,
                        "buyer": r[2] or "",
                        "status": r[3] or "",
                        "amount": r[4] or 0,
                        "cost": r[5] or 0,
                        "commission_rate": r[6] if r[6] is not None else 0.06,
                    }
                )
            return result
        except Exception as e:
            logger.error("[XianyuContext] 获取全部订单失败: %s", e)
            return []

    # ---- 运营智能查询 ----

    def get_item_rankings(self, days: int = 7, limit: int = 10) -> list:
        """商品热度排行: 按咨询次数排序，返回 item_id / 咨询数 / 转化数 / 转化率"""
        try:
            with self._conn() as c:
                rows = c.execute(
                    """
                    SELECT
                        c.item_id,
                        COALESCE(i.data, '{}')                      AS item_data,
                        COUNT(*)                                     AS consult_count,
                        SUM(CASE WHEN c.converted = 1 THEN 1 ELSE 0 END) AS convert_count
                    FROM consultations c
                    LEFT JOIN items i ON c.item_id = i.item_id
                    WHERE c.first_ts > datetime('now', '-' || ? || ' days')
                      AND c.item_id IS NOT NULL AND c.item_id != ''
                    GROUP BY c.item_id
                    ORDER BY consult_count DESC
                    LIMIT ?
                    """,
                    (days, limit),
                ).fetchall()
            result = []
            for item_id, item_data_str, consult, converted in rows:
                # 从 items 表的 JSON 中提取商品标题
                try:
                    title = json.loads(item_data_str).get("title", "")
                except Exception as e:  # noqa: F841
                    title = ""
                rate = round(converted / consult * 100, 1) if consult > 0 else 0.0
                result.append(
                    {
                        "item_id": item_id,
                        "title": title,
                        "consultations": consult,
                        "conversions": converted,
                        "conversion_rate": f"{rate}%",
                    }
                )
            return result
        except Exception as e:
            logger.debug("get_item_rankings 异常: %s", e)
            return []

    def get_peak_hours(self, days: int = 7) -> list:
        """咨询时段分布: 按小时聚合消息数，返回 24 个时段的消息量"""
        try:
            with self._conn() as c:
                rows = c.execute(
                    """
                    SELECT
                        strftime('%%H', ts)  AS hour,
                        COUNT(*)             AS msg_count
                    FROM messages
                    WHERE role = 'user'
                      AND ts > datetime('now', '-' || ? || ' days')
                    GROUP BY hour
                    ORDER BY hour ASC
                    """,
                    (days,),
                ).fetchall()
            # 补全 24 小时（没有消息的时段填 0）
            hour_map = {r[0]: r[1] for r in rows}
            result = []
            for h in range(24):
                hk = f"{h:02d}"
                result.append({"hour": hk, "messages": hour_map.get(hk, 0)})
            return result
        except Exception as e:
            logger.debug("get_peak_hours 异常: %s", e)
            return []

    # ---- 回复配置 (风格/FAQ/商品规则) ----

    _FAQ_LIMIT = 50  # FAQ 最多 50 条
    _ITEM_RULE_LIMIT = 100  # 商品规则最多 100 条

    def set_reply_style(self, tone: str):
        """设置全局回复风格 — 如'热情活泼'/'专业简洁'/'可爱卖萌'"""
        with self._conn() as c:
            c.execute(
                "INSERT INTO reply_config(config_type,key,value) VALUES('style','tone',?) "
                "ON CONFLICT(config_type,key) DO UPDATE SET value=?",
                (tone, tone),
            )

    def add_faq(self, question_keyword: str, answer: str) -> bool:
        """添加常见问题 — 当买家消息包含关键词时优先使用模板回复

        返回 True 表示成功, False 表示已达上限。
        """
        with self._conn() as c:
            count = c.execute("SELECT COUNT(*) FROM reply_config WHERE config_type='faq'").fetchone()[0]
            if count >= self._FAQ_LIMIT:
                return False
            c.execute(
                "INSERT INTO reply_config(config_type,key,value) VALUES('faq',?,?) "
                "ON CONFLICT(config_type,key) DO UPDATE SET value=?",
                (question_keyword, answer, answer),
            )
        return True

    def get_faqs(self) -> list[dict[str, str]]:
        """获取所有FAQ"""
        with self._conn() as c:
            rows = c.execute(
                "SELECT key, value FROM reply_config WHERE config_type='faq' ORDER BY priority DESC, id ASC"
            ).fetchall()
        return [{"key": r[0], "value": r[1]} for r in rows]

    def remove_faq(self, keyword: str) -> bool:
        """删除FAQ，返回是否有记录被删除"""
        with self._conn() as c:
            cur = c.execute(
                "DELETE FROM reply_config WHERE config_type='faq' AND key=?",
                (keyword,),
            )
        return cur.rowcount > 0

    def set_item_rule(self, item_id: str, rule: str) -> bool:
        """设置商品个性化规则 — 如'这个商品强调正版授权'

        返回 True 表示成功, False 表示已达上限。
        """
        with self._conn() as c:
            count = c.execute("SELECT COUNT(*) FROM reply_config WHERE config_type='item_rule'").fetchone()[0]
            # 允许更新已有规则，不计入上限
            existing = c.execute(
                "SELECT 1 FROM reply_config WHERE config_type='item_rule' AND key=?",
                (item_id,),
            ).fetchone()
            if not existing and count >= self._ITEM_RULE_LIMIT:
                return False
            c.execute(
                "INSERT INTO reply_config(config_type,key,value) VALUES('item_rule',?,?) "
                "ON CONFLICT(config_type,key) DO UPDATE SET value=?",
                (item_id, rule, rule),
            )
        return True

    def remove_item_rule(self, item_id: str) -> bool:
        """删除商品规则"""
        with self._conn() as c:
            cur = c.execute(
                "DELETE FROM reply_config WHERE config_type='item_rule' AND key=?",
                (item_id,),
            )
        return cur.rowcount > 0

    def get_reply_config(self) -> dict:
        """获取完整回复配置 — 风格+FAQ+商品规则

        返回格式:
        {
            "style": "热情活泼" | None,
            "faqs": [{"key": "发货", "value": "..."}],
            "item_rules": {"item_id_1": "规则内容"}
        }
        """
        with self._conn() as c:
            rows = c.execute(
                "SELECT config_type, key, value FROM reply_config ORDER BY priority DESC, id ASC"
            ).fetchall()
        style = None
        faqs: list[dict[str, str]] = []
        item_rules: dict[str, str] = {}
        for config_type, key, value in rows:
            if config_type == "style" and key == "tone":
                style = value
            elif config_type == "faq":
                faqs.append({"key": key, "value": value})
            elif config_type == "item_rule":
                item_rules[key] = value
        return {"style": style, "faqs": faqs, "item_rules": item_rules}

    # ---- 买家画像 ----
    def get_buyer_profile(self, user_id: str) -> dict:
        """构建买家画像 — 从历史咨询/订单/议价数据中生成买家特征

        返回包含以下字段的字典:
        - total_consultations: 总咨询次数
        - total_orders: 总成交次数
        - items_consulted: 咨询过的不同商品数
        - bargain_tendency: 砍价倾向 ("低"/"中"/"高"/"未知")
        - last_contact_days: 距上次联系天数
        - avg_msg_count: 平均每次对话消息数
        - is_repeat_buyer: 是否回头客
        - total_spent: 历史总消费金额
        """
        # 新买家默认画像 — 全部归零
        empty_profile = {
            "total_consultations": 0,
            "total_orders": 0,
            "items_consulted": 0,
            "bargain_tendency": "未知",
            "last_contact_days": -1,
            "avg_msg_count": 0.0,
            "is_repeat_buyer": False,
            "total_spent": 0.0,
        }

        # 1) 咨询统计 — 总次数、不同商品数、平均消息数、最近联系时间
        try:
            with self._conn() as c:
                consult_rows = c.execute(
                    "SELECT COUNT(*), COUNT(DISTINCT item_id), "
                    "AVG(msg_count), MAX(last_ts) "
                    "FROM consultations WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
        except Exception as e:
            logger.debug("get_buyer_profile 查询咨询数据异常: %s", e)
            consult_rows = None

        if not consult_rows or consult_rows[0] == 0:
            return empty_profile

        total_consultations = consult_rows[0] or 0
        items_consulted = consult_rows[1] or 0
        avg_msg_count = round(consult_rows[2] or 0.0, 1)
        last_ts_str = consult_rows[3]

        # 计算距上次联系天数
        last_contact_days = -1
        if last_ts_str:
            try:
                from datetime import datetime

                last_ts = datetime.strptime(last_ts_str, "%Y-%m-%d %H:%M:%S")
                delta = now_et().replace(tzinfo=None) - last_ts
                last_contact_days = max(delta.days, 0)
            except Exception as e:
                logger.debug("get_buyer_profile 解析 last_ts 异常: %s", e)

        # 2) 订单统计 — 成交次数、累计消费金额
        total_orders = 0
        total_spent = 0.0
        try:
            with self._conn() as c:
                order_row = c.execute(
                    "SELECT COUNT(*), COALESCE(SUM(amount), 0) "
                    "FROM orders WHERE user_id = ? AND status IN ('paid', 'shipped', 'completed', '交易成功')",
                    (user_id,),
                ).fetchone()
            if order_row:
                total_orders = order_row[0] or 0
                total_spent = round(order_row[1] or 0.0, 2)
        except Exception as e:
            logger.debug("get_buyer_profile 查询订单数据异常: %s", e)

        # 3) 砍价倾向 — 从 bargain_counts 表获取该用户所有对话的平均砍价次数
        bargain_tendency = "未知"
        try:
            with self._conn() as c:
                bargain_row = c.execute(
                    "SELECT AVG(b.count) FROM bargain_counts b "
                    "INNER JOIN consultations cs ON b.chat_id = cs.chat_id "
                    "WHERE cs.user_id = ?",
                    (user_id,),
                ).fetchone()
            if bargain_row and bargain_row[0] is not None:
                avg_bargain = bargain_row[0]
                if avg_bargain < 2:
                    bargain_tendency = "低"
                elif avg_bargain < 4:
                    bargain_tendency = "中"
                else:
                    bargain_tendency = "高"
        except Exception as e:
            logger.debug("get_buyer_profile 查询砍价数据异常: %s", e)

        # 4) 是否回头客 — 有过成交且咨询次数超过 1
        is_repeat_buyer = total_orders > 0 and total_consultations > 1

        return {
            "total_consultations": total_consultations,
            "total_orders": total_orders,
            "items_consulted": items_consulted,
            "bargain_tendency": bargain_tendency,
            "last_contact_days": last_contact_days,
            "avg_msg_count": avg_msg_count,
            "is_repeat_buyer": is_repeat_buyer,
            "total_spent": total_spent,
        }

    def get_conversion_funnel(self, days: int = 7) -> dict:
        """转化漏斗: 总咨询 → 有回复 → 成交 → 发货，各阶段数量和转化率"""
        try:
            with self._conn() as c:
                # 1) 总咨询量（去重 chat_id）
                total = c.execute(
                    "SELECT COUNT(DISTINCT chat_id) FROM consultations "
                    "WHERE first_ts > datetime('now', '-' || ? || ' days')",
                    (days,),
                ).fetchone()[0]

                # 2) 有回复的咨询（该 chat_id 下有 assistant 消息）
                replied = c.execute(
                    """
                    SELECT COUNT(DISTINCT c.chat_id)
                    FROM consultations c
                    INNER JOIN messages m ON c.chat_id = m.chat_id AND m.role = 'assistant'
                    WHERE c.first_ts > datetime('now', '-' || ? || ' days')
                    """,
                    (days,),
                ).fetchone()[0]

                # 3) 已成交（converted = 1）
                converted = c.execute(
                    "SELECT COUNT(DISTINCT chat_id) FROM consultations "
                    "WHERE first_ts > datetime('now', '-' || ? || ' days') AND converted = 1",
                    (days,),
                ).fetchone()[0]

                # 4) 已发货 / 交易完成
                shipped = c.execute(
                    "SELECT COUNT(DISTINCT chat_id) FROM orders "
                    "WHERE ts > datetime('now', '-' || ? || ' days') "
                    "AND status IN ('completed', '交易成功')",
                    (days,),
                ).fetchone()[0]

            # 计算各阶段转化率（相对上一阶段）
            def _rate(num: int, denom: int) -> str:
                return f"{round(num / denom * 100, 1)}%" if denom > 0 else "0%"

            return {
                "days": days,
                "total_consultations": total,
                "replied": replied,
                "replied_rate": _rate(replied, total),
                "converted": converted,
                "converted_rate": _rate(converted, replied),
                "shipped": shipped,
                "shipped_rate": _rate(shipped, converted),
                "overall_rate": _rate(converted, total),
            }
        except Exception as e:
            logger.debug("get_conversion_funnel 异常: %s", e)
            return {}
