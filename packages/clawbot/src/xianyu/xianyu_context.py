"""闲鱼对话上下文管理 — SQLite 持久化"""
import json
import os
import sqlite3
import logging
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, Dict, List, Optional
from src.utils import now_et

logger = logging.getLogger(__name__)

# 订单通知状态
NOTIFY_NONE = 0       # 未通知
NOTIFY_ORDER = 1      # 已发下单通知
NOTIFY_SHIPMENT = 2   # 已发发货提醒

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
        """获取 SQLite 连接 (上下文管理器自动关闭)"""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

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
            except Exception:
                pass  # 字段已存在
            try:
                c.execute("ALTER TABLE orders ADD COLUMN cost REAL DEFAULT 0")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE orders ADD COLUMN commission_rate REAL DEFAULT 0.06")
            except Exception:
                pass  # 字段已存在
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

    def get_context(self, chat_id: str) -> List[Dict[str, str]]:
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

    def get_item(self, item_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT data FROM items WHERE item_id=?", (item_id,)).fetchone()
        return json.loads(row[0]) if row else None

    # ---- orders ----
    def record_order(self, chat_id: str, user_id: str, item_id: str, status: str,
                     amount: float = 0.0, cost: float = 0.0):
        with self._conn() as c:
            c.execute(
                "INSERT INTO orders(chat_id,user_id,item_id,status,amount,cost) VALUES(?,?,?,?,?,?)",
                (chat_id, user_id, item_id, status, amount, cost),
            )

    def get_unnotified_orders(self) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id,chat_id,user_id,item_id,status,ts FROM orders WHERE notified=?"\
            , (NOTIFY_NONE,)).fetchall()
        return [{"id": r[0], "chat_id": r[1], "user_id": r[2], "item_id": r[3], "status": r[4], "ts": r[5]} for r in rows]

    def mark_notified(self, order_id: int):
        with self._conn() as c:
            c.execute("UPDATE orders SET notified=? WHERE id=?", (NOTIFY_ORDER, order_id))

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

    # ---- floor prices (底价) ----
    def set_floor_price(self, item_id: str, floor_price: float):
        """设置商品底价"""
        with self._conn() as c:
            c.execute(
                "INSERT INTO floor_prices(item_id,floor_price) VALUES(?,?) "
                "ON CONFLICT(item_id) DO UPDATE SET floor_price=?, updated=datetime('now')",
                (item_id, floor_price, floor_price),
            )

    def get_floor_price(self, item_id: str) -> Optional[float]:
        """获取商品底价，未设置返回 None"""
        with self._conn() as c:
            row = c.execute("SELECT floor_price FROM floor_prices WHERE item_id=?", (item_id,)).fetchone()
        return row[0] if row else None

    def remove_floor_price(self, item_id: str) -> bool:
        """移除商品底价，返回是否有记录被删除"""
        with self._conn() as c:
            cur = c.execute("DELETE FROM floor_prices WHERE item_id=?", (item_id,))
        return cur.rowcount > 0

    def list_floor_prices(self) -> List[Dict]:
        """列出所有已设底价的商品"""
        with self._conn() as c:
            rows = c.execute("SELECT item_id, floor_price, updated FROM floor_prices ORDER BY updated DESC").fetchall()
        return [{"item_id": r[0], "floor_price": r[1], "updated": r[2]} for r in rows]

    def get_recent_item_id(self, user_id: str) -> Optional[str]:
        """获取该用户最近一次会话的商品ID"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT item_id FROM messages WHERE user_id=? AND item_id IS NOT NULL AND item_id != '' ORDER BY ts DESC LIMIT 1",
                (user_id,)
            ).fetchone()
        return row[0] if row else None

    def daily_stats(self, date: str = "") -> Dict[str, Any]:
        """获取某天的统计数据，默认今天"""
        if not date:
            date = now_et().strftime("%Y-%m-%d")
        with self._conn() as c:
            # 咨询数
            consult_total = c.execute(
                "SELECT COUNT(DISTINCT chat_id) FROM consultations WHERE first_ts LIKE ?", (f"{date}%",)
            ).fetchone()[0]
            # 下单数
            order_total = c.execute(
                "SELECT COUNT(*) FROM orders WHERE ts LIKE ?", (f"{date}%",)
            ).fetchone()[0]
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
        rate = f"{converted/consult_total*100:.1f}%" if consult_total > 0 else "0%"
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
                "SELECT id, chat_id, item_id, status, ts FROM orders "
                "WHERE status='paid' AND ts < ? AND notified < ?",
                (cutoff, NOTIFY_SHIPMENT)
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
                (days,)
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
                except Exception:
                    item_name = r[1] or ""
                result.append({
                    "date": r[0] or "",
                    "item_name": item_name,
                    "buyer": r[2] or "",
                    "status": r[3] or "",
                    "amount": r[4] or 0,
                    "cost": r[5] or 0,
                    "commission_rate": r[6] if r[6] is not None else 0.06,
                })
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
                except Exception:
                    title = ""
                rate = round(converted / consult * 100, 1) if consult > 0 else 0.0
                result.append({
                    "item_id": item_id,
                    "title": title,
                    "consultations": consult,
                    "conversions": converted,
                    "conversion_rate": f"{rate}%",
                })
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

    _FAQ_LIMIT = 50       # FAQ 最多 50 条
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
            count = c.execute(
                "SELECT COUNT(*) FROM reply_config WHERE config_type='faq'"
            ).fetchone()[0]
            if count >= self._FAQ_LIMIT:
                return False
            c.execute(
                "INSERT INTO reply_config(config_type,key,value) VALUES('faq',?,?) "
                "ON CONFLICT(config_type,key) DO UPDATE SET value=?",
                (question_keyword, answer, answer),
            )
        return True

    def get_faqs(self) -> List[Dict[str, str]]:
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
            count = c.execute(
                "SELECT COUNT(*) FROM reply_config WHERE config_type='item_rule'"
            ).fetchone()[0]
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
        faqs: List[Dict[str, str]] = []
        item_rules: Dict[str, str] = {}
        for config_type, key, value in rows:
            if config_type == "style" and key == "tone":
                style = value
            elif config_type == "faq":
                faqs.append({"key": key, "value": value})
            elif config_type == "item_rule":
                item_rules[key] = value
        return {"style": style, "faqs": faqs, "item_rules": item_rules}

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
