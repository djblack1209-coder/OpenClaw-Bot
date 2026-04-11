"""
ClawBot 交易日志 & 绩效系统 v1.1
对标真实专业交易团队的完整交易生命周期管理

功能：
- 交易日志：每笔交易完整记录（入场理由/AI分析/止损止盈/实际盈亏）
- 绩效仪表盘：胜率/盈亏比/夏普比率/最大回撤/日PnL
- 自动复盘：收盘后生成复盘报告，供AI团队总结经验教训
- 持仓监控：追踪止损/止盈触发

v1.1: 拆分为 Mixin 模块（HI-358），按 DB 表域名分离：
- journal_performance.py  — 绩效统计
- journal_predictions.py  — 研判预期 & 验证
- journal_targets.py      — 盈利目标管理
- journal_review.py       — 复盘 & 迭代改进
"""
from src.utils import now_et
import sqlite3
import os
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import List, Dict, Optional

# 导入所有 Mixin
from src.journal_performance import JournalPerformanceMixin
from src.journal_predictions import JournalPredictionsMixin
from src.journal_targets import JournalTargetsMixin
from src.journal_review import JournalReviewMixin

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "trading.db")


class TradingJournal(
    JournalPerformanceMixin,
    JournalPredictionsMixin,
    JournalTargetsMixin,
    JournalReviewMixin,
):
    """专业交易日志系统（Mixin 架构）"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        # P2#27: timeout=10 防止并发 "database is locked"
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        except Exception as e:  # noqa: F841
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            # P2#27: WAL 模式允许并发读 + 单写，大幅减少 lock 冲突
            conn.execute("PRAGMA journal_mode=WAL")
            # 交易记录（完整生命周期）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    -- 基本信息
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,           -- BUY / SELL
                    quantity REAL NOT NULL,
                    -- 入场
                    entry_price REAL,
                    entry_time TEXT,
                    entry_order_id TEXT,
                    -- 出场
                    exit_price REAL,
                    exit_time TEXT,
                    exit_order_id TEXT,
                    -- 止损止盈
                    stop_loss REAL,
                    take_profit REAL,
                    trailing_stop_pct REAL,
                    -- 盈亏
                    pnl REAL DEFAULT 0,
                    pnl_pct REAL DEFAULT 0,
                    fees REAL DEFAULT 0,
                    -- AI决策信息
                    signal_score INTEGER DEFAULT 0,
                    ai_analysis TEXT,             -- AI团队分析摘要
                    entry_reason TEXT,           -- 入场理由
                    exit_reason TEXT,             -- 出场理由
                    decided_by TEXT,              -- 哪个AI决策的
                    -- 复盘
                    review_notes TEXT,            -- 复盘笔记
                    review_score INTEGER,         -- 复盘评分 1-5
                    lessons TEXT,                 -- 经验教训
                    -- 状态
                    status TEXT DEFAULT 'open',   -- open / closed / cancelled
                    hold_duration_hours REAL,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 每日绩效快照
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_pnl (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL UNIQUE,
                    starting_equity REAL,
                    ending_equity REAL,
                    daily_pnl REAL DEFAULT 0,
                    daily_pnl_pct REAL DEFAULT 0,
                    trades_count INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    total_fees REAL DEFAULT 0,
                    max_drawdown_pct REAL DEFAULT 0,
                    notes TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 复盘会议记录
            conn.execute("""
                CREATE TABLE IF NOT EXISTS review_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    session_type TEXT DEFAULT 'daily',  -- daily / weekly / monthly
                    -- 统计
                    trades_reviewed INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    win_rate REAL DEFAULT 0,
                    -- AI复盘内容
                    market_summary TEXT,          -- 当日市场总结
                    good_trades TEXT,             -- 做得好的交易
                    bad_trades TEXT,              -- 做得差的交易
                    lessons_learned TEXT,         -- 经验教训
                    improvements TEXT,            -- 改进建议
                    next_day_plan TEXT,           -- 明日计划
                    full_report TEXT,             -- 完整复盘报告
                    -- 参与者
                    participants TEXT,            -- 参与复盘的AI
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 系统配置
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # 默认配置
            defaults = {
                'initial_capital': '2000',
                'daily_loss_limit': '100',
                'max_position_pct': '30',
                'risk_per_trade_pct': '2',
                'min_risk_reward': '2',
            }
            for k, v in defaults.items():
                conn.execute(
                    "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v)
                )

            # 盈利目标表（日/周/月）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS profit_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period TEXT NOT NULL,            -- daily / weekly / monthly
                    period_start TEXT NOT NULL,      -- 周期起始日
                    period_end TEXT NOT NULL,        -- 周期截止日
                    target_pnl REAL NOT NULL,        -- 目标盈亏金额
                    actual_pnl REAL DEFAULT 0,       -- 实际盈亏
                    target_trades INTEGER DEFAULT 0, -- 目标交易笔数
                    actual_trades INTEGER DEFAULT 0, -- 实际交易笔数
                    target_win_rate REAL DEFAULT 0,  -- 目标胜率
                    actual_win_rate REAL DEFAULT 0,  -- 实际胜率
                    status TEXT DEFAULT 'active',    -- active / achieved / missed / cancelled
                    notes TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

            # 研判预期表（收盘验证用）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER,                -- 关联交易ID
                    symbol TEXT NOT NULL,
                    prediction_time TEXT NOT NULL,    -- 预测时间
                    predicted_direction TEXT,         -- UP / DOWN / SIDEWAYS
                    predicted_target REAL,            -- 预测目标价
                    predicted_stop REAL,              -- 预测止损价
                    predicted_timeframe TEXT,         -- 预测时间框架 (1d/3d/1w)
                    confidence REAL DEFAULT 0,        -- 置信度 0-1
                    ai_reasoning TEXT,               -- AI 推理过程
                    decided_by TEXT,                  -- 哪个AI的判断
                    -- 验证结果（收盘时回填）
                    actual_close REAL,               -- 实际收盘价
                    actual_direction TEXT,            -- 实际方向
                    direction_correct INTEGER,        -- 方向是否正确 0/1
                    target_hit INTEGER DEFAULT 0,     -- 是否触及目标价 0/1
                    deviation_pct REAL,              -- 偏差百分比
                    validation_time TEXT,             -- 验证时间
                    validation_notes TEXT,            -- 验证备注
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

    # ============ 配置 ============

    def get_config(self, key: str, default: str = '0') -> str:
        """获取配置项"""
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default

    def set_config(self, key: str, value: str):
        """设置配置项"""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value)
            )

    # ============ 交易记录 ============

    def open_trade(self, symbol: str, side: str, quantity: float,
                   entry_price: float, entry_order_id: str = '',
                   stop_loss: float = 0, take_profit: float = 0,
                   signal_score: int = 0, ai_analysis: str = '',
                   entry_reason: str = '', decided_by: str = '',
                   status: str = 'open') -> int:
        """开仓记录"""
        from src.utils import now_et
        _now_et = now_et()
        safe_status = str(status or 'open').lower()
        if safe_status not in ('open', 'pending', 'closed', 'cancelled'):
            safe_status = 'open'
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO trades (symbol, side, quantity, entry_price, entry_time,
                    entry_order_id, stop_loss, take_profit, signal_score,
                    ai_analysis, entry_reason, decided_by, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol.upper(), side.upper(), quantity, entry_price,
                  _now_et.isoformat(), entry_order_id,
                  stop_loss, take_profit, signal_score,
                  ai_analysis, entry_reason, decided_by, safe_status))
            trade_id = cursor.lastrowid
        logger.info(
            f"[Journal] 开仓 #{trade_id}: {side} {symbol} x{quantity} @ {entry_price} "
            f"(status={safe_status})"
        )
        return trade_id

    def get_pending_trades(self, limit: int = 200) -> List[Dict]:
        """获取待成交入场交易（status='pending'）"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='pending' ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_trade_entry_filled(self, trade_id: int, filled_qty: float,
                                fill_price: float, entry_order_id: str = '',
                                fill_time: Optional[str] = None) -> Dict:
        """将 pending 交易回写为 open（成交回补）"""
        if filled_qty <= 0 or fill_price <= 0:
            return {"error": "filled_qty/fill_price 必须大于0"}

        with self._conn() as conn:
            trade = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
            if not trade:
                return {"error": f"交易 #{trade_id} 不存在"}

            existing_order_id = str(trade['entry_order_id'] or '')
            target_order_id = str(entry_order_id or existing_order_id)

            ts = fill_time or now_et().isoformat()
            conn.execute(
                """
                UPDATE trades
                SET quantity=?, entry_price=?, entry_time=?, entry_order_id=?,
                    status='open', updated_at=datetime('now')
                WHERE id=?
                """,
                (float(filled_qty), float(fill_price), ts, target_order_id, trade_id),
            )

        logger.info(
            "[Journal] 成交回写 #%d: qty=%.4f @ %.4f (order=%s)",
            trade_id,
            filled_qty,
            fill_price,
            target_order_id,
        )
        return {
            "trade_id": trade_id,
            "quantity": float(filled_qty),
            "entry_price": float(fill_price),
            "entry_order_id": target_order_id,
            "status": "open",
        }

    def cancel_trade(self, trade_id: int, reason: str = '') -> Dict:
        """取消交易（通常用于 pending 入场订单撤单）"""
        with self._conn() as conn:
            trade = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
            if not trade:
                return {"error": f"交易 #{trade_id} 不存在"}

            if trade['status'] in ('closed', 'cancelled'):
                return {"error": f"交易 #{trade_id} 当前状态为 {trade['status']}"}

            from src.utils import now_et
            _now_et = now_et().isoformat()
            conn.execute(
                """
                UPDATE trades
                SET status='cancelled', exit_time=?, exit_reason=?,
                    updated_at=datetime('now')
                WHERE id=?
                """,
                (_now_et, reason, trade_id),
            )

        logger.info("[Journal] 交易取消 #%d: %s", trade_id, reason)
        return {
            "trade_id": trade_id,
            "status": "cancelled",
            "reason": reason,
        }

    def set_trade_status(self, trade_id: int, status: str,
                         reason: str = '') -> Dict:
        """通用状态更新（open/pending/cancelled）"""
        safe_status = str(status or '').lower().strip()
        if safe_status not in ('open', 'pending', 'cancelled', 'closed'):
            return {"error": f"不支持的状态: {status}"}

        with self._conn() as conn:
            trade = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
            if not trade:
                return {"error": f"交易 #{trade_id} 不存在"}

            params = [safe_status, trade_id]
            sql = "UPDATE trades SET status=?, updated_at=datetime('now') WHERE id=?"

            if safe_status == 'cancelled':
                from src.utils import now_et
                _now_et = now_et().isoformat()
                sql = (
                    "UPDATE trades SET status='cancelled', exit_time=?, exit_reason=?, "
                    "updated_at=datetime('now') WHERE id=?"
                )
                params = [_now_et, reason, trade_id]

            conn.execute(sql, params)

        return {
            "trade_id": trade_id,
            "status": safe_status,
            "reason": reason,
        }

    def close_trade(self, trade_id: int, exit_price: float,
                    exit_order_id: str = '', exit_reason: str = '',
                    fees: float = 0) -> Dict:
        """平仓记录"""
        with self._conn() as conn:
            trade = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
            if not trade:
                return {"error": f"交易 #{trade_id} 不存在"}
            if trade['status'] != 'open':
                return {"error": f"交易 #{trade_id} 已关闭"}

            entry_price = trade['entry_price']
            quantity = trade['quantity']
            side = trade['side']

            if side == 'BUY':
                pnl = (exit_price - entry_price) * quantity - fees
            else:
                pnl = (entry_price - exit_price) * quantity - fees

            pnl_pct = (pnl / (entry_price * quantity)) * 100 if entry_price * quantity > 0 else 0

            entry_time = datetime.fromisoformat(trade['entry_time'])
            from src.utils import now_et, _ET
            _now_et = now_et()
            _tz = _ET if _ET is not None else _now_et.tzinfo
            hold_hours = (_now_et - entry_time.replace(tzinfo=_tz)).total_seconds() / 3600

            conn.execute("""
                UPDATE trades SET exit_price=?, exit_time=?, exit_order_id=?,
                    exit_reason=?, pnl=?, pnl_pct=?, fees=?,
                    hold_duration_hours=?, status='closed',
                    updated_at=datetime('now')
                WHERE id=?
            """, (exit_price, _now_et.isoformat(), exit_order_id,
                  exit_reason, round(pnl, 2), round(pnl_pct, 2), fees,
                  round(hold_hours, 1), trade_id))

        logger.info(f"[Journal] 平仓 #{trade_id}: {trade['symbol']} PnL=${pnl:.2f} ({pnl_pct:.1f}%)")
        return {
            "trade_id": trade_id,
            "symbol": trade['symbol'],
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "hold_hours": round(hold_hours, 1),
        }

    def get_open_trades(self) -> List[Dict]:
        """获取所有未平仓交易"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='open' ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_closed_trades(self, days: int = 30, limit: int = 50) -> List[Dict]:
        """获取已平仓交易"""
        since = (now_et() - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='closed' AND exit_time>=? ORDER BY exit_time DESC LIMIT ?",
                (since, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_trade(self, trade_id: int) -> Optional[Dict]:
        """获取指定交易记录"""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        return dict(row) if row else None

    # ============ 数据清理 ============

    def cleanup(self, days: int = 365) -> int:
        """Delete closed trades older than N days. Returns deleted count."""
        cutoff = (now_et() - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM trades WHERE status='closed' AND exit_time IS NOT NULL AND exit_time < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
        if deleted:
            logger.info("[TradingJournal] cleanup: deleted %d trades older than %d days", deleted, days)
        return deleted


# 全局实例
journal = TradingJournal()
