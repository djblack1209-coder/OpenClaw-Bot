"""
ClawBot 监控 — 成本归因分析器

对标 LiteLLM 的 Budget Manager + Cost Tracking。
按 bot/用户/功能/模型 维度的成本归因 + 月度预测 + 预算告警。
"""
import time
import sqlite3
import logging
import threading
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class CostAnalyzer:
    """成本归因分析器（对标 LiteLLM 的 Budget Manager + Cost Tracking）

    功能：
    - 按 bot/用户/功能/模型 维度的成本归因
    - 滑动窗口成本追踪（1h / 24h / 7d）
    - 月度成本预测
    - 预算告警
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self._db_path = db_path
        else:
            self._db_path = str(Path(__file__).parent.parent.parent / "data" / "cost_analytics.db")
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()
        # 内存缓存：最近 1000 条记录用于快速聚合
        self._recent: List[Dict[str, Any]] = []
        self._max_recent = 1000

    def _init_db(self):
        conn = sqlite3.connect(self._db_path, timeout=10)
        try:
            # WAL 模式: 多线程高频写入场景防止 database is locked
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cost_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    bot_id TEXT NOT NULL,
                    user_id INTEGER DEFAULT 0,
                    feature TEXT DEFAULT '',
                    model TEXT NOT NULL,
                    provider TEXT DEFAULT '',
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    latency_ms REAL DEFAULT 0.0,
                    success INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_ts ON cost_events(ts)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_bot ON cost_events(bot_id)
            """)
            conn.commit()
        finally:
            conn.close()

    def record(self, bot_id: str, model: str, input_tokens: int = 0,
               output_tokens: int = 0, cost_usd: float = 0.0,
               latency_ms: float = 0.0, success: bool = True,
               user_id: int = 0, feature: str = "", provider: str = ""):
        """记录一次 API 调用的成本事件"""
        now = time.time()
        event = {
            "ts": now, "bot_id": bot_id, "user_id": user_id,
            "feature": feature, "model": model, "provider": provider,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_usd": cost_usd, "latency_ms": latency_ms,
            "success": 1 if success else 0,
        }
        with self._lock:
            self._recent.append(event)
            if len(self._recent) > self._max_recent:
                self._recent = self._recent[-self._max_recent:]
        # 异步写入 DB（不阻塞主线程）
        try:
            with sqlite3.connect(self._db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute(
                    "INSERT INTO cost_events (ts,bot_id,user_id,feature,model,provider,"
                    "input_tokens,output_tokens,cost_usd,latency_ms,success) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (now, bot_id, user_id, feature, model, provider,
                     input_tokens, output_tokens, cost_usd, latency_ms,
                     1 if success else 0)
                )
        except Exception as e:
            logger.debug(f"[CostAnalyzer] DB写入失败: {e}")

    def analyze_by_bot(self, hours: float = 24) -> Dict[str, Dict[str, Any]]:
        """按 bot 维度的成本归因"""
        cutoff = time.time() - hours * 3600
        result: Dict[str, Dict[str, Any]] = {}
        try:
            with sqlite3.connect(self._db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                rows = conn.execute(
                    "SELECT bot_id, SUM(cost_usd), SUM(input_tokens), SUM(output_tokens), "
                    "COUNT(*), AVG(latency_ms), SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) "
                    "FROM cost_events WHERE ts > ? GROUP BY bot_id", (cutoff,)
                ).fetchall()
            for r in rows:
                result[r[0]] = {
                    "cost_usd": round(r[1] or 0, 4),
                    "input_tokens": r[2] or 0,
                    "output_tokens": r[3] or 0,
                    "requests": r[4] or 0,
                    "avg_latency_ms": round(r[5] or 0, 1),
                    "errors": r[6] or 0,
                }
        except Exception as e:
            logger.debug(f"[CostAnalyzer] 查询失败: {e}")
        return result

    def analyze_by_model(self, hours: float = 24) -> Dict[str, Dict[str, Any]]:
        """按模型维度的成本归因"""
        cutoff = time.time() - hours * 3600
        result: Dict[str, Dict[str, Any]] = {}
        try:
            with sqlite3.connect(self._db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                rows = conn.execute(
                    "SELECT model, SUM(cost_usd), SUM(input_tokens), SUM(output_tokens), "
                    "COUNT(*), AVG(latency_ms) "
                    "FROM cost_events WHERE ts > ? GROUP BY model ORDER BY SUM(cost_usd) DESC",
                    (cutoff,)
                ).fetchall()
            for r in rows:
                result[r[0]] = {
                    "cost_usd": round(r[1] or 0, 4),
                    "input_tokens": r[2] or 0,
                    "output_tokens": r[3] or 0,
                    "requests": r[4] or 0,
                    "avg_latency_ms": round(r[5] or 0, 1),
                }
        except Exception as e:
            logger.debug(f"[CostAnalyzer] 查询失败: {e}")
        return result

    def analyze_by_user(self, hours: float = 24) -> Dict[int, Dict[str, Any]]:
        """按用户维度的成本归因"""
        cutoff = time.time() - hours * 3600
        result: Dict[int, Dict[str, Any]] = {}
        try:
            with sqlite3.connect(self._db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                rows = conn.execute(
                    "SELECT user_id, SUM(cost_usd), COUNT(*), SUM(input_tokens+output_tokens) "
                    "FROM cost_events WHERE ts > ? AND user_id > 0 GROUP BY user_id "
                    "ORDER BY SUM(cost_usd) DESC",
                    (cutoff,)
                ).fetchall()
            for r in rows:
                result[r[0]] = {
                    "cost_usd": round(r[1] or 0, 4),
                    "requests": r[2] or 0,
                    "total_tokens": r[3] or 0,
                }
        except Exception as e:
            logger.debug(f"[CostAnalyzer] 查询失败: {e}")
        return result

    def analyze_by_feature(self, hours: float = 24) -> Dict[str, Dict[str, Any]]:
        """按功能维度的成本归因"""
        cutoff = time.time() - hours * 3600
        result: Dict[str, Dict[str, Any]] = {}
        try:
            with sqlite3.connect(self._db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                rows = conn.execute(
                    "SELECT feature, SUM(cost_usd), COUNT(*), SUM(input_tokens+output_tokens) "
                    "FROM cost_events WHERE ts > ? AND feature != '' GROUP BY feature "
                    "ORDER BY SUM(cost_usd) DESC",
                    (cutoff,)
                ).fetchall()
            for r in rows:
                result[r[0]] = {
                    "cost_usd": round(r[1] or 0, 4),
                    "requests": r[2] or 0,
                    "total_tokens": r[3] or 0,
                }
        except Exception as e:
            logger.debug(f"[CostAnalyzer] 查询失败: {e}")
        return result

    def predict_monthly_cost(self) -> Dict[str, float]:
        """基于最近 7 天数据预测月度成本"""
        week_data = self.analyze_by_bot(hours=168)  # 7 days
        total_week = sum(v["cost_usd"] for v in week_data.values())
        daily_avg = total_week / 7 if total_week > 0 else 0
        return {
            "daily_avg_usd": round(daily_avg, 4),
            "weekly_total_usd": round(total_week, 4),
            "monthly_predicted_usd": round(daily_avg * 30, 2),
        }

    def get_dashboard(self) -> Dict[str, Any]:
        """获取成本看板数据"""
        return {
            "by_bot_24h": self.analyze_by_bot(24),
            "by_model_24h": self.analyze_by_model(24),
            "by_feature_24h": self.analyze_by_feature(24),
            "prediction": self.predict_monthly_cost(),
        }

    def cleanup(self, days: int = 30):
        """清理过期数据"""
        cutoff = time.time() - days * 86400
        try:
            with sqlite3.connect(self._db_path, timeout=10) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("DELETE FROM cost_events WHERE ts < ?", (cutoff,))
                conn.commit()
        except Exception as e:
            logger.debug(f"[CostAnalyzer] 清理失败: {e}")


# 全局实例
cost_analyzer = CostAnalyzer()
