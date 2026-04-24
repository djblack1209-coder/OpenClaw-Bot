"""
ClawBot 监控 — 异常检测器

对标 Datadog APM 的异常检测：延迟尖峰、错误率突增、成本异常、流量异常。
"""
import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """异常检测器（对标 Datadog APM 的异常检测）

    功能：
    - 延迟尖峰检测（Z-score）
    - 错误率突增检测
    - 成本异常检测
    - 流量异常检测
    """

    def __init__(self, window_size: int = 100):
        self._window_size = window_size
        self._latency_window = deque(maxlen=window_size)
        self._error_window = deque(maxlen=window_size)
        self._cost_window = deque(maxlen=window_size)
        self._request_timestamps = deque(maxlen=window_size * 2)
        self._lock = threading.Lock()
        # 告警状态
        self._alerts: list[dict[str, Any]] = []
        self._max_alerts = 200

    def record_request(self, latency_ms: float, success: bool, cost_usd: float = 0.0):
        """记录一次请求的指标"""
        now = time.time()
        with self._lock:
            self._latency_window.append(latency_ms)
            self._error_window.append(not success)
            self._cost_window.append(cost_usd)
            self._request_timestamps.append(now)

    def _z_score(self, values: list[float], current: float) -> float:
        """计算 Z-score"""
        if len(values) < 10:
            return 0.0
        import math
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 0.001
        return (current - mean) / std

    def detect_latency_spike(self, threshold_z: float = 2.5) -> dict[str, Any] | None:
        """检测延迟尖峰（Z-score > threshold）"""
        with self._lock:
            if len(self._latency_window) < 20:
                return None
            current = self._latency_window[-1]
            # 用前 N-1 个值计算基线
            baseline = list(self._latency_window)[:-1]
        z = self._z_score(baseline, current)
        if z > threshold_z:
            alert = {
                "type": "latency_spike",
                "severity": "warning" if z < 4.0 else "critical",
                "z_score": round(z, 2),
                "current_ms": round(current, 1),
                "baseline_avg_ms": round(sum(baseline) / len(baseline), 1),
                "ts": time.time(),
            }
            self._add_alert(alert)
            return alert
        return None

    def detect_error_rate_spike(self, threshold: float = 0.3) -> dict[str, Any] | None:
        """检测错误率突增（最近窗口错误率 > threshold）"""
        with self._lock:
            if len(self._error_window) < 10:
                return None
            error_list = list(self._error_window)
            recent = error_list[-20:]  # 最近 20 次
            older = error_list[:-20] if len(error_list) > 20 else []

        recent_rate = sum(1 for e in recent if e) / len(recent)
        older_rate = (sum(1 for e in older if e) / len(older)) if older else 0.05

        if recent_rate > threshold and recent_rate > older_rate * 2:
            alert = {
                "type": "error_rate_spike",
                "severity": "warning" if recent_rate < 0.5 else "critical",
                "current_rate": round(recent_rate, 3),
                "baseline_rate": round(older_rate, 3),
                "ts": time.time(),
            }
            self._add_alert(alert)
            return alert
        return None

    def detect_cost_anomaly(self, threshold_z: float = 3.0) -> dict[str, Any] | None:
        """检测成本异常（单次请求成本 Z-score 过高）"""
        with self._lock:
            if len(self._cost_window) < 20:
                return None
            current = self._cost_window[-1]
            baseline = list(self._cost_window)[:-1]

        if current <= 0:
            return None
        z = self._z_score(baseline, current)
        if z > threshold_z:
            alert = {
                "type": "cost_anomaly",
                "severity": "warning" if z < 5.0 else "critical",
                "z_score": round(z, 2),
                "current_usd": round(current, 4),
                "baseline_avg_usd": round(sum(baseline) / len(baseline), 4),
                "ts": time.time(),
            }
            self._add_alert(alert)
            return alert
        return None

    def detect_traffic_anomaly(self) -> dict[str, Any] | None:
        """检测流量异常（QPS 突增或骤降）"""
        with self._lock:
            ts = list(self._request_timestamps)
        if len(ts) < 20:
            return None
        now = time.time()
        # 最近 60 秒 QPS
        recent_count = sum(1 for t in ts if now - t < 60)
        # 前 5 分钟平均 QPS
        older_count = sum(1 for t in ts if 60 < now - t < 360)
        older_minutes = min(5, (now - ts[0]) / 60) if ts else 1
        baseline_qpm = older_count / max(older_minutes, 0.1)
        current_qpm = recent_count  # 最近 1 分钟

        if baseline_qpm > 0 and current_qpm > baseline_qpm * 3:
            alert = {
                "type": "traffic_spike",
                "severity": "warning",
                "current_qpm": current_qpm,
                "baseline_qpm": round(baseline_qpm, 1),
                "ts": now,
            }
            self._add_alert(alert)
            return alert
        return None

    def check_all(self) -> list[dict[str, Any]]:
        """运行所有异常检测"""
        alerts = []
        for detect_fn in [
            self.detect_latency_spike,
            self.detect_error_rate_spike,
            self.detect_cost_anomaly,
            self.detect_traffic_anomaly,
        ]:
            try:
                result = detect_fn()
                if result:
                    alerts.append(result)
            except Exception as e:
                logger.debug(f"[AnomalyDetector] 检测失败: {e}")
        return alerts

    def _add_alert(self, alert: dict[str, Any]):
        with self._lock:
            self._alerts.append(alert)
            if len(self._alerts) > self._max_alerts:
                self._alerts = self._alerts[-self._max_alerts:]

    def get_recent_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._alerts[-limit:])

    def get_health_summary(self) -> dict[str, Any]:
        """获取健康摘要"""
        with self._lock:
            lat = list(self._latency_window)
            err = list(self._error_window)
            cost = list(self._cost_window)
        avg_lat = sum(lat) / len(lat) if lat else 0
        p95_lat = sorted(lat)[int(len(lat) * 0.95)] if len(lat) > 5 else 0
        err_rate = sum(1 for e in err if e) / len(err) if err else 0
        total_cost = sum(cost)
        return {
            "avg_latency_ms": round(avg_lat, 1),
            "p95_latency_ms": round(p95_lat, 1),
            "error_rate": round(err_rate, 3),
            "total_cost_usd": round(total_cost, 4),
            "sample_size": len(lat),
            "recent_alerts": len(self._alerts),
        }


# 全局实例
anomaly_detector = AnomalyDetector()
