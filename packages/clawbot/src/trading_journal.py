"""
ClawBot 交易日志 & 绩效系统 v1.0
对标真实专业交易团队的完整交易生命周期管理

功能：
- 交易日志：每笔交易完整记录（入场理由/AI分析/止损止盈/实际盈亏）
- 绩效仪表盘：胜率/盈亏比/夏普比率/最大回撤/日PnL
- 自动复盘：收盘后生成复盘报告，供AI团队总结经验教训
- 持仓监控：追踪止损/止盈触发
"""
from src.utils import now_et
import sqlite3
import os
import logging
import math
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "trading.db")


class TradingJournal:
    """专业交易日志系统"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        # P2#27: timeout=10 防止并发 "database is locked"
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
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
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default

    def set_config(self, key: str, value: str):
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
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        return dict(row) if row else None

    # ============ 复盘 ============

    def save_review_session(self, date: str, session_type: str = 'daily',
                            **kwargs) -> int:
        """保存复盘会议"""
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO review_sessions (date, session_type,
                    trades_reviewed, total_pnl, win_rate,
                    market_summary, good_trades, bad_trades,
                    lessons_learned, improvements, next_day_plan,
                    full_report, participants)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date, session_type,
                  kwargs.get('trades_reviewed', 0),
                  kwargs.get('total_pnl', 0),
                  kwargs.get('win_rate', 0),
                  kwargs.get('market_summary', ''),
                  kwargs.get('good_trades', ''),
                  kwargs.get('bad_trades', ''),
                  kwargs.get('lessons_learned', ''),
                  kwargs.get('improvements', ''),
                  kwargs.get('next_day_plan', ''),
                  kwargs.get('full_report', ''),
                  kwargs.get('participants', '')))
            return cursor.lastrowid

    def get_latest_review(self, session_type: str = 'daily') -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM review_sessions WHERE session_type=? ORDER BY date DESC LIMIT 1",
                (session_type,)
            ).fetchone()
        return dict(row) if row else None

    def get_review_history(self, limit: int = 5) -> List[Dict]:
        """获取历史复盘记录列表"""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, date, session_type, trades_reviewed, total_pnl,
                          win_rate, lessons_learned, improvements, created_at
                   FROM review_sessions
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ============ 绩效统计 ============

    def get_performance(self, days: int = 30) -> Dict:
        """计算绩效指标"""
        trades = self.get_closed_trades(days=days, limit=1000)
        if not trades:
            return {
                "total_trades": 0, "win_rate": 0, "avg_pnl": 0,
                "total_pnl": 0, "profit_factor": 0, "avg_hold_hours": 0,
                "max_win": 0, "max_loss": 0, "sharpe": 0, "max_drawdown": 0,
                "avg_win": 0, "avg_loss": 0, "expectancy": 0,
                "consecutive_wins": 0, "consecutive_losses": 0,
            }

        pnls = [t['pnl'] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_pnl = sum(pnls)
        win_rate = len(wins) / len(pnls) * 100 if pnls else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf')

        # 期望值 = 胜率 * 平均盈利 + 败率 * 平均亏损
        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

        # 夏普比率（简化版，假设无风险利率=0）
        if len(pnls) > 1:
            import statistics
            mean_pnl = statistics.mean(pnls)
            std_pnl = statistics.stdev(pnls)
            sharpe = (mean_pnl / std_pnl) * math.sqrt(252) if std_pnl > 0 else 0
        else:
            sharpe = 0

        # 最大回撤
        cumulative = []
        running = 0
        for p in pnls:
            running += p
            cumulative.append(running)
        peak = cumulative[0]
        max_dd = 0
        for c in cumulative:
            if c > peak:
                peak = c
            dd = peak - c
            if dd > max_dd:
                max_dd = dd

        # 连续胜/败
        max_consec_wins = 0
        max_consec_losses = 0
        current_wins = 0
        current_losses = 0
        for p in pnls:
            if p > 0:
                current_wins += 1
                current_losses = 0
                max_consec_wins = max(max_consec_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consec_losses = max(max_consec_losses, current_losses)

        hold_hours = [t['hold_duration_hours'] or 0 for t in trades]

        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / len(trades), 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "max_win": round(max(pnls), 2) if pnls else 0,
            "max_loss": round(min(pnls), 2) if pnls else 0,
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else 999,
            "expectancy": round(expectancy, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 2),
            "avg_hold_hours": round(sum(hold_hours) / len(hold_hours), 1) if hold_hours else 0,
            "consecutive_wins": max_consec_wins,
            "consecutive_losses": max_consec_losses,
        }

    def get_today_pnl(self) -> Dict:
        """今日盈亏"""
        from src.utils import today_et_str
        today = today_et_str()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status='closed' AND substr(exit_time,1,10)=?",
                (today,)
            ).fetchall()
        trades = [dict(r) for r in rows]
        pnl = sum(t['pnl'] for t in trades)
        wins = sum(1 for t in trades if t['pnl'] > 0)
        return {
            "date": today,
            "trades": len(trades),
            "wins": wins,
            "losses": len(trades) - wins,
            "pnl": round(pnl, 2),
            "limit": float(self.get_config('daily_loss_limit', '100')),
            "hit_limit": pnl <= -float(self.get_config('daily_loss_limit', '100')),
        }

    def get_equity_curve(self, days: int = 30) -> tuple:
        """生成权益曲线数据（按日聚合）。

        Returns:
            (equity_values, date_labels) — 累计权益序列和日期标签。
            无交易时返回空列表。
        """
        since = (now_et() - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT substr(exit_time,1,10) AS d, SUM(pnl) AS daily_pnl
                   FROM trades
                   WHERE status='closed' AND exit_time>=?
                   GROUP BY d ORDER BY d ASC""",
                (since,),
            ).fetchall()

        if not rows:
            return ([], [])

        initial_capital = float(self.get_config('initial_capital', '2000'))
        equity_values: List[float] = []
        date_labels: List[str] = []
        running = initial_capital

        for r in rows:
            running += r['daily_pnl']
            equity_values.append(round(running, 2))
            # 日期标签: "3/15"
            try:
                dt = datetime.strptime(r['d'], '%Y-%m-%d')
                date_labels.append(f"{dt.month}/{dt.day}")
            except Exception as e:  # noqa: F841
                date_labels.append(r['d'] or '?')

        return (equity_values, date_labels)

    def format_performance(self, days: int = 30) -> str:
        """格式化绩效报告"""
        p = self.get_performance(days)
        today = self.get_today_pnl()

        if p['total_trades'] == 0:
            return (
                "绩效仪表盘\n\n"
                "暂无交易记录。\n"
                "说「开始投资」启动AI团队。"
            )

        lines = [
            f"绩效仪表盘 (近{days}天)",
            "",
            f"总交易: {p['total_trades']}笔 (胜{p['wins']} 负{p['losses']})",
            f"胜率: {p['win_rate']}%",
            f"总盈亏: ${p['total_pnl']:+.2f}",
            f"平均盈亏: ${p['avg_pnl']:+.2f}/笔",
            "",
            f"平均盈利: ${p['avg_win']:+.2f}",
            f"平均亏损: ${p['avg_loss']:.2f}",
            f"盈亏比: {abs(p['avg_win']/p['avg_loss']):.2f}" if p['avg_loss'] != 0 else "盈亏比: N/A",
            f"利润因子: {p['profit_factor']}",
            f"期望值: ${p['expectancy']:+.2f}/笔",
            "",
            f"夏普比率: {p['sharpe']}",
            f"最大回撤: ${p['max_drawdown']:.2f}",
            f"最大单笔盈利: ${p['max_win']:+.2f}",
            f"最大单笔亏损: ${p['max_loss']:.2f}",
            "",
            f"平均持仓: {p['avg_hold_hours']}小时",
            f"连续胜: {p['consecutive_wins']}次",
            f"连续败: {p['consecutive_losses']}次",
            "",
            f"-- 今日 ({today['date']}) --",
            f"交易: {today['trades']}笔 (胜{today['wins']} 负{today['losses']})",
            f"盈亏: ${today['pnl']:+.2f} / 日限额-${today['limit']:.0f}",
        ]
        if today['hit_limit']:
            lines.append("!! 已触及日亏损限额，建议停止交易 !!")

        return "\n".join(lines)

    def generate_review_data(self, date: str = None) -> Dict:
        """生成复盘数据（供AI团队复盘用）"""
        if date is None:
            date = now_et().strftime('%Y-%m-%d')

        with self._conn() as conn:
            trades = conn.execute(
                "SELECT * FROM trades WHERE substr(exit_time,1,10)=? AND status='closed' ORDER BY exit_time",
                (date,)
            ).fetchall()
            open_trades = conn.execute(
                "SELECT * FROM trades WHERE status='open'"
            ).fetchall()

        trades = [dict(r) for r in trades]
        open_trades = [dict(r) for r in open_trades]

        good = [t for t in trades if t['pnl'] > 0]
        bad = [t for t in trades if t['pnl'] <= 0]
        total_pnl = sum(t['pnl'] for t in trades)

        perf = self.get_performance(days=30)

        return {
            "date": date,
            "closed_trades": trades,
            "open_trades": open_trades,
            "good_trades": good,
            "bad_trades": bad,
            "total_pnl": round(total_pnl, 2),
            "trade_count": len(trades),
            "win_rate": round(len(good) / len(trades) * 100, 1) if trades else 0,
            "performance_30d": perf,
        }

    def format_review_prompt(self, date: str = None) -> str:
        """生成复盘提示词（给AI团队用）"""
        data = self.generate_review_data(date)

        lines = [
            f"【交易复盘 {data['date']}】",
            f"今日交易: {data['trade_count']}笔",
            f"今日盈亏: ${data['total_pnl']:+.2f}",
            f"今日胜率: {data['win_rate']}%",
            "",
        ]

        if data['closed_trades']:
            lines.append("-- 今日已平仓交易 --")
            for t in data['closed_trades']:
                lines.append(
                    f"#{t['id']} {t['side']} {t['symbol']} x{t['quantity']} "
                    f"入:{t['entry_price']} 出:{t['exit_price']} "
                    f"PnL:${t['pnl']:+.2f}({t['pnl_pct']:+.1f}%) "
                    f"持仓:{t['hold_duration_hours']}h "
                    f"理由:{t['entry_reason'] or '无'}"
                )

        if data['open_trades']:
            lines.append("\n-- 当前持仓 --")
            for t in data['open_trades']:
                lines.append(
                    f"#{t['id']} {t['side']} {t['symbol']} x{t['quantity']} "
                    f"入:{t['entry_price']} 止损:{t['stop_loss']} 止盈:{t['take_profit']}"
                )

        p = data['performance_30d']
        lines.append("\n-- 近30天绩效 --")
        lines.append(f"总交易:{p['total_trades']} 胜率:{p['win_rate']}% 总PnL:${p['total_pnl']:+.2f}")
        lines.append(f"夏普:{p['sharpe']} 最大回撤:${p['max_drawdown']:.2f} 期望值:${p['expectancy']:+.2f}")

        return "\n".join(lines)

    # ============ 盈利目标管理 ============

    def set_profit_target(self, period: str, target_pnl: float,
                          target_trades: int = 0, target_win_rate: float = 0,
                          notes: str = '') -> int:
        """设定盈利目标（daily/weekly/monthly）"""
        from src.utils import now_et
        _now = now_et()

        if period == 'daily':
            start = _now.strftime('%Y-%m-%d')
            end = start
        elif period == 'weekly':
            # 本周一到周五
            start = (_now - timedelta(days=_now.weekday())).strftime('%Y-%m-%d')
            end = (_now + timedelta(days=4 - _now.weekday())).strftime('%Y-%m-%d')
        elif period == 'monthly':
            start = _now.strftime('%Y-%m-01')
            import calendar
            last_day = calendar.monthrange(_now.year, _now.month)[1]
            end = _now.strftime(f'%Y-%m-{last_day:02d}')
        else:
            start = end = _now.strftime('%Y-%m-%d')

        with self._conn() as conn:
            # 取消同周期旧目标
            conn.execute(
                "UPDATE profit_targets SET status='cancelled' WHERE period=? AND status='active'",
                (period,)
            )
            cursor = conn.execute("""
                INSERT INTO profit_targets (period, period_start, period_end,
                    target_pnl, target_trades, target_win_rate, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (period, start, end, target_pnl, target_trades, target_win_rate, notes))
            tid = cursor.lastrowid

        logger.info(f"[Journal] 设定{period}盈利目标: ${target_pnl:+.2f} ({start}~{end})")
        return tid

    def update_profit_target_progress(self):
        """更新所有活跃盈利目标的实际进度"""
        with self._conn() as conn:
            targets = conn.execute(
                "SELECT * FROM profit_targets WHERE status='active'"
            ).fetchall()

            for t in targets:
                # 统计周期内已平仓交易
                rows = conn.execute("""
                    SELECT pnl FROM trades
                    WHERE status='closed' AND substr(exit_time,1,10) BETWEEN ? AND ?
                """, (t['period_start'], t['period_end'])).fetchall()

                pnls = [r['pnl'] for r in rows]
                actual_pnl = sum(pnls)
                actual_trades = len(pnls)
                wins = sum(1 for p in pnls if p > 0)
                actual_win_rate = (wins / actual_trades * 100) if actual_trades > 0 else 0

                status = 'active'
                if actual_pnl >= t['target_pnl'] and t['target_pnl'] > 0:
                    status = 'achieved'

                conn.execute("""
                    UPDATE profit_targets SET actual_pnl=?, actual_trades=?,
                        actual_win_rate=?, status=?, updated_at=datetime('now')
                    WHERE id=?
                """, (round(actual_pnl, 2), actual_trades,
                      round(actual_win_rate, 1), status, t['id']))

    def get_active_targets(self) -> List[Dict]:
        """获取所有活跃盈利目标"""
        self.update_profit_target_progress()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM profit_targets WHERE status IN ('active','achieved') ORDER BY period"
            ).fetchall()
        return [dict(r) for r in rows]

    def format_target_progress(self) -> str:
        """格式化盈利目标进度"""
        targets = self.get_active_targets()
        if not targets:
            return "暂未设定盈利目标。\n用 /target <日/周/月> <金额> 设定目标。"

        lines = ["盈利目标进度\n"]
        for t in targets:
            pct = (t['actual_pnl'] / t['target_pnl'] * 100) if t['target_pnl'] != 0 else 0
            bar_len = 15
            filled = min(int(bar_len * abs(pct) / 100), bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)

            period_label = {'daily': '日', 'weekly': '周', 'monthly': '月'}.get(t['period'], t['period'])
            status_icon = '✓' if t['status'] == 'achieved' else '→'

            lines.append(
                f"{status_icon} {period_label}目标: ${t['target_pnl']:+.0f}\n"
                f"  [{bar}] {pct:.0f}%\n"
                f"  实际: ${t['actual_pnl']:+.2f} | {t['actual_trades']}笔 | 胜率{t['actual_win_rate']:.0f}%\n"
                f"  周期: {t['period_start']}~{t['period_end']}"
            )
        return "\n".join(lines)

    # ============ 研判预期记录 & 收盘验证 ============

    def record_prediction(self, symbol: str, direction: str, target_price: float,
                          stop_price: float = 0, timeframe: str = '1d',
                          confidence: float = 0.5, reasoning: str = '',
                          decided_by: str = '', trade_id: int = None) -> int:
        """记录 AI 研判预期（开仓时调用）"""
        from src.utils import now_et
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO predictions (trade_id, symbol, prediction_time,
                    predicted_direction, predicted_target, predicted_stop,
                    predicted_timeframe, confidence, ai_reasoning, decided_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (trade_id, symbol.upper(), now_et().isoformat(),
                  direction.upper(), target_price, stop_price, timeframe,
                  confidence, reasoning, decided_by))
            return cursor.lastrowid

    def validate_predictions(self, date: str = None) -> Dict:
        """收盘验证：对比 AI 研判 vs 实际走势"""
        if date is None:
            date = now_et().strftime('%Y-%m-%d')

        with self._conn() as conn:
            preds = conn.execute("""
                SELECT * FROM predictions
                WHERE substr(prediction_time,1,10)=? AND validation_time IS NULL
            """, (date,)).fetchall()

        if not preds:
            return {"date": date, "predictions": 0, "validated": 0, "accuracy": 0}

        validated = 0
        correct = 0

        for p in preds:
            p = dict(p)
            symbol = p['symbol']

            # 获取实际收盘价（从 yfinance）
            try:
                from src.invest_tools import get_stock_quote
                quote = get_stock_quote(symbol)
                if not quote:
                    continue
                actual_close = quote.get('price', 0)
                if actual_close <= 0:
                    continue
            except Exception as e:  # noqa: F841
                continue

            # 计算实际方向
            entry_ref = p['predicted_stop'] if p['predicted_stop'] > 0 else actual_close * 0.98
            if p['predicted_direction'] == 'UP':
                direction_correct = actual_close > entry_ref
            elif p['predicted_direction'] == 'DOWN':
                direction_correct = actual_close < entry_ref
            else:
                direction_correct = False

            # 目标价是否触及
            target_hit = 0
            if p['predicted_target'] and p['predicted_target'] > 0:
                if p['predicted_direction'] == 'UP':
                    target_hit = 1 if actual_close >= p['predicted_target'] else 0
                else:
                    target_hit = 1 if actual_close <= p['predicted_target'] else 0

            # 偏差
            deviation = 0
            if p['predicted_target'] and p['predicted_target'] > 0:
                deviation = (actual_close - p['predicted_target']) / p['predicted_target'] * 100

            with self._conn() as conn:
                conn.execute("""
                    UPDATE predictions SET actual_close=?, actual_direction=?,
                        direction_correct=?, target_hit=?, deviation_pct=?,
                        validation_time=datetime('now')
                    WHERE id=?
                """, (actual_close,
                      'UP' if actual_close > entry_ref else 'DOWN',
                      1 if direction_correct else 0,
                      target_hit, round(deviation, 2), p['id']))

            validated += 1
            if direction_correct:
                correct += 1

        accuracy = (correct / validated * 100) if validated > 0 else 0
        return {
            "date": date,
            "predictions": len(preds),
            "validated": validated,
            "correct": correct,
            "accuracy": round(accuracy, 1),
        }

    def get_prediction_accuracy(self, days: int = 30) -> Dict:
        """获取指定天数内的研判准确率统计"""
        since = (now_et() - timedelta(days=days)).strftime('%Y-%m-%d')
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT decided_by, 
                       COUNT(*) as total,
                       SUM(CASE WHEN direction_correct=1 THEN 1 ELSE 0 END) as correct,
                       AVG(ABS(deviation_pct)) as avg_deviation
                FROM predictions
                WHERE validation_time IS NOT NULL AND substr(prediction_time,1,10) >= ?
                GROUP BY decided_by
            """, (since,)).fetchall()

        by_ai = {}
        total_all = 0
        correct_all = 0
        for r in rows:
            r = dict(r)
            ai_name = r['decided_by'] or 'unknown'
            acc = (r['correct'] / r['total'] * 100) if r['total'] > 0 else 0
            by_ai[ai_name] = {
                "total": r['total'],
                "correct": r['correct'],
                "accuracy": round(acc, 1),
                "avg_deviation": round(r['avg_deviation'] or 0, 2),
            }
            total_all += r['total']
            correct_all += r['correct']

        return {
            "days": days,
            "total_predictions": total_all,
            "overall_accuracy": round(correct_all / total_all * 100, 1) if total_all > 0 else 0,
            "by_ai": by_ai,
        }

    # ============ 周期复盘迭代 ============

    def generate_iteration_report(self, days: int = 7) -> Dict:
        """生成迭代改进报告：分析失败交易的模式"""
        since = (now_et() - timedelta(days=days)).strftime('%Y-%m-%d')

        with self._conn() as conn:
            # 所有亏损交易
            bad_trades = conn.execute("""
                SELECT * FROM trades
                WHERE status='closed' AND pnl < 0 AND substr(exit_time,1,10) >= ?
                ORDER BY pnl ASC
            """, (since,)).fetchall()

            # 所有盈利交易
            good_trades = conn.execute("""
                SELECT * FROM trades
                WHERE status='closed' AND pnl > 0 AND substr(exit_time,1,10) >= ?
                ORDER BY pnl DESC
            """, (since,)).fetchall()

            # 研判不准确的
            wrong_preds = conn.execute("""
                SELECT * FROM predictions
                WHERE validation_time IS NOT NULL AND direction_correct=0
                    AND substr(prediction_time,1,10) >= ?
            """, (since,)).fetchall()

        bad_trades = [dict(r) for r in bad_trades]
        good_trades = [dict(r) for r in good_trades]
        wrong_preds = [dict(r) for r in wrong_preds]

        # 分析失败模式
        patterns = []
        for t in bad_trades:
            reason = t.get('entry_reason', '') or ''
            exit_r = t.get('exit_reason', '') or ''
            hold_h = t.get('hold_duration_hours', 0) or 0

            if hold_h < 0.5:
                patterns.append('过快止损（持仓<30分钟）')
            if hold_h > 48:
                patterns.append('持仓过久（>48小时未止损）')
            if '追涨' in reason or '突破' in reason:
                patterns.append('追涨买入')
            if t.get('pnl_pct', 0) < -5:
                sym = t.get('symbol', '?')
                pct = t.get('pnl_pct', 0)
                patterns.append(f'大额亏损（{sym} {pct:.1f}%）')

        # 统计模式频率
        from collections import Counter
        pattern_freq = Counter(patterns)

        return {
            "period_days": days,
            "total_trades": len(bad_trades) + len(good_trades),
            "bad_trades_count": len(bad_trades),
            "good_trades_count": len(good_trades),
            "total_loss": round(sum(t['pnl'] for t in bad_trades), 2),
            "total_profit": round(sum(t['pnl'] for t in good_trades), 2),
            "wrong_predictions": len(wrong_preds),
            "failure_patterns": dict(pattern_freq.most_common(5)),
            "worst_trades": bad_trades[:3],
            "best_trades": good_trades[:3],
            "improvement_suggestions": self._generate_suggestions(pattern_freq, bad_trades),
        }

    def _generate_suggestions(self, pattern_freq: dict, bad_trades: list) -> List[str]:
        """根据失败模式生成改进建议"""
        suggestions = []

        if pattern_freq.get('过快止损（持仓<30分钟）', 0) >= 2:
            suggestions.append("止损设太紧：考虑用 1.5-2x ATR 替代固定百分比止损")

        if pattern_freq.get('持仓过久（>48小时未止损）', 0) >= 1:
            suggestions.append("超短线不应持仓超过2天：增加时间止损规则")

        if pattern_freq.get('追涨买入', 0) >= 2:
            suggestions.append("追涨亏损率高：限制只在回调到支撑位时入场")

        if len(bad_trades) > 0:
            avg_loss = sum(t['pnl'] for t in bad_trades) / len(bad_trades)
            if abs(avg_loss) > 50:
                suggestions.append(f"平均亏损${abs(avg_loss):.0f}过大：减小仓位或收紧止损")

        if not suggestions:
            suggestions.append("近期无明显失败模式，继续保持当前策略")

        return suggestions

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

