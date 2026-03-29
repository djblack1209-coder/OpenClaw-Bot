"""
monitoring.py 单元测试
覆盖 StructuredLogger、CostAnalyzer、HealthChecker 三个核心类

- StructuredLogger: 结构化日志记录 + 统计摘要
- CostAnalyzer: 成本事件记录 + 按维度汇总 (临时 SQLite)
- HealthChecker: Bot 注册 / 连续错误判定 / 成功恢复
"""
import os
import sqlite3
import tempfile
import shutil
from datetime import datetime
from unittest.mock import patch

import pytest

# 固定时间点，避免测试结果受真实时间影响
FIXED_NOW = datetime(2026, 3, 27, 12, 0, 0)


@pytest.fixture
def tmp_dir():
    """每个测试用例使用独立的临时目录，测试结束后自动清理"""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ════════════════════════════════════════════
#  StructuredLogger 测试
# ════════════════════════════════════════════

class TestStructuredLogger:

    @patch("src.monitoring.logger.now_et", return_value=FIXED_NOW)
    def test_structured_logger_log(self, mock_now, tmp_dir):
        """记录一条消息后，total_messages 计数器应加 1"""
        from src.monitoring import StructuredLogger

        sl = StructuredLogger("test", log_dir=tmp_dir)
        sl.log_message(bot_id="bot1", chat_id=100, user_id=200, text_length=42)

        # 验证内部统计
        assert sl._stats["total_messages"] == 1
        # 验证当日消息也被记录
        assert sl._stats["daily_messages"].get("2026-03-27") == 1

    @patch("src.monitoring.logger.now_et", return_value=FIXED_NOW)
    def test_structured_logger_get_summary(self, mock_now, tmp_dir):
        """记录多条消息和 API 调用后，get_stats 返回正确的汇总数据"""
        from src.monitoring import StructuredLogger

        sl = StructuredLogger("test", log_dir=tmp_dir)

        # 记录 3 条消息
        for _ in range(3):
            sl.log_message("bot1", 100, 200, 50)

        # 记录 2 次 API 调用（1 成功 1 失败）
        sl.log_api_call("bot1", "gpt-4", latency_ms=100.0, success=True)
        sl.log_api_call("bot1", "gpt-4", latency_ms=200.0, success=False, error="timeout")

        stats = sl.get_stats()

        assert stats["total_messages"] == 3
        assert stats["total_api_calls"] == 2
        assert stats["total_errors"] == 1
        # 平均延迟 = (100 + 200) / 2 = 150
        assert stats["avg_latency_ms"] == 150.0
        # 模型使用次数
        assert stats["model_usage"]["gpt-4"] == 2
        # 错误率 = 1/2 * 100 = 50.0%
        assert stats["error_rate"] == 50.0


# ════════════════════════════════════════════
#  CostAnalyzer 测试
# ════════════════════════════════════════════

class TestCostAnalyzer:

    def test_cost_analyzer_record(self, tmp_dir):
        """记录一条成本事件后，能在 SQLite 数据库中查到对应行"""
        from src.monitoring import CostAnalyzer

        db_path = os.path.join(tmp_dir, "cost.db")
        ca = CostAnalyzer(db_path=db_path)

        ca.record(
            bot_id="bot1", model="gpt-4",
            input_tokens=100, output_tokens=50,
            cost_usd=0.005, latency_ms=120.0,
        )

        # 直接查数据库验证写入
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT bot_id, model, input_tokens, output_tokens, cost_usd "
            "FROM cost_events"
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "bot1"
        assert row[1] == "gpt-4"
        assert row[2] == 100
        assert row[3] == 50
        assert abs(row[4] - 0.005) < 1e-9

    def test_cost_analyzer_get_daily_total(self, tmp_dir):
        """记录多条事件后，analyze_by_bot 返回正确的 24 小时汇总"""
        from src.monitoring import CostAnalyzer

        db_path = os.path.join(tmp_dir, "cost.db")
        ca = CostAnalyzer(db_path=db_path)

        # 两条 bot1、一条 bot2
        ca.record(bot_id="bot1", model="gpt-4", cost_usd=0.01)
        ca.record(bot_id="bot1", model="gpt-4", cost_usd=0.02)
        ca.record(bot_id="bot2", model="claude", cost_usd=0.05)

        result = ca.analyze_by_bot(hours=24)

        # bot1: 2 次请求，合计 0.03
        assert "bot1" in result
        assert result["bot1"]["requests"] == 2
        assert abs(result["bot1"]["cost_usd"] - 0.03) < 1e-4

        # bot2: 1 次请求，合计 0.05
        assert "bot2" in result
        assert result["bot2"]["requests"] == 1
        assert abs(result["bot2"]["cost_usd"] - 0.05) < 1e-4


# ════════════════════════════════════════════
#  HealthChecker 测试
# ════════════════════════════════════════════

class TestHealthChecker:

    def test_health_checker_register(self):
        """注册 Bot 后，状态中应包含该 Bot 且默认健康"""
        from src.monitoring import HealthChecker

        hc = HealthChecker()
        hc.register_bot("bot1")

        status = hc.get_status()
        assert "bot1" in status
        assert status["bot1"]["healthy"] is True
        assert status["bot1"]["consecutive_errors"] == 0
        assert status["bot1"]["restart_count"] == 0

    def test_health_checker_record_error(self):
        """连续 5 次错误后，Bot 状态变为不健康"""
        from src.monitoring import HealthChecker

        hc = HealthChecker()
        hc.register_bot("bot1")

        # 连续记录 5 次错误
        for i in range(5):
            hc.record_error("bot1", f"connection_error_{i}")

        status = hc.get_status()
        assert status["bot1"]["healthy"] is False
        assert status["bot1"]["consecutive_errors"] == 5
        assert status["bot1"]["last_error"] == "connection_error_4"

    def test_health_checker_record_success(self):
        """不健康的 Bot 在 record_success 后恢复健康"""
        from src.monitoring import HealthChecker

        hc = HealthChecker()
        hc.register_bot("bot1")

        # 先制造不健康状态（连续 5 次错误）
        for i in range(5):
            hc.record_error("bot1", f"error_{i}")
        assert hc.get_status()["bot1"]["healthy"] is False

        # 调用 record_success 恢复
        hc.record_success("bot1")

        status = hc.get_status()
        assert status["bot1"]["healthy"] is True
        assert status["bot1"]["consecutive_errors"] == 0
