"""
ClawBot 监控 — Prometheus 指标收集器 + HTTP 服务器

对标 LiteLLM: 无外部依赖的轻量级 Prometheus 指标导出。
支持 Counter, Gauge, Histogram 三种指标类型。
"""
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)

# 模块启动时间（用于 /health 端点计算 uptime）
_start_time = time.time()


class PrometheusMetrics:
    """轻量级 Prometheus 指标收集器（无外部依赖）

    对标 LiteLLM 的 Prometheus 集成，提供 /metrics 端点。
    支持 Counter, Gauge, Histogram 三种指标类型。
    """

    def __init__(self):
        self._counters: dict[str, dict[str, float]] = {}   # name -> {labels_key: value}
        self._gauges: dict[str, dict[str, float]] = {}
        self._histograms: dict[str, dict[str, list[float]]] = {}
        self._help: dict[str, str] = {}
        self._type: dict[str, str] = {}
        self._lock = threading.Lock()

    def _labels_key(self, labels: dict[str, str] | None = None) -> str:
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))

    def counter_inc(self, name: str, value: float = 1, labels: dict[str, str] | None = None,
                    help_text: str = ""):
        with self._lock:
            if name not in self._counters:
                self._counters[name] = {}
                self._type[name] = "counter"
                if help_text:
                    self._help[name] = help_text
            key = self._labels_key(labels)
            self._counters[name][key] = self._counters[name].get(key, 0) + value

    def gauge_set(self, name: str, value: float, labels: dict[str, str] | None = None,
                  help_text: str = ""):
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = {}
                self._type[name] = "gauge"
                if help_text:
                    self._help[name] = help_text
            key = self._labels_key(labels)
            self._gauges[name][key] = value

    def histogram_observe(self, name: str, value: float, labels: dict[str, str] | None = None,
                          help_text: str = ""):
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = {}
                self._type[name] = "histogram"
                if help_text:
                    self._help[name] = help_text
            key = self._labels_key(labels)
            if key not in self._histograms[name]:
                self._histograms[name][key] = []
            bucket = self._histograms[name][key]
            bucket.append(value)
            if len(bucket) > 1000:
                self._histograms[name][key] = bucket[-500:]

    def render(self) -> str:
        """渲染 Prometheus text format"""
        lines = []
        with self._lock:
            for name, buckets in self._counters.items():
                if name in self._help:
                    lines.append(f"# HELP {name} {self._help[name]}")
                lines.append(f"# TYPE {name} counter")
                for lk, val in buckets.items():
                    label_str = f"{{{lk}}}" if lk else ""
                    lines.append(f"{name}{label_str} {val}")

            for name, buckets in self._gauges.items():
                if name in self._help:
                    lines.append(f"# HELP {name} {self._help[name]}")
                lines.append(f"# TYPE {name} gauge")
                for lk, val in buckets.items():
                    label_str = f"{{{lk}}}" if lk else ""
                    lines.append(f"{name}{label_str} {val}")

            for name, buckets in self._histograms.items():
                if name in self._help:
                    lines.append(f"# HELP {name} {self._help[name]}")
                lines.append(f"# TYPE {name} histogram")
                for lk, vals in buckets.items():
                    if not vals:
                        continue
                    label_str = f"{{{lk}}}" if lk else ""
                    sorted_v = sorted(vals)
                    count = len(sorted_v)
                    total = sum(sorted_v)
                    p50 = sorted_v[int(count * 0.5)] if count else 0
                    p95 = sorted_v[int(count * 0.95)] if count else 0
                    p99 = sorted_v[min(int(count * 0.99), count - 1)] if count else 0
                    base = f"{{{lk}," if lk else "{"
                    lines.append(f'{name}{base}quantile="0.5"}} {p50}')
                    lines.append(f'{name}{base}quantile="0.95"}} {p95}')
                    lines.append(f'{name}{base}quantile="0.99"}} {p99}')
                    lines.append(f"{name}_sum{label_str} {total}")
                    lines.append(f"{name}_count{label_str} {count}")

        return "\n".join(lines) + "\n"


# 全局 Prometheus 实例
prom = PrometheusMetrics()


class _MetricsHandler(BaseHTTPRequestHandler):
    """Prometheus 指标 HTTP 请求处理器"""

    def _check_auth(self) -> bool:
        """检查 Bearer token 认证（如设置了 METRICS_AUTH_TOKEN 环境变量）"""
        expected = os.environ.get("METRICS_AUTH_TOKEN", "")
        if not expected:
            return True  # 未配置 token，允许访问
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {expected}":
            return True
        self.send_response(403)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error":"forbidden"}')
        return False

    def do_GET(self):
        if not self._check_auth():
            return
        if self.path == "/metrics":
            body = prom.render().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            health = {
                "status": "ok",
                "uptime_seconds": int(time.time() - _start_time),
                "components": {
                    "bot": "running",
                    "api": "running",
                },
            }
            body = json.dumps(health).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # 将 HTTP 请求日志降级为 debug 级别，避免刷屏但仍可通过调高日志级别查看
        logger.debug("[Metrics HTTP] %s", format % args if args else format)


def start_metrics_server(port: int = 9090):
    """启动 Prometheus 指标 HTTP 服务器（后台线程）"""
    server = HTTPServer(("127.0.0.1", port), _MetricsHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"[Prometheus] 指标服务器已启动: http://127.0.0.1:{port}/metrics")
    return server
