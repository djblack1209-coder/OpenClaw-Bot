"""
ClawBot 监控 — 结构化日志 + 任务可观测性

StructuredLogger: 结构化 JSON 日志 + Prometheus 指标集成
TaskObserver: 任务级质量评估、成本分析、检索评估
"""
import time
import json
import logging
from typing import Dict, Any, Optional
from datetime import timedelta
from pathlib import Path

from src.utils import now_et
from src.monitoring.metrics import prom

logger = logging.getLogger(__name__)


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
            self.log_dir = Path(__file__).parent.parent.parent / "logs"
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
    def _rotate_jsonl(path, max_bytes: int, max_backups: int):
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


class TaskObserver:
    """任务级可观测性：质量评估、成本分析、检索评估。

    每个"任务"是一个完整的用户请求处理周期，可能包含多次 API 调用。
    跟踪每个任务的总成本、总延迟、输出质量评分、检索命中率。
    """

    def __init__(self, log_dir: Optional[str] = None):
        if log_dir:
            self._log_dir = Path(log_dir)
        else:
            self._log_dir = Path(__file__).parent.parent.parent / "logs"
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
