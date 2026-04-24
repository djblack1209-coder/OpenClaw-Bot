"""
交易日志 — 研判预期记录 & 收盘验证 Mixin
提供预测记录、验证、准确率统计等功能。
支持共识预测 + 每个AI分析师的个体投票追踪（HI-535）。
"""
import logging
from datetime import timedelta

from src.utils import now_et

logger = logging.getLogger(__name__)


class JournalPredictionsMixin:
    """研判预期相关方法，依赖主类的 _conn()"""

    def record_prediction(self, symbol: str, direction: str, target_price: float,
                          stop_price: float = 0, timeframe: str = '1d',
                          confidence: float = 0.5, reasoning: str = '',
                          decided_by: str = '', trade_id: int = None) -> int:
        """记录 AI 研判预期（开仓时调用），返回 prediction_id"""
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

    def record_vote_records(self, prediction_id: int, symbol: str, votes: list) -> None:
        """记录每个AI分析师的独立投票结果（HI-535）

        参数:
            prediction_id: 关联的 predictions 表 ID
            symbol: 标的代码
            votes: BotVote 对象列表，每个包含 bot_id/vote/confidence 等字段
        """
        if not votes:
            return
        with self._conn() as conn:
            for v in votes:
                # 兼容 BotVote dataclass 的属性名
                bot_id = getattr(v, 'bot_id', '') or ''
                vote = getattr(v, 'vote', 'HOLD') or 'HOLD'
                confidence = getattr(v, 'confidence', 5) or 5
                target_price = getattr(v, 'take_profit', 0) or 0
                stop_price = getattr(v, 'stop_loss', 0) or 0
                reasoning = getattr(v, 'reasoning', '') or ''
                abstained = 1 if getattr(v, 'abstained', False) else 0

                conn.execute("""
                    INSERT INTO vote_records
                        (prediction_id, symbol, bot_id, vote, confidence,
                         target_price, stop_price, reasoning, abstained)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (prediction_id, symbol.upper(), bot_id, vote.upper(),
                      confidence, target_price, stop_price,
                      str(reasoning)[:500], abstained))
        logger.debug("[Predictions] 记录 %d 条个体投票 (prediction_id=%d, symbol=%s)",
                     len(votes), prediction_id, symbol)

    def validate_predictions(self, date: str = None) -> dict:
        """收盘验证：对比 AI 研判 vs 实际走势，同时验证个体投票"""
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

            # 同步验证该预测关联的个体投票记录
            self._validate_vote_records_for_prediction(p['id'], actual_close)

        accuracy = (correct / validated * 100) if validated > 0 else 0
        return {
            "date": date,
            "predictions": len(preds),
            "validated": validated,
            "correct": correct,
            "accuracy": round(accuracy, 1),
        }

    def _validate_vote_records_for_prediction(self, prediction_id: int, actual_close: float) -> None:
        """验证单条预测关联的所有个体投票记录

        判定逻辑：BUY 票 → 价格上涨则正确；SKIP/HOLD 票 → 价格下跌则正确
        弃权的投票不参与验证。
        """
        with self._conn() as conn:
            votes = conn.execute("""
                SELECT id, vote, stop_price, abstained FROM vote_records
                WHERE prediction_id=? AND direction_correct IS NULL AND abstained=0
            """, (prediction_id,)).fetchall()

            for v in votes:
                v = dict(v)
                # 用该投票者自己的止损价做参考基准
                ref = v['stop_price'] if v['stop_price'] and v['stop_price'] > 0 else actual_close * 0.98
                vote_upper = (v['vote'] or '').upper()

                if vote_upper == 'BUY':
                    # BUY 票：价格高于参考价 = 方向正确
                    dir_correct = 1 if actual_close > ref else 0
                elif vote_upper in ('SKIP', 'HOLD'):
                    # SKIP/HOLD 票：价格没涨（低于或等于参考价）= 判断正确
                    dir_correct = 1 if actual_close <= ref else 0
                else:
                    dir_correct = 0

                conn.execute("""
                    UPDATE vote_records SET direction_correct=? WHERE id=?
                """, (dir_correct, v['id']))

    def get_prediction_accuracy(self, days: int = 30) -> dict:
        """获取指定天数内的研判准确率统计（含个体投票准确率）"""
        since = (now_et() - timedelta(days=days)).strftime('%Y-%m-%d')
        with self._conn() as conn:
            # 共识预测准确率（原有逻辑）
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

        # 个体投票准确率（HI-535 新增）
        per_voter = self._get_per_voter_accuracy(since)

        return {
            "days": days,
            "total_predictions": total_all,
            "overall_accuracy": round(correct_all / total_all * 100, 1) if total_all > 0 else 0,
            "by_ai": by_ai,
            "per_voter": per_voter,
        }

    def _get_per_voter_accuracy(self, since: str) -> dict:
        """统计每个AI分析师的个体投票准确率

        返回格式:
        {
            "haiku": {"total": 45, "correct": 28, "accuracy": 62.2, "avg_confidence": 7.2},
            "qwen235b": {"total": 43, "correct": 25, "accuracy": 58.1, "avg_confidence": 6.5},
            ...
        }
        """
        try:
            with self._conn() as conn:
                # 检查 vote_records 表是否存在（兼容旧数据库）
                table_check = conn.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='vote_records'
                """).fetchone()
                if not table_check:
                    return {}

                rows = conn.execute("""
                    SELECT vr.bot_id,
                           COUNT(*) as total,
                           SUM(CASE WHEN vr.direction_correct=1 THEN 1 ELSE 0 END) as correct,
                           AVG(vr.confidence) as avg_confidence
                    FROM vote_records vr
                    JOIN predictions p ON vr.prediction_id = p.id
                    WHERE vr.direction_correct IS NOT NULL
                      AND vr.abstained = 0
                      AND substr(p.prediction_time, 1, 10) >= ?
                    GROUP BY vr.bot_id
                """, (since,)).fetchall()
        except Exception as e:
            logger.warning("[Predictions] 查询个体投票准确率失败: %s", e)
            return {}

        per_voter = {}
        for r in rows:
            r = dict(r)
            bot_id = r['bot_id'] or 'unknown'
            total = r['total'] or 0
            correct_count = r['correct'] or 0
            acc = (correct_count / total * 100) if total > 0 else 0
            per_voter[bot_id] = {
                "total": total,
                "correct": correct_count,
                "accuracy": round(acc, 1),
                "avg_confidence": round(r['avg_confidence'] or 0, 1),
            }
        return per_voter
