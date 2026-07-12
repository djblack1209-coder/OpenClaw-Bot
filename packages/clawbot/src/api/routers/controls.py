"""控制面板端点 — 交易控制、调度器控制、全局设置"""

import json
import logging
import os
from datetime import UTC
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# 持久化状态文件路径
CONTROLS_STATE_FILE = Path(__file__).resolve().parents[3] / "data" / "controls_state.json"


class TradingControls(BaseModel):
    """交易控制开关"""

    auto_trader_enabled: bool = False
    ibkr_live_mode: bool = False  # True=实盘, False=模拟盘
    risk_protection_enabled: bool = True  # 风控熔断（只读展示，不允许关闭）
    allow_short_selling: bool = False
    max_daily_trades: int = 50


class SocialControls(BaseModel):
    """社媒控制开关"""

    xhs_enabled: bool = True
    x_twitter_enabled: bool = True
    auto_hotspot_post: bool = False
    content_review_mode: bool = True  # True=发布前人工审核
    scheduler_paused: bool = False


class SchedulerControls(BaseModel):
    """调度器任务控制"""

    scheduler_enabled: bool = True
    maintenance_mode: bool = False


class GlobalSettings(BaseModel):
    """全局设置"""

    daily_budget_usd: float = 50.0
    default_llm_model: str = "claude-sonnet-4-20250514"
    local_hf_model_enabled: bool = True
    local_hf_model_endpoint: str = "http://localhost:11434"
    auto_heal_enabled: bool = True
    scheduler_enabled: bool = True
    maintenance_mode: bool = False


def _load_state() -> dict:
    """从文件加载控制状态"""
    if CONTROLS_STATE_FILE.exists():
        try:
            return json.loads(CONTROLS_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("读取控制状态文件失败: %s", e)
    return {}


def _save_state(state: dict) -> None:
    """以 0600 原子保存控制状态，避免开关写到一半或被其他账号读取。"""
    CONTROLS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONTROLS_STATE_FILE.parent.chmod(0o700)
    temporary = CONTROLS_STATE_FILE.with_name(
        f".{CONTROLS_STATE_FILE.name}.tmp-{os.getpid()}"
    )
    try:
        temporary.write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(CONTROLS_STATE_FILE)
        CONTROLS_STATE_FILE.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


# ── 交易控制 ──────────────────────────────────────


@router.get("/controls/trading", response_model=TradingControls)
def get_trading_controls():
    """获取交易控制开关状态"""
    state = _load_state()
    trading = state.get("trading", {})
    return TradingControls(**trading)


@router.post("/controls/trading", response_model=TradingControls)
def update_trading_controls(controls: TradingControls):
    """更新交易控制开关"""
    # 风控熔断不允许关闭
    if not controls.risk_protection_enabled:
        raise HTTPException(status_code=400, detail="风控熔断保护不允许关闭")

    state = _load_state()
    state["trading"] = controls.model_dump()
    _save_state(state)

    # 联动：如果 auto_trader 状态变化，通知交易系统
    try:
        from src.auto_trader import AutoTrader

        if hasattr(AutoTrader, "instance") and AutoTrader.instance:
            if controls.auto_trader_enabled:
                AutoTrader.instance.start()
            else:
                AutoTrader.instance.stop()
    except Exception as e:
        logger.warning("联动 AutoTrader 失败（非致命）: %s", e)

    logger.info("交易控制已更新: %s", controls.model_dump())
    return controls


# ── 社媒控制 ──────────────────────────────────────


@router.get("/controls/social", response_model=SocialControls)
def get_social_controls():
    """获取社媒控制开关状态"""
    state = _load_state()
    social = state.get("social", {})
    return SocialControls(**social)


@router.post("/controls/social", response_model=SocialControls)
def update_social_controls(controls: SocialControls):
    """更新社媒控制开关"""
    state = _load_state()
    state["social"] = controls.model_dump()
    _save_state(state)
    logger.info("社媒控制已更新: %s", controls.model_dump())
    return controls


# ── 调度器控制 ──────────────────────────────────────


@router.get("/controls/scheduler")
def get_scheduler_status():
    """获取调度器状态和所有任务列表"""
    state = _load_state()
    scheduler_state = state.get("scheduler", {})

    # 尝试从运行中的 ExecutionHub 实例获取调度器运行时状态
    scheduler_running = False
    scheduler_instance = None
    try:
        from src.bot.globals import execution_hub
        scheduler_instance = execution_hub._scheduler
        scheduler_running = getattr(scheduler_instance, "_running", False)
    except Exception:
        pass  # globals 未初始化，退回静态列表

    # 静态任务描述表 — 与 ExecutionScheduler._loop() 中实际注册的任务一一对应
    # 注: ExecutionScheduler 是循环驱动型调度器，没有任务注册表，
    #     因此这里维护一份与代码同步的静态描述。
    #     如果调度器正在运行，补充 last_run 等运行时字段。
    static_tasks = [
        {"id": "daily_brief", "name": "每日运营简报", "cron": "08:00 ET", "enabled": True},
        {"id": "intel_brief", "name": "Intel Brief 沙盒闸门", "cron": "08:30 ET", "enabled": False},
        {"id": "morning_news", "name": "科技早报推送", "cron": "08:00 ET", "enabled": True},
        {"id": "monitors", "name": "监控巡检", "cron": "每15分钟", "enabled": True},
        {"id": "social_operator", "name": "社媒自动驾驶", "cron": "可配间隔", "enabled": True},
        {"id": "bounty_scan", "name": "赏金猎人扫描", "cron": "每45分钟", "enabled": True},
        {"id": "reminders", "name": "用户提醒", "cron": "每60秒", "enabled": True},
        {"id": "bill_checks", "name": "账单告警", "cron": "09:00/18:00 ET", "enabled": True},
        {"id": "xianyu_shipment", "name": "闲鱼发货超时", "cron": "每60秒", "enabled": True},
        {"id": "stock_check", "name": "闲鱼库存预警", "cron": "每4小时", "enabled": True},
        {"id": "price_watch", "name": "降价监控", "cron": "每6小时", "enabled": True},
        {"id": "deal_scan", "name": "全网折扣扫描", "cron": "每4小时", "enabled": True},
        {"id": "budget_alert", "name": "预算超支检查", "cron": "20:00 ET", "enabled": True},
        {"id": "weekly_strategy", "name": "策略绩效评估", "cron": "周日 20:00", "enabled": True},
        {"id": "weekly_report", "name": "综合周报", "cron": "周日 20:30", "enabled": True},
        {"id": "db_cleanup", "name": "数据清理", "cron": "03:00 ET", "enabled": True},
        {"id": "db_backup", "name": "数据库备份", "cron": "04:00 ET", "enabled": True},
    ]

    # 调度器实例属性名 → 任务 id 的映射，用于读取 last_run 时间戳
    _ts_field_map: dict[str, str] = {
        "monitors": "_last_monitor_ts",
        "bounty_scan": "_last_bounty_ts",
        "social_operator": "_last_social_operator_ts",
        "stock_check": "_last_stock_check_ts",
        "price_watch": "_last_price_watch_ts",
    }
    _date_field_map: dict[str, str] = {
        "daily_brief": "_last_brief_date",
        "intel_brief": "_last_intel_brief_date",
        "morning_news": "_last_news_date",
    }

    runtime_health: dict[str, Any] = {}
    if scheduler_instance and hasattr(scheduler_instance, "get_health_snapshot"):
        try:
            snapshot = scheduler_instance.get_health_snapshot()
            runtime_health = snapshot if isinstance(snapshot, dict) else {}
        except Exception:
            logger.debug("读取调度器健康摘要失败", exc_info=True)
    runtime_jobs = runtime_health.get("jobs") if isinstance(runtime_health.get("jobs"), dict) else {}

    tasks: list[dict[str, Any]] = []
    source = "live" if scheduler_running else "static"

    for task_def in static_tasks:
        task: dict[str, Any] = {**task_def, "source": source}

        # 从调度器实例补充运行时信息
        if scheduler_instance and scheduler_running:
            tid = task_def["id"]
            # 时间戳类型的 last_run（monitors, bounty 等）
            if tid in _ts_field_map:
                ts_val = getattr(scheduler_instance, _ts_field_map[tid], 0.0)
                if ts_val and ts_val > 0:
                    from datetime import datetime
                    task["last_run"] = datetime.fromtimestamp(ts_val, tz=UTC).isoformat()
            # 日期类型的 last_run（daily_brief, morning_news 等）
            elif tid in _date_field_map:
                date_val = getattr(scheduler_instance, _date_field_map[tid], "")
                if date_val:
                    task["last_run"] = date_val
            # 特殊：周度任务用 day-of-year 标记
            elif tid == "weekly_strategy":
                day_val = getattr(scheduler_instance, "_last_strategy_review", None)
                if day_val:
                    task["last_run"] = f"yday={day_val}"
            elif tid == "weekly_report":
                day_val = getattr(scheduler_instance, "_last_weekly_report", None)
                if day_val:
                    task["last_run"] = f"yday={day_val}"
            elif tid == "bill_checks":
                check_key = getattr(scheduler_instance, "_last_bill_check", None)
                if check_key:
                    task["last_run"] = check_key
            elif tid == "budget_alert":
                date_val = getattr(scheduler_instance, "_last_budget_alert_date", None)
                if date_val:
                    task["last_run"] = date_val

        job_health = runtime_jobs.get(task_def["id"]) if isinstance(runtime_jobs, dict) else None
        if isinstance(job_health, dict):
            task["last_status"] = job_health.get("status")
            task["consecutive_failures"] = int(job_health.get("consecutive_failures", 0) or 0)
            task["duration_seconds"] = float(job_health.get("duration_seconds", 0.0) or 0.0)
            last_runtime = job_health.get("last_success_at") or job_health.get("last_attempt_at")
            if last_runtime:
                task["last_run"] = last_runtime

        tasks.append(task)

    if not scheduler_running:
        # 调度器未运行时给前端一个提示
        for task in tasks:
            task["note"] = "静态配置（调度器未运行）"

    # 合并持久化的启用/禁用状态
    task_overrides = scheduler_state.get("tasks", {})
    for task in tasks:
        if task["id"] in task_overrides:
            task["enabled"] = task_overrides[task["id"]].get("enabled", True)
            override_last_run = task_overrides[task["id"]].get("last_run")
            if override_last_run and "last_run" not in task:
                task["last_run"] = override_last_run
            override_status = task_overrides[task["id"]].get("last_status")
            if override_status is not None and "last_status" not in task:
                task["last_status"] = override_status

    return {
        "enabled": scheduler_state.get("enabled", True),
        "maintenance_mode": scheduler_state.get("maintenance_mode", False),
        "scheduler_running": scheduler_running,
        "source": source,
        "runtime_health": {
            "iteration_count": int(runtime_health.get("iteration_count", 0) or 0),
            "last_loop_at": runtime_health.get("last_loop_at", ""),
            "last_loop_completed_at": runtime_health.get("last_loop_completed_at", ""),
        },
        "tasks": tasks,
    }


@router.post("/controls/scheduler/toggle")
def toggle_scheduler(enabled: bool):
    """启用/禁用调度器总开关"""
    state = _load_state()
    state.setdefault("scheduler", {})["enabled"] = enabled
    _save_state(state)
    logger.info("调度器总开关: %s", "启用" if enabled else "禁用")
    return {"ok": True, "enabled": enabled}


@router.post("/controls/scheduler/task/{task_id}/toggle")
def toggle_task(task_id: str, enabled: bool):
    """启用/禁用单个调度任务"""
    state = _load_state()
    scheduler = state.setdefault("scheduler", {})
    tasks = scheduler.setdefault("tasks", {})
    tasks.setdefault(task_id, {})["enabled"] = enabled
    _save_state(state)
    logger.info("调度任务 %s: %s", task_id, "启用" if enabled else "禁用")
    return {"ok": True, "task_id": task_id, "enabled": enabled}


# ── 全局设置 ──────────────────────────────────────


@router.get("/controls/settings", response_model=GlobalSettings)
def get_global_settings():
    """获取全局设置"""
    state = _load_state()
    settings = state.get("global_settings", {})
    return GlobalSettings(**settings)


@router.post("/controls/settings", response_model=GlobalSettings)
def update_global_settings(settings: GlobalSettings):
    """更新全局设置"""
    state = _load_state()
    state["global_settings"] = settings.model_dump()
    _save_state(state)
    logger.info("全局设置已更新")
    return settings
