"""
交易日志 — 绩效统计 Mixin
提供绩效计算、今日盈亏、权益曲线、格式化报告等功能。
"""
import math
from datetime import datetime, timedelta

from src.utils import now_et


class JournalPerformanceMixin:
    """绩效统计相关方法，依赖主类的 _conn() / get_closed_trades() / get_config()"""

    def get_performance(self, days: int = 30) -> dict:
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

    def get_today_pnl(self) -> dict:
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
        equity_values: list[float] = []
        date_labels: list[str] = []
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
