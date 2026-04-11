"""
交易日志 — 研判预期记录 & 收盘验证 Mixin
提供预测记录、验证、准确率统计等功能。
"""
from datetime import timedelta
from typing import Dict

from src.utils import now_et


class JournalPredictionsMixin:
    """研判预期相关方法，依赖主类的 _conn()"""

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
