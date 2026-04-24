"""
交易日志 — 盈利目标管理 Mixin
提供盈利目标设定、进度更新、格式化展示等功能。
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


class JournalTargetsMixin:
    """盈利目标相关方法，依赖主类的 _conn()"""

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

    def get_active_targets(self) -> list[dict]:
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
