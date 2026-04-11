"""
交易日志 — 复盘 & 迭代改进 Mixin
提供复盘会议记录、复盘数据生成、迭代改进报告等功能。
"""
from collections import Counter
from datetime import timedelta
from typing import List, Dict, Optional

from src.utils import now_et


class JournalReviewMixin:
    """复盘与迭代相关方法，依赖主类的 _conn() / get_performance()"""

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
        """获取最近一次复盘记录"""
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
