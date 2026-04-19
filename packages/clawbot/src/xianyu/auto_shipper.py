"""
闲鱼自动发货引擎 v1.0
搬运 xianyu-super-butler (Mxucc) 的自动发货逻辑

功能:
  - 虚拟商品卡券管理 (存储、分配、库存追踪)
  - 订单匹配 → 自动发货 → 发货通知
  - 多规格商品支持 (如不同版本的激活码)
  - 延时发货规则 (防止秒发引起平台风控)

集成点:
  - xianyu_live.py 的 WebSocket 订单事件 → 触发自动发货
  - order_notifier.py → 发货后通知卖家
  - xianyu_context.py → 订单状态更新

用法:
    from src.xianyu.auto_shipper import AutoShipper
    shipper = AutoShipper()
    result = shipper.process_order(order_id, item_id, buyer_id)
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

from src.db_utils import get_conn as _get_db_conn

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DB_PATH = _DATA_DIR / "auto_shipper.db"


class AutoShipper:
    """闲鱼虚拟商品自动发货引擎"""

    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        """SQLite 连接 (委托给全局连接工厂)"""
        with _get_db_conn(self.db_path, row_factory=sqlite3.Row) as conn:
            yield conn

    def _init_db(self):
        with self._conn() as conn:
            # 卡券库存表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS card_inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    spec TEXT DEFAULT '',
                    card_content TEXT NOT NULL,
                    status TEXT DEFAULT 'available',
                    assigned_order TEXT DEFAULT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    used_at TEXT DEFAULT NULL,
                    UNIQUE(item_id, card_content)
                )
            """)
            # 发货规则表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shipping_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL UNIQUE,
                    auto_ship BOOLEAN DEFAULT 1,
                    delay_seconds INTEGER DEFAULT 30,
                    reply_template TEXT DEFAULT '您好，您的卡券如下：\\n{card_content}\\n请注意保存，如有问题随时联系~',
                    max_daily_ship INTEGER DEFAULT 50
                )
            """)
            # 发货记录表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shipping_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    buyer_id TEXT DEFAULT '',
                    card_id INTEGER,
                    card_content TEXT DEFAULT '',
                    status TEXT DEFAULT 'shipped',
                    shipped_at TEXT DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (card_id) REFERENCES card_inventory(id),
                    UNIQUE(order_id)
                )
            """)

    # ── 卡券管理 ──

    def add_cards(self, item_id: str, cards: List[str], spec: str = "") -> Dict:
        """批量添加卡券到库存"""
        added = 0
        duplicates = 0
        with self._conn() as conn:
            for card in cards:
                card = card.strip()
                if not card:
                    continue
                try:
                    conn.execute(
                        "INSERT INTO card_inventory (item_id, spec, card_content) VALUES (?,?,?)", (item_id, spec, card)
                    )
                    added += 1
                except sqlite3.IntegrityError as e:  # noqa: F841
                    duplicates += 1
        logger.info("[AutoShipper] 添加卡券: item=%s, 成功=%d, 重复=%d", item_id, added, duplicates)
        return {"added": added, "duplicates": duplicates}

    def get_inventory(self, item_id: str = None) -> List[Dict]:
        """查看库存状态"""
        with self._conn() as conn:
            if item_id:
                rows = conn.execute(
                    """SELECT item_id, spec,
                       SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) as available,
                       SUM(CASE WHEN status='used' THEN 1 ELSE 0 END) as used,
                       COUNT(*) as total
                       FROM card_inventory WHERE item_id=? GROUP BY item_id, spec""",
                    (item_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT item_id, spec,
                       SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) as available,
                       SUM(CASE WHEN status='used' THEN 1 ELSE 0 END) as used,
                       COUNT(*) as total
                       FROM card_inventory GROUP BY item_id, spec"""
                ).fetchall()
        return [dict(r) for r in rows]

    # ── 发货规则 ──

    def set_rule(
        self,
        item_id: str,
        auto_ship: bool = True,
        delay_seconds: int = 30,
        reply_template: str = None,
        max_daily_ship: int = 50,
    ) -> Dict:
        """设置商品发货规则"""
        template = reply_template or "您好，您的卡券如下：\n{card_content}\n请注意保存，如有问题随时联系~"
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO shipping_rules (item_id, auto_ship, delay_seconds, reply_template, max_daily_ship)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET
                   auto_ship=excluded.auto_ship, delay_seconds=excluded.delay_seconds,
                   reply_template=excluded.reply_template, max_daily_ship=excluded.max_daily_ship""",
                (item_id, auto_ship, max(10, delay_seconds), template, max_daily_ship),
            )
        return {"success": True, "item_id": item_id}

    def get_rule(self, item_id: str) -> Optional[Dict]:
        """获取商品发货规则"""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM shipping_rules WHERE item_id=?", (item_id,)).fetchone()
        return dict(row) if row else None

    # ── 发货执行 ──

    def process_order(self, order_id: str, item_id: str, buyer_id: str = "", spec: str = "") -> Dict:
        """处理订单 → 分配卡券 → 返回发货内容"""
        # 检查发货规则
        rule = self.get_rule(item_id)
        if rule and not rule["auto_ship"]:
            return {"success": False, "reason": "该商品未启用自动发货"}

        # 幂等: 检查是否已处理过此订单
        with self._conn() as conn:
            existing = conn.execute("SELECT id FROM shipping_log WHERE order_id=?", (order_id,)).fetchone()
            if existing:
                return {"success": True, "reason": "已发货（幂等跳过）", "duplicate": True}

        # 检查今日发货量
        with self._conn() as conn:
            today_count = conn.execute(
                "SELECT COUNT(*) FROM shipping_log WHERE item_id=? AND shipped_at >= date('now','localtime')",
                (item_id,),
            ).fetchone()[0]
            max_daily = rule["max_daily_ship"] if rule else 50
            if today_count >= max_daily:
                logger.warning("[AutoShipper] 今日发货已达上限: item=%s, count=%d", item_id, today_count)
                return {"success": False, "reason": f"今日发货已达上限 ({max_daily})"}

            # 原子性分配: 用子查询避免竞态
            cursor = conn.execute(
                """UPDATE card_inventory SET status='used', assigned_order=?, used_at=datetime('now','localtime')
                   WHERE id = (SELECT id FROM card_inventory
                               WHERE item_id=? AND spec=? AND status='available'
                               ORDER BY id LIMIT 1)
                   AND status='available'""",
                (order_id, item_id, spec),
            )
            if cursor.rowcount == 0:
                # 尝试不限规格
                cursor = conn.execute(
                    """UPDATE card_inventory SET status='used', assigned_order=?, used_at=datetime('now','localtime')
                       WHERE id = (SELECT id FROM card_inventory
                                   WHERE item_id=? AND status='available'
                                   ORDER BY id LIMIT 1)
                       AND status='available'""",
                    (order_id, item_id),
                )

            if cursor.rowcount == 0:
                logger.warning("[AutoShipper] 库存不足: item=%s", item_id)
                return {"success": False, "reason": "库存不足，请补充卡券"}

            # 查询刚刚分配的卡券内容
            card = conn.execute(
                "SELECT id, card_content FROM card_inventory WHERE assigned_order=? AND status='used'", (order_id,)
            ).fetchone()

            # 记录发货日志
            conn.execute(
                "INSERT INTO shipping_log (order_id, item_id, buyer_id, card_id, card_content) VALUES (?,?,?,?,?)",
                (order_id, item_id, buyer_id, card["id"], card["card_content"]),
            )

        # 格式化发货消息
        template = rule["reply_template"] if rule else "您好，您的卡券如下：\n{card_content}\n请注意保存~"
        message = template.replace("{card_content}", card["card_content"])

        remaining = self._get_remaining(item_id)
        logger.info(
            "[AutoShipper] 发货成功: order=%s, item=%s, card=#%d, 剩余=%d", order_id, item_id, card["id"], remaining
        )
        result = {
            "success": True,
            "order_id": order_id,
            "card_content": card["card_content"],
            "message": message,
            "remaining": remaining,
        }
        # 发货后库存预警
        if remaining <= 3:
            result["low_stock_warning"] = f"⚠️ {item_id} 库存仅剩 {remaining} 张，请及时补货"
        return result

    def _get_remaining(self, item_id: str) -> int:
        """获取剩余库存"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM card_inventory WHERE item_id=? AND status='available'", (item_id,)
            ).fetchone()
        return row[0] if row else 0

    def check_low_stock(self, threshold: int = 3) -> List[Dict]:
        """检查低库存商品 — 返回库存低于阈值的商品列表"""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT item_id, COUNT(*) as available
                   FROM card_inventory WHERE status='available'
                   GROUP BY item_id HAVING available < ?""",
                (threshold,),
            ).fetchall()
        return [{"item_id": r["item_id"], "available": r["available"]} for r in rows]

    def get_shipping_stats(self, item_id: str = None) -> Dict:
        """发货统计"""
        with self._conn() as conn:
            if item_id:
                total = conn.execute("SELECT COUNT(*) FROM shipping_log WHERE item_id=?", (item_id,)).fetchone()[0]
                today = conn.execute(
                    "SELECT COUNT(*) FROM shipping_log WHERE item_id=? AND shipped_at >= date('now','localtime')",
                    (item_id,),
                ).fetchone()[0]
            else:
                total = conn.execute("SELECT COUNT(*) FROM shipping_log").fetchone()[0]
                today = conn.execute(
                    "SELECT COUNT(*) FROM shipping_log WHERE shipped_at >= date('now','localtime')"
                ).fetchone()[0]
        return {"total_shipped": total, "today_shipped": today}
