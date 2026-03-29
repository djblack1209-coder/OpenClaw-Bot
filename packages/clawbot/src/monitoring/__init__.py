"""
ClawBot 监控包 — 结构化日志 + 健康检查 + 自动恢复 + Prometheus 指标 v2.0

本包由原始 monitoring.py (1294行) 拆分而来，保持所有公开 API 不变。
所有外部 import 路径 (from src.monitoring import X) 无需修改。
"""

# === Prometheus 指标 ===
from src.monitoring.metrics import (
    PrometheusMetrics,
    prom,
    start_metrics_server,
    _start_time,
)

# === 告警规则引擎 ===
from src.monitoring.alerts import AlertRule, AlertManager

# === 结构化日志 + 任务可观测性 ===
from src.monitoring.logger import StructuredLogger, TaskObserver, task_observer

# === 健康检查 + 自动恢复 ===
from src.monitoring.health import HealthChecker, AutoRecovery

# === 成本归因分析 ===
from src.monitoring.cost_analyzer import CostAnalyzer, cost_analyzer

# === 异常检测 ===
from src.monitoring.anomaly_detector import AnomalyDetector, anomaly_detector

# === 监控增强 (代理到 monitoring_extras) ===

def get_system_resources():
    """获取系统资源 — 代理到 monitoring_extras"""
    try:
        from src.monitoring_extras import get_system_resources as _get
        return _get()
    except ImportError:
        return {"cpu_load_1m": -1, "memory_percent": -1, "disk_used_percent": -1}


async def check_g4f_health(**kwargs):
    """检查 g4f 服务健康 — 代理到 monitoring_extras"""
    try:
        from src.monitoring_extras import check_g4f_health as _check
        return await _check(**kwargs)
    except ImportError:
        return {"alive": False, "error": "monitoring_extras 不可用"}


# 导入 now_et 使得 @patch("src.monitoring.now_et") 在测试中仍然生效
from src.utils import now_et

__all__ = [
    # 指标
    "PrometheusMetrics", "prom", "start_metrics_server", "_start_time",
    # 告警
    "AlertRule", "AlertManager",
    # 日志
    "StructuredLogger", "TaskObserver", "task_observer",
    # 健康
    "HealthChecker", "AutoRecovery",
    # 成本
    "CostAnalyzer", "cost_analyzer",
    # 异常检测
    "AnomalyDetector", "anomaly_detector",
    # 辅助
    "get_system_resources", "check_g4f_health", "now_et",
]
