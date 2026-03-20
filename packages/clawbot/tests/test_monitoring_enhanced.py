"""测试 monitoring.py 增强功能"""
import pytest
import time
import tempfile
import os
from src.monitoring import CostAnalyzer, AnomalyDetector


def test_cost_analyzer():
    """测试成本归因分析器"""
    # 使用临时 DB 避免全局状态污染
    tmp = tempfile.mktemp(suffix=".db")
    try:
        analyzer = CostAnalyzer(db_path=tmp)
        
        # 记录几次调用
        analyzer.record("bot1", "gpt-4", 100, 50, 0.01, 500, True, 123, "chat")
        analyzer.record("bot1", "gpt-4", 200, 100, 0.02, 600, True, 123, "chat")
        analyzer.record("bot2", "claude", 150, 75, 0.015, 700, True, 456, "analysis")
        
        # 按 bot 分析
        by_bot = analyzer.analyze_by_bot(hours=24)
        assert "bot1" in by_bot
        assert by_bot["bot1"]["cost_usd"] > 0
        assert by_bot["bot1"]["requests"] == 2
        
        # 按模型分析
        by_model = analyzer.analyze_by_model(hours=24)
        assert "gpt-4" in by_model
        
        # 按用户分析
        by_user = analyzer.analyze_by_user(hours=24)
        assert 123 in by_user or 456 in by_user
        
        # 月度预测
        prediction = analyzer.predict_monthly_cost()
        assert "monthly_predicted_usd" in prediction
        
        # 看板
        dashboard = analyzer.get_dashboard()
        assert "by_bot_24h" in dashboard
        assert "prediction" in dashboard
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def test_anomaly_detector():
    """测试异常检测器"""
    detector = AnomalyDetector(window_size=50)
    
    # 正常请求（需要至少20个基线数据）
    for _ in range(25):
        detector.record_request(500, True, 0.01)
    
    # 延迟尖峰
    detector.record_request(3000, True, 0.01)
    spike = detector.detect_latency_spike(threshold_z=2.0)
    assert spike is not None
    assert spike["type"] == "latency_spike"
    
    # 错误率突增
    detector2 = AnomalyDetector(window_size=20)
    for _ in range(10):
        detector2.record_request(500, True)
    for _ in range(8):
        detector2.record_request(500, False)
    
    error_spike = detector2.detect_error_rate_spike(threshold=0.3)
    assert error_spike is not None
    
    # 健康摘要
    summary = detector.get_health_summary()
    assert "avg_latency_ms" in summary
    assert "error_rate" in summary
    
    # 检查所有异常
    alerts = detector.check_all()
    assert isinstance(alerts, list)
