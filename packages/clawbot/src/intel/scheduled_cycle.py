"""Timezone-stable, at-most-once dispatch for the Intel Brief LaunchAgent.

The host wakes this entry point hourly. Only the real Singapore delivery window
can claim a business date. A durable claim survives failures and process death;
review is required before any manual retry with the separate one-shot command.
"""

from __future__ import annotations

import json
import os
import stat
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.runtime_policy import (
    DEFAULT_INTEL_BRIEF_DELIVERY_TIME,
    DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE,
    evaluate_intel_brief_delivery_window,
)

STATE_DIRECTORY = "scheduler-state"


def _now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10 worker compatibility


def _private_file(directory_fd: int, name: str, flags: int) -> int:
    fd = os.open(name, flags | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise ValueError("scheduler state must be an owned regular file")
        os.fchmod(fd, 0o600)
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def _locked_state(output_dir: Path) -> Iterator[int | None]:
    import fcntl

    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise ValueError("scheduler output directory must not be a symlink")
    state_dir = output_dir / STATE_DIRECTORY
    state_dir.mkdir(mode=0o700, exist_ok=True)
    directory_fd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock_fd = None
    try:
        if os.fstat(directory_fd).st_uid != os.getuid():
            raise ValueError("scheduler state directory must be owned by the current user")
        os.fchmod(directory_fd, 0o700)
        lock_fd = _private_file(directory_fd, "dispatch.lock", os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield None
            return
        yield directory_fd
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        os.close(directory_fd)


def _write_json(fd: int, payload: dict[str, Any]) -> None:
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def _finish_claim(directory_fd: int, name: str, payload: dict[str, Any]) -> None:
    temporary = f".{name}.{uuid.uuid4().hex}.tmp"
    try:
        fd = _private_file(directory_fd, temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        _write_json(fd, payload)
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory_fd)


def run_scheduled_intel_cycle(
    *,
    output_dir: str | Path,
    evidence_path: str | Path,
    project_root: str | Path | None = None,
    sources: list[str] | None = None,
    llm_mode: str = "fallback-only",
    env: dict[str, str] | None = None,
    clock: Callable[[], datetime] | None = None,
    cycle_runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Claim today's Singapore window before invoking any collection or delivery.

    Clock/runner injection is for isolated tests only. The scheduled CLI exposes
    neither replay timestamps nor a claim-reset option. Skips leave the latest
    real production-cycle evidence untouched.
    """
    now = (clock or _now)()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("scheduled clock must be timezone aware")
    window = evaluate_intel_brief_delivery_window(now=now)
    scheduler = {
        "timezone": DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE,
        "delivery_time": DEFAULT_INTEL_BRIEF_DELIVERY_TIME,
        "business_date": window.local_now.date().isoformat(),
        "window_status": window.reason,
    }

    def skipped(reason: str) -> dict[str, Any]:
        return {"status": "skipped", "reason": reason, "network_calls": 0, "scheduler": scheduler}

    if not window.should_run:
        return skipped(window.reason)

    root = Path(project_root) if project_root is not None else Path.cwd()
    output = Path(output_dir)
    if not output.is_absolute():
        output = root / output
    claim_name = f"{scheduler['business_date']}.json"
    claim = {
        **scheduler,
        "claimed_at": now.astimezone(timezone.utc).isoformat(),  # noqa: UP017
        "status": "claimed",
    }

    def delivery_clock() -> datetime:
        current = (clock or _now)()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("delivery clock must be timezone aware")
        current_window = evaluate_intel_brief_delivery_window(now=current)
        if current_window.local_now.date().isoformat() != scheduler["business_date"]:
            raise ValueError("the claimed Singapore business date has ended")
        return current

    cycle_started = False
    try:
        with _locked_state(output) as directory_fd:
            if directory_fd is None:
                return skipped("scheduler_running")
            try:
                fd = _private_file(directory_fd, claim_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return skipped("business_date_already_claimed")
            # Persist both the file content and directory entry before side effects.
            _write_json(fd, claim)
            os.fsync(directory_fd)
            cycle_started = True
            try:
                if cycle_runner is None:
                    from src.intel.production_cycle import run_intel_production_cycle

                    cycle_runner = run_intel_production_cycle
                env_map = dict(os.environ if env is None else env)
                env_map.update({
                    "INTEL_BRIEF_SCHEDULER_TIMEZONE": DEFAULT_INTEL_BRIEF_SCHEDULER_TIMEZONE,
                    "INTEL_BRIEF_SCHEDULER_WINDOW_END": "10:00",
                })
                result = cycle_runner(
                    output_dir=output,
                    evidence_path=evidence_path,
                    now=now,
                    scheduled_time=DEFAULT_INTEL_BRIEF_DELIVERY_TIME,
                    project_root=root,
                    sources=sources,
                    llm_mode=llm_mode,
                    env=env_map,
                    delivery_clock=delivery_clock,
                )
                if not isinstance(result, dict) or result.get("status") not in {"success", "failed", "blocked", "unknown"}:
                    result = {"status": "unknown", "reason": "invalid_cycle_result", "network_calls": None}
            except Exception as error:
                result = {
                    "status": "unknown",
                    "reason": "cycle_runner_exception",
                    "error_type": type(error).__name__,
                    "network_calls": None,
                }
            _finish_claim(directory_fd, claim_name, {**claim, "status": result["status"]})
            return {**result, "scheduler": scheduler}
    except (OSError, ValueError) as error:
        # A failed final state write may follow a successful external send. Keep
        # the original durable claim and never classify the network outcome as zero.
        return {
            "status": "unknown" if cycle_started else "blocked",
            "reason": "scheduler_state_unavailable",
            "error_type": type(error).__name__,
            "network_calls": None if cycle_started else 0,
            "scheduler": scheduler,
        }
