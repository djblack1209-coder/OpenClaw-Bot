"""
ClawBot - 结构化日志 + 健康检查 + 自动恢复 + Prometheus 指标 v2.0
对标 LiteLLM: Prometheus 指标导出 + 结构化 JSON 日志 + 告警规则
"""
import os
import time
import json
import asyncio
import logging
import sqlite3
from collections import deque
from typing import Dict, Any, Optional, List, Callable
from datetime import timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from src.utils import now_et

logger = logging.getLogger(__name__)

# 模块启动时间（用于 /health 端点计算 uptime）
_start_time = time.time()


# ============ 对标 LiteLLM: Prometheus 指标收集器 ============

class PrometheusMetrics:
    """轻量级 Prometheus 指标收集器（无外部依赖）
    
    对标 LiteLLM 的 Prometheus 集成，提供 /metrics 端点。
    支持 Counter, Gauge, Histogram 三种指标类型。
    """

    def __init__(self):
        self._counters: Dict[str, Dict[str, float]] = {}   # name -> {labels_key: value}
        self._gauges: Dict[str, Dict[str, float]] = {}
        self._histograms: Dict[str, Dict[str, List[float]]] = {}
        self._help: Dict[str, str] = {}
        self._type: Dict[str, str] = {}
        self._lock = threading.Lock()

    def _labels_key(self, labels: Optional[Dict[str, str]] = None) -> str:
        if not labels:
            return ""
        return ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))

    def counter_inc(self, name: str, value: float = 1, labels: Optional[Dict[str, str]] = None,
                    help_text: str = ""):
        with self._lock:
            if name not in self._counters:
                self._counters[name] = {}
                self._type[name] = "counter"
                if help_text:
                    self._help[name] = help_text
            key = self._labels_key(labels)
            self._counters[name][key] = self._counters[name].get(key, 0) + value

    def gauge_set(self, name: str, value: float, labels: Optional[Dict[str, str]] = None,
                  help_text: str = ""):
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = {}
                self._type[name] = "gauge"
                if help_text:
                    self._help[name] = help_text
            key = self._labels_key(labels)
            self._gauges[name][key] = value

    def histogram_observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None,
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
    def _check_auth(self) -> bool:
        """Check bearer token auth if METRICS_AUTH_TOKEN is set."""
        expected = os.environ.get("METRICS_AUTH_TOKEN", "")
        if not expected:
            return True  # no token configured, allow access
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


# ============ 对标 LiteLLM: 告警规则引擎 ============

class AlertRule:
    """告警规则"""
    def __init__(self, name: str, condition_fn: Callable[[], bool],
                 message_fn: Callable[[], str], cooldown: float = 300):
        self.name = name
        self.condition_fn = condition_fn
        self.message_fn = message_fn
        self.cooldown = cooldown
        self.last_fired = 0.0

    def check(self) -> Optional[str]:
        now = time.time()
        if now - self.last_fired < self.cooldown:
            return None
        try:
            if self.condition_fn():
                self.last_fired = now
                return self.message_fn()
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)
        return None


class AlertManager:
    """告警管理器"""
    def __init__(self):
        self.rules: List[AlertRule] = []
        self._callbacks: List[Callable[[str, str], None]] = []

    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)

    def on_alert(self, callback: Callable[[str, str], None]):
        """注册告警回调 (rule_name, message)"""
        self._callbacks.append(callback)

    def check_all(self) -> List[str]:
        fired = []
        for rule in self.rules:
            msg = rule.check()
            if msg:
                fired.append(msg)
                for cb in self._callbacks:
                    try:
                        cb(rule.name, msg)
                    except Exception as e:
                        logger.debug(f"[Alert] 回调失败: {e}")
        return fired


# ============ 结构化日志 ============

class StructuredLogger:
    """结构化日志记录器 + Prometheus 指标集成（对标 LiteLLM）"""

    def __init__(self, name: str, log_dir: Optional[str] = None):
        self.name = name
        self._stats: Dict[str, Any] = {
            "start_time": time.time(),
            "total_messages": 0,
            "total_api_calls": 0,
            "total_errors": 0,
            "model_usage": {},       # model -> count
            "daily_messages": {},    # date -> count
            "api_latencies": [],     # 最近100次延迟
        }
        self._max_latencies = 100

        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path(__file__).parent.parent / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self._metrics_path = self.log_dir / "metrics.json"
        self._jsonl_path = self.log_dir / "events.jsonl"
        self._max_jsonl_bytes = 50 * 1024 * 1024  # 50MB 触发轮转
        self._max_jsonl_backups = 3
        self._load_metrics()

        # 对标 LiteLLM: 注册 Prometheus 指标
        prom.counter_inc("clawbot_messages_total", 0,
                         help_text="Total messages received")
        prom.counter_inc("clawbot_api_calls_total", 0,
                         help_text="Total LLM API calls")
        prom.counter_inc("clawbot_errors_total", 0,
                         help_text="Total errors")

    def _load_metrics(self):
        """加载持久化的指标"""
        if self._metrics_path.exists():
            try:
                with open(self._metrics_path, 'r') as f:
                    saved = json.load(f)
                self._stats["total_messages"] = saved.get("total_messages", 0)
                self._stats["total_api_calls"] = saved.get("total_api_calls", 0)
                self._stats["total_errors"] = saved.get("total_errors", 0)
                self._stats["model_usage"] = saved.get("model_usage", {})
                self._stats["daily_messages"] = saved.get("daily_messages", {})
            except Exception as e:
                logger.warning("[Metrics] 加载指标文件失败: %s", e)

    def _save_metrics(self):
        """持久化指标"""
        try:
            data = {
                "total_messages": self._stats["total_messages"],
                "total_api_calls": self._stats["total_api_calls"],
                "total_errors": self._stats["total_errors"],
                "model_usage": self._stats["model_usage"],
                "daily_messages": self._stats["daily_messages"],
                "last_saved": now_et().isoformat(),
            }
            with open(self._metrics_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"保存指标失败: {e}")

    def log_message(self, bot_id: str, chat_id: int, user_id: int, text_length: int):
        """记录收到的消息 + Prometheus 指标"""
        self._stats["total_messages"] += 1
        today = now_et().strftime("%Y-%m-%d")
        self._stats["daily_messages"][today] = self._stats["daily_messages"].get(today, 0) + 1

        # 对标 LiteLLM: Prometheus counter
        prom.counter_inc("clawbot_messages_total", 1, {"bot_id": bot_id})
        prom.gauge_set("clawbot_messages_today", self._stats["daily_messages"][today])

        # 对标 LiteLLM: 结构化 JSON 日志
        self._emit_jsonl({
            "event": "message", "bot_id": bot_id, "chat_id": chat_id,
            "user_id": user_id, "text_length": text_length,
        })

        logger.info(
            f"[MSG] bot={bot_id} chat={chat_id} user={user_id} len={text_length}"
        )

        if self._stats["total_messages"] % 50 == 0:
            self._save_metrics()

    def log_api_call(
        self,
        bot_id: str,
        model: str,
        latency_ms: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        success: bool = True,
        error: Optional[str] = None,
        provider: str = "",
        cost_usd: float = 0.0,
    ):
        """记录 API 调用 + Prometheus 指标（对标 LiteLLM）"""
        self._stats["total_api_calls"] += 1
        self._stats["model_usage"][model] = self._stats["model_usage"].get(model, 0) + 1

        latencies = self._stats["api_latencies"]
        latencies.append(latency_ms)
        if len(latencies) > self._max_latencies:
            self._stats["api_latencies"] = latencies[-self._max_latencies:]

        if not success:
            self._stats["total_errors"] += 1

        # 对标 LiteLLM: Prometheus 指标
        labels = {"bot_id": bot_id, "model": model}
        if provider:
            labels["provider"] = provider
        prom.counter_inc("clawbot_api_calls_total", 1, labels)
        prom.histogram_observe("clawbot_api_latency_ms", latency_ms, labels,
                               help_text="LLM API call latency in milliseconds")
        if input_tokens > 0:
            prom.counter_inc("clawbot_input_tokens_total", input_tokens, labels,
                             help_text="Total input tokens consumed")
        if output_tokens > 0:
            prom.counter_inc("clawbot_output_tokens_total", output_tokens, labels,
                             help_text="Total output tokens generated")
        if cost_usd > 0:
            prom.counter_inc("clawbot_cost_usd_total", cost_usd, labels,
                             help_text="Total cost in USD")
        if not success:
            prom.counter_inc("clawbot_errors_total", 1, labels)

        # 对标 LiteLLM: 结构化 JSON 日志
        self._emit_jsonl({
            "event": "api_call", "bot_id": bot_id, "model": model,
            "provider": provider, "latency_ms": round(latency_ms, 1),
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_usd": cost_usd, "success": success, "error": error,
        })

        level = logging.INFO if success else logging.WARNING
        logger.log(
            level,
            f"[API] bot={bot_id} model={model} "
            f"latency={latency_ms:.0f}ms tokens={input_tokens}+{output_tokens} "
            f"{'OK' if success else f'FAIL: {error}'}"
        )

    def log_error(self, bot_id: str, error_type: str, error_msg: str):
        """记录错误 + Prometheus 指标"""
        self._stats["total_errors"] += 1
        prom.counter_inc("clawbot_errors_total", 1,
                         {"bot_id": bot_id, "error_type": error_type})
        self._emit_jsonl({
            "event": "error", "bot_id": bot_id,
            "error_type": error_type, "error_msg": error_msg,
        })
        logger.error(f"[ERR] bot={bot_id} type={error_type} msg={error_msg}")

    def _emit_jsonl(self, data: Dict[str, Any]):
        """写入结构化 JSONL 日志 + 自动轮转（对标 logrotate）"""
        data["ts"] = now_et().isoformat()
        try:
            self._rotate_jsonl(self._jsonl_path, self._max_jsonl_bytes, self._max_jsonl_backups)
            with open(self._jsonl_path, "a") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[Metrics] JSONL 写入失败 ({self._jsonl_path}): {e}")

    @staticmethod
    def _rotate_jsonl(path: Path, max_bytes: int, max_backups: int):
        """JSONL 日志轮转 — 参考 Python logging.handlers.RotatingFileHandler"""
        if not path.exists():
            return
        try:
            if path.stat().st_size < max_bytes:
                return
        except OSError as e:  # noqa: F841
            return
        # 轮转: events.jsonl.3 删除, .2 → .3, .1 → .2, events.jsonl → .1
        for i in range(max_backups, 0, -1):
            src = path.with_suffix(f".jsonl.{i}")
            dst = path.with_suffix(f".jsonl.{i + 1}")
            if i == max_backups and src.exists():
                src.unlink()
            elif src.exists():
                src.rename(dst)
        path.rename(path.with_suffix(".jsonl.1"))

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = time.time() - self._stats["start_time"]
        latencies = self._stats["api_latencies"]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        today = now_et().strftime("%Y-%m-%d")
        today_messages = self._stats["daily_messages"].get(today, 0)

        return {
            "uptime_hours": round(uptime / 3600, 1),
            "total_messages": self._stats["total_messages"],
            "today_messages": today_messages,
            "total_api_calls": self._stats["total_api_calls"],
            "total_errors": self._stats["total_errors"],
            "error_rate": round(
                self._stats["total_errors"] / max(self._stats["total_api_calls"], 1) * 100, 1
            ),
            "avg_latency_ms": round(avg_latency, 0),
            "model_usage": self._stats["model_usage"],
        }

    def shutdown(self):
        """关闭时保存"""
        self._save_metrics()


# ============ 任务可观测性 ============

class TaskObserver:
    """任务级可观测性：质量评估、成本分析、检索评估。
    
    每个"任务"是一个完整的用户请求处理周期，可能包含多次 API 调用。
    跟踪每个任务的总成本、总延迟、输出质量评分、检索命中率。
    """

    def __init__(self, log_dir: Optional[str] = None):
        if log_dir:
            self._log_dir = Path(log_dir)
        else:
            self._log_dir = Path(__file__).parent.parent / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._task_log_path = self._log_dir / "task-observations.jsonl"
        self._active_tasks: Dict[str, Dict[str, Any]] = {}

    def start_task(self, task_id: str, task_type: str, bot_id: str = "",
                   chat_id: int = 0, prompt_preview: str = ""):
        """开始跟踪一个任务"""
        self._active_tasks[task_id] = {
            "task_id": task_id,
            "task_type": task_type,
            "bot_id": bot_id,
            "chat_id": chat_id,
            "prompt_preview": prompt_preview[:200],
            "started_at": time.time(),
            "api_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "total_latency_ms": 0.0,
            "retrieval_queries": 0,
            "retrieval_hits": 0,
            "errors": [],
        }

    def record_api_call(self, task_id: str, model: str = "", latency_ms: float = 0,
                        input_tokens: int = 0, output_tokens: int = 0,
                        cost_usd: float = 0.0, success: bool = True, error: str = ""):
        """记录任务中的一次 API 调用"""
        task = self._active_tasks.get(task_id)
        if not task:
            return
        task["api_calls"] += 1
        task["total_input_tokens"] += input_tokens
        task["total_output_tokens"] += output_tokens
        task["total_cost_usd"] += cost_usd
        task["total_latency_ms"] += latency_ms
        if not success and error:
            task["errors"].append(error)

    def record_retrieval(self, task_id: str, query: str = "", hit: bool = False,
                         score: float = 0.0):
        """记录任务中的一次检索（记忆/RAG）"""
        task = self._active_tasks.get(task_id)
        if not task:
            return
        task["retrieval_queries"] += 1
        if hit:
            task["retrieval_hits"] += 1

    def end_task(self, task_id: str, quality_score: int = 0,
                 output_length: int = 0, user_feedback: str = ""):
        """结束任务并写入日志
        
        Args:
            quality_score: 输出质量评分 1-5（0=未评估）
            output_length: 输出字符数
            user_feedback: 用户反馈（positive/negative/none）
        """
        task = self._active_tasks.pop(task_id, None)
        if not task:
            return

        elapsed_ms = (time.time() - task["started_at"]) * 1000
        retrieval_hit_rate = (
            task["retrieval_hits"] / task["retrieval_queries"]
            if task["retrieval_queries"] > 0 else 0.0
        )

        record = {
            "ts": now_et().isoformat(),
            "task_id": task["task_id"],
            "task_type": task["task_type"],
            "bot_id": task["bot_id"],
            "chat_id": task["chat_id"],
            "prompt_preview": task["prompt_preview"],
            "elapsed_ms": round(elapsed_ms, 1),
            "api_calls": task["api_calls"],
            "total_input_tokens": task["total_input_tokens"],
            "total_output_tokens": task["total_output_tokens"],
            "total_cost_usd": round(task["total_cost_usd"], 6),
            "total_latency_ms": round(task["total_latency_ms"], 1),
            "retrieval_queries": task["retrieval_queries"],
            "retrieval_hits": task["retrieval_hits"],
            "retrieval_hit_rate": round(retrieval_hit_rate, 3),
            "quality_score": quality_score,
            "output_length": output_length,
            "user_feedback": user_feedback,
            "errors": task["errors"],
        }

        # Prometheus 指标
        labels = {"task_type": task["task_type"], "bot_id": task["bot_id"]}
        prom.counter_inc("clawbot_tasks_total", 1, labels,
                         help_text="Total tasks completed")
        prom.histogram_observe("clawbot_task_elapsed_ms", elapsed_ms, labels,
                               help_text="Task total elapsed time in ms")
        if task["total_cost_usd"] > 0:
            prom.counter_inc("clawbot_task_cost_usd", task["total_cost_usd"], labels,
                             help_text="Total task cost in USD")
        if quality_score > 0:
            prom.histogram_observe("clawbot_task_quality", float(quality_score), labels,
                                   help_text="Task output quality score 1-5")
        if task["retrieval_queries"] > 0:
            prom.gauge_set("clawbot_retrieval_hit_rate", retrieval_hit_rate, labels,
                           help_text="Memory retrieval hit rate")

        # JSONL 日志（带轮转）
        try:
            StructuredLogger._rotate_jsonl(self._task_log_path, 50 * 1024 * 1024, 3)
            with open(self._task_log_path, "a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[TaskObserver] JSONL 写入失败: {e}")

        return record

    def get_summary(self, days: int = 7) -> Dict[str, Any]:
        """获取近 N 天的任务可观测性摘要"""
        cutoff = now_et() - timedelta(days=days)
        cutoff_iso = cutoff.isoformat()

        by_type: Dict[str, Dict[str, Any]] = {}
        total_tasks = 0
        total_cost = 0.0
        quality_scores = []

        if not self._task_log_path.exists():
            return {"total_tasks": 0, "message": "No task observations yet"}

        try:
            with open(self._task_log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError as e:  # noqa: F841
                        continue
                    if rec.get("ts", "") < cutoff_iso:
                        continue

                    total_tasks += 1
                    total_cost += rec.get("total_cost_usd", 0)
                    qs = rec.get("quality_score", 0)
                    if qs > 0:
                        quality_scores.append(qs)

                    tt = rec.get("task_type", "unknown")
                    if tt not in by_type:
                        by_type[tt] = {"count": 0, "cost": 0.0, "avg_latency": 0.0,
                                       "total_latency": 0.0, "quality_scores": []}
                    entry = by_type[tt]
                    entry["count"] += 1
                    entry["cost"] += rec.get("total_cost_usd", 0)
                    entry["total_latency"] += rec.get("total_latency_ms", 0)
                    if qs > 0:
                        entry["quality_scores"].append(qs)
        except Exception as e:
            logger.debug("Silenced exception", exc_info=True)

        # 计算平均值
        for tt, entry in by_type.items():
            entry["avg_latency"] = round(entry["total_latency"] / max(entry["count"], 1), 1)
            entry["avg_quality"] = (
                round(sum(entry["quality_scores"]) / len(entry["quality_scores"]), 2)
                if entry["quality_scores"] else 0
            )
            entry["cost"] = round(entry["cost"], 6)
            del entry["total_latency"]
            del entry["quality_scores"]

        return {
            "period_days": days,
            "total_tasks": total_tasks,
            "total_cost_usd": round(total_cost, 6),
            "avg_quality": (
                round(sum(quality_scores) / len(quality_scores), 2)
                if quality_scores else 0
            ),
            "by_task_type": by_type,
        }


# 全局 TaskObserver 实例
task_observer = TaskObserver()


# ============ 健康检查 ============

class HealthChecker:
    """Bot 健康检查器"""

    def __init__(self):
        self._bot_status: Dict[str, Dict[str, Any]] = {}
        self._callbacks: List[Callable] = []

    def register_bot(self, bot_id: str):
        """注册 bot"""
        self._bot_status[bot_id] = {
            "healthy": True,
            "last_heartbeat": time.time(),
            "consecutive_errors": 0,
            "last_error": None,
            "restart_count": 0,
        }

    def heartbeat(self, bot_id: str):
        """心跳"""
        if bot_id in self._bot_status:
            self._bot_status[bot_id]["last_heartbeat"] = time.time()
            self._bot_status[bot_id]["healthy"] = True

    def record_error(self, bot_id: str, error: str):
        """记录错误"""
        if bot_id not in self._bot_status:
            return
        status = self._bot_status[bot_id]
        status["consecutive_errors"] += 1
        status["last_error"] = error
        if status["consecutive_errors"] >= 5:
            status["healthy"] = False
            # EventBus: Bot 健康状态变更为不健康
            try:
                from src.core.event_bus import get_event_bus
                bus = get_event_bus()
                if bus:
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        _t = loop.create_task(bus.publish("system.bot_health", {
                            "bot_id": bot_id, "healthy": False,
                            "consecutive_errors": status["consecutive_errors"],
                            "last_error": error,
                        }))
                        _t.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
                    except RuntimeError as e:  # noqa: F841
                        pass
            except Exception as e:
                pass
                logger.debug("静默异常: %s", e)

    def record_success(self, bot_id: str):
        """记录成功"""
        if bot_id in self._bot_status:
            self._bot_status[bot_id]["consecutive_errors"] = 0
            self._bot_status[bot_id]["healthy"] = True

    def on_unhealthy(self, callback: Callable):
        """注册不健康回调"""
        self._callbacks.append(callback)

    def check_all(self) -> Dict[str, bool]:
        """检查所有 bot 健康状态"""
        now = time.time()
        results = {}
        for bot_id, status in self._bot_status.items():
            # 超过5分钟没有心跳视为不健康
            if now - status["last_heartbeat"] > 300:
                status["healthy"] = False
            results[bot_id] = status["healthy"]

            if not status["healthy"]:
                for cb in self._callbacks:
                    try:
                        cb(bot_id, status)
                    except Exception as e:
                        logger.debug("[HealthChecker] 回调执行失败: %s", e)
        return results

    def get_status(self) -> Dict[str, Any]:
        return {
            bot_id: {
                "healthy": s["healthy"],
                "last_heartbeat_ago": round(time.time() - s["last_heartbeat"], 0),
                "consecutive_errors": s["consecutive_errors"],
                "last_error": s["last_error"],
                "restart_count": s["restart_count"],
            }
            for bot_id, s in self._bot_status.items()
        }


# ============ 自动恢复 ============

class AutoRecovery:
    """Bot 自动恢复管理器"""

    def __init__(
        self,
        health_checker: HealthChecker,
        max_restarts: int = 3,
        restart_cooldown: float = 60.0,
        reset_window: float = 600.0,  # 持续健康10分钟后重置重启计数
    ):
        self.health = health_checker
        self.max_restarts = max_restarts
        self.restart_cooldown = restart_cooldown
        self.reset_window = reset_window
        self._restart_funcs: Dict[str, Callable] = {}
        self._stop_funcs: Dict[str, Callable] = {}  # 停止函数（重启前先停旧实例）
        self._last_restart: Dict[str, float] = {}
        self._last_healthy_since: Dict[str, float] = {}  # 持续健康起始时间
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register_restart_func(self, bot_id: str, restart_func: Callable, stop_func: Optional[Callable] = None):
        """注册 bot 重启函数和停止函数"""
        self._restart_funcs[bot_id] = restart_func
        if stop_func:
            self._stop_funcs[bot_id] = stop_func

    async def _check_loop(self):
        """定期检查并自动恢复"""
        while self._running:
            try:
                statuses = self.health.check_all()
                now = time.time()
                for bot_id, healthy in statuses.items():
                    if healthy:
                        # 记录持续健康起始时间
                        if bot_id not in self._last_healthy_since:
                            self._last_healthy_since[bot_id] = now
                        # 持续健康超过 reset_window，重置重启计数
                        elif now - self._last_healthy_since[bot_id] > self.reset_window:
                            status = self.health._bot_status.get(bot_id, {})
                            if status.get("restart_count", 0) > 0:
                                logger.info(f"[{bot_id}] 持续健康 {self.reset_window:.0f}s，重置重启计数")
                                status["restart_count"] = 0
                                self._last_healthy_since[bot_id] = now
                    else:
                        # 不健康时清除健康计时
                        self._last_healthy_since.pop(bot_id, None)
                        await self._try_restart(bot_id)
            except Exception as e:
                logger.error(f"健康检查循环错误: {e}")

            await asyncio.sleep(30)  # 每30秒检查一次

    async def _try_restart(self, bot_id: str):
        """尝试重启 bot（先停旧实例，等待后再启新实例）"""
        status = self.health._bot_status.get(bot_id, {})
        restart_count = status.get("restart_count", 0)

        if restart_count >= self.max_restarts:
            logger.error(
                f"[{bot_id}] 已达最大重启次数 ({self.max_restarts})，放弃恢复"
            )
            return

        last = self._last_restart.get(bot_id, 0)
        if time.time() - last < self.restart_cooldown:
            return

        restart_func = self._restart_funcs.get(bot_id)
        if not restart_func:
            logger.warning(f"[{bot_id}] 未注册重启函数")
            return

        logger.warning(f"[{bot_id}] 尝试自动恢复 (第 {restart_count + 1} 次)")
        self._last_restart[bot_id] = time.time()

        try:
            # 先停止旧的 polling 实例，防止 409 Conflict
            stop_func = self._stop_funcs.get(bot_id)
            if stop_func:
                logger.info(f"[{bot_id}] 停止旧实例...")
                try:
                    await stop_func()
                except Exception as e:
                    logger.debug(f"[{bot_id}] 停止旧实例时出错(可忽略): {e}")

            # 等待 Telegram 释放 polling 会话
            await asyncio.sleep(5)

            await restart_func()
            status["restart_count"] = restart_count + 1
            status["healthy"] = True
            status["consecutive_errors"] = 0
            status["last_heartbeat"] = time.time()
            logger.info(f"[{bot_id}] 自动恢复成功")
        except Exception as e:
            status["restart_count"] = restart_count + 1
            logger.error(f"[{bot_id}] 自动恢复失败: {e}")

    def start(self):
        """启动自动恢复"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        def _recovery_done(t):
            if not t.cancelled() and t.exception():
                logger.warning("[AutoRecovery] 自动恢复循环崩溃: %s", t.exception())
        self._task.add_done_callback(_recovery_done)
        logger.info("自动恢复管理器已启动")

    def stop(self):
        """停止"""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("自动恢复管理器已停止")


# ============ 对标 LiteLLM v2: 成本归因分析器 ============

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
            self._db_path = str(Path(__file__).parent.parent / "data" / "cost_analytics.db")
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
            with sqlite3.connect(self._db_path) as conn:
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
            with sqlite3.connect(self._db_path) as conn:
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
            with sqlite3.connect(self._db_path) as conn:
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
                conn.execute("DELETE FROM cost_events WHERE ts < ?", (cutoff,))
                conn.commit()
        except Exception as e:
            logger.debug(f"[CostAnalyzer] 清理失败: {e}")


# ============ 对标 Datadog/Grafana: 异常检测器 ============

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
        self._alerts: List[Dict[str, Any]] = []
        self._max_alerts = 200

    def record_request(self, latency_ms: float, success: bool, cost_usd: float = 0.0):
        """记录一次请求的指标"""
        now = time.time()
        with self._lock:
            self._latency_window.append(latency_ms)
            self._error_window.append(not success)
            self._cost_window.append(cost_usd)
            self._request_timestamps.append(now)

    def _z_score(self, values: List[float], current: float) -> float:
        """计算 Z-score"""
        if len(values) < 10:
            return 0.0
        import math
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 0.001
        return (current - mean) / std

    def detect_latency_spike(self, threshold_z: float = 2.5) -> Optional[Dict[str, Any]]:
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

    def detect_error_rate_spike(self, threshold: float = 0.3) -> Optional[Dict[str, Any]]:
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

    def detect_cost_anomaly(self, threshold_z: float = 3.0) -> Optional[Dict[str, Any]]:
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

    def detect_traffic_anomaly(self) -> Optional[Dict[str, Any]]:
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

    def check_all(self) -> List[Dict[str, Any]]:
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

    def _add_alert(self, alert: Dict[str, Any]):
        with self._lock:
            self._alerts.append(alert)
            if len(self._alerts) > self._max_alerts:
                self._alerts = self._alerts[-self._max_alerts:]

    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._alerts[-limit:])

    def get_health_summary(self) -> Dict[str, Any]:
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


# ============ 全局实例 ============

cost_analyzer = CostAnalyzer()
anomaly_detector = AnomalyDetector()

# ============ 监控增强 (从 monitoring_extras 集成) ============

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
