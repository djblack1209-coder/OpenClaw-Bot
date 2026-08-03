"""P0 社媒发布授权门回归测试。"""

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.social_scheduler as social_scheduler
from src.api.rpc import ClawBotRPC


@pytest.fixture(autouse=True)
def isolate_state_file(tmp_path, monkeypatch):
    """隔离两套社媒草稿状态，避免读取本机生产数据。"""
    monkeypatch.setenv(
        "OPENCLAW_PUBLISH_LOCK_PATH",
        str(tmp_path / "locks" / "social-publish.lock"),
    )
    scheduler_state = tmp_path / "social_scheduler.json"
    monkeypatch.setattr(social_scheduler, "_STATE_FILE", scheduler_state)

    from src.execution.social import x_auto_ops

    x_state = tmp_path / "x_auto_ops.json"
    monkeypatch.setattr(x_auto_ops, "_STATE_FILE", x_state)
    x_auto_ops._save_state({"drafts": [], "extension_schedule": []}, x_state)
    yield scheduler_state


def _seed_draft() -> None:
    state = social_scheduler._load_state()
    state["drafts"] = [
        {
            "id": "draft-gated-1",
            "status": "ready",
            "platform": "x",
            "text": "这是经过审核后才能发布的正文",
        }
    ]
    social_scheduler._save_state(state)


def test_content_direct_publish_is_closed(isolate_state_file):
    with patch("src.execution.social.worker_bridge.run_social_worker_async") as worker:
        result = asyncio.run(
            ClawBotRPC._rpc_social_publish(
                platform="x",
                content="绕过草稿的直发内容",
            )
        )

    assert result["success"] is False
    assert result["requires_approved_draft"] is True
    worker.assert_not_called()


def test_platform_helpers_cannot_bypass_draft_gate(isolate_state_file):
    from src.execution.social.x_platform import publish_x_post
    from src.execution.social.xhs_platform import publish_xhs_article

    worker = MagicMock()
    x_result = asyncio.run(publish_x_post("绕过审核的 X 正文", worker_fn=worker))
    xhs_result = asyncio.run(
        publish_xhs_article("标题", "绕过审核的小红书正文", worker_fn=worker)
    )

    assert x_result["success"] is False
    assert xhs_result["success"] is False
    assert x_result["requires_approved_draft"] is True
    assert xhs_result["requires_final_confirmation"] is True
    worker.assert_not_called()


def test_approved_draft_still_requires_one_time_confirmation(isolate_state_file):
    _seed_draft()
    approval = ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")

    with patch("src.execution.social.worker_bridge.run_social_worker") as worker:
        result = asyncio.run(ClawBotRPC._rpc_social_draft_publish(0))

    assert approval["success"] is True
    assert result["success"] is False
    assert result["requires_final_confirmation"] is True
    worker.assert_not_called()


def test_confirmation_is_bound_to_immutable_content(isolate_state_file):
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")
    token = confirmation["confirmation_token"]

    state = social_scheduler._load_state()
    state["drafts"][0]["text"] = "审核后被替换的内容"
    social_scheduler._save_state(state)

    with patch("src.execution.social.worker_bridge.run_social_worker") as worker:
        result = asyncio.run(
            ClawBotRPC._rpc_social_draft_publish(0, confirmation_token=token)
        )

    assert result["success"] is False
    assert result["requires_review"] is True
    worker.assert_not_called()


def test_confirmation_token_can_only_be_consumed_once(isolate_state_file):
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")
    token = confirmation["confirmation_token"]

    with patch(
        "src.execution.social.worker_bridge.run_social_worker",
        return_value={"success": True, "url": "https://x.com/demo/status/1"},
    ) as worker:
        first = asyncio.run(
            ClawBotRPC._rpc_social_draft_publish(0, confirmation_token=token)
        )
        second = asyncio.run(
            ClawBotRPC._rpc_social_draft_publish(0, confirmation_token=token)
        )

    assert first["success"] is True
    assert second["success"] is False
    assert second["requires_final_confirmation"] is True
    assert worker.call_count == 1


def test_publish_completion_uses_stable_id_after_queue_reorder(isolate_state_file):
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")
    worker_started = threading.Event()
    release_worker = threading.Event()

    def blocked_worker(action, payload):
        worker_started.set()
        assert release_worker.wait(timeout=5)
        return {"success": True, "url": "https://x.com/demo/status/reordered"}

    async def scenario():
        with patch(
            "src.execution.social.worker_bridge.run_social_worker",
            side_effect=blocked_worker,
        ):
            publishing = asyncio.create_task(
                ClawBotRPC._rpc_social_draft_publish(
                    0,
                    confirmation_token=confirmation["confirmation_token"],
                )
            )
            assert await asyncio.to_thread(worker_started.wait, 5)
            state = social_scheduler._load_state()
            state["drafts"] = [
                {
                    "id": "replacement-draft",
                    "status": "ready",
                    "platform": "x",
                    "text": "不能被旧索引污染的新草稿",
                }
            ]
            social_scheduler._save_state(state)
            release_worker.set()
            return await publishing

    result = asyncio.run(scenario())
    latest = social_scheduler._load_state()["drafts"]

    assert result["success"] is True
    assert result["state_update_rejected"] is True
    assert result["external_result"]["url"] == "https://x.com/demo/status/reordered"
    assert result["manual_reconciliation_required"] is True
    assert latest == [
        {
            "id": "replacement-draft",
            "status": "ready",
            "platform": "x",
            "text": "不能被旧索引污染的新草稿",
        }
    ]
    outcomes = social_scheduler._load_state()["publish_outcomes"]
    assert len(outcomes) == 1
    assert outcomes[0]["draft_id"] == "draft-gated-1"
    assert outcomes[0]["external_success"] is True
    assert outcomes[0]["url"] == "https://x.com/demo/status/reordered"


def test_stale_snapshot_conflict_permanently_revokes_confirmation(isolate_state_file):
    """即使外部旧快照绕过事务落盘，冲突分支也不能恢复可复用令牌。"""
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")
    token = confirmation["confirmation_token"]
    stale_state = social_scheduler._load_state()
    worker_started = threading.Event()
    release_worker = threading.Event()

    def blocked_worker(action, payload):
        worker_started.set()
        assert release_worker.wait(timeout=5)
        return {"success": True, "url": "https://x.com/demo/status/stale-conflict"}

    async def scenario():
        with patch(
            "src.execution.social.worker_bridge.run_social_worker",
            side_effect=blocked_worker,
        ) as worker:
            publishing = asyncio.create_task(
                ClawBotRPC._rpc_social_draft_publish(0, confirmation_token=token)
            )
            assert await asyncio.to_thread(worker_started.wait, 5)
            social_scheduler._save_state(stale_state)
            release_worker.set()
            first = await publishing
            second = await ClawBotRPC._rpc_social_draft_publish(0, confirmation_token=token)
            return first, second, worker.call_count

    first, second, worker_calls = asyncio.run(scenario())
    latest = social_scheduler._load_state()["drafts"][0]

    assert first["success"] is True
    assert first["manual_reconciliation_required"] is True
    assert second["success"] is False
    assert latest["status"] == "manual_reconciliation_required"
    assert latest["review_status"] == "pending"
    assert "confirmation_token_hash" not in latest
    assert worker_calls == 1


def test_publishing_draft_rejects_edit_delete_and_review(isolate_state_file):
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")
    worker_started = threading.Event()
    release_worker = threading.Event()

    def blocked_worker(action, payload):
        worker_started.set()
        assert release_worker.wait(timeout=5)
        return {"success": True, "url": "https://x.com/demo/status/immutable"}

    async def scenario():
        with patch(
            "src.execution.social.worker_bridge.run_social_worker",
            side_effect=blocked_worker,
        ):
            publishing = asyncio.create_task(
                ClawBotRPC._rpc_social_draft_publish(
                    0,
                    confirmation_token=confirmation["confirmation_token"],
                )
            )
            assert await asyncio.to_thread(worker_started.wait, 5)
            mutation_results = [
                ClawBotRPC._rpc_social_draft_update(0, "发布途中不允许替换"),
                ClawBotRPC._rpc_social_draft_delete(0),
                ClawBotRPC._rpc_social_draft_review(0, approved=False, reviewer="owner"),
            ]
            release_worker.set()
            return mutation_results, await publishing

    mutation_results, publish_result = asyncio.run(scenario())
    latest = social_scheduler._load_state()["drafts"][0]

    assert all(result["success"] is False for result in mutation_results)
    assert all(result["immutable_status"] == "publishing" for result in mutation_results)
    assert publish_result["success"] is True
    assert latest["status"] == "published"
    assert latest["text"] == "这是经过审核后才能发布的正文"


def test_concurrent_confirmation_consumption_publishes_only_once(isolate_state_file):
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")
    token = confirmation["confirmation_token"]

    def slow_worker(action, payload):
        time.sleep(0.05)
        return {"success": True, "url": "https://x.com/demo/status/concurrent"}

    def publish_once():
        return asyncio.run(
            ClawBotRPC._rpc_social_draft_publish(0, confirmation_token=token)
        )

    with patch(
        "src.execution.social.worker_bridge.run_social_worker",
        side_effect=slow_worker,
    ) as worker, ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [pool.submit(publish_once), pool.submit(publish_once)]]

    assert sum(1 for result in results if result.get("success")) == 1
    assert worker.call_count == 1


def test_scheduler_review_cannot_restore_consumed_confirmation(isolate_state_file):
    """定时复盘的旧快照不能覆盖已消费令牌并造成重复发布。"""
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")
    token = confirmation["confirmation_token"]
    metrics_started = threading.Event()
    release_metrics = threading.Event()
    publish_calls = 0

    def worker(action, payload):
        nonlocal publish_calls
        if action == "metrics":
            metrics_started.set()
            assert release_metrics.wait(timeout=5)
            return {"success": False}
        publish_calls += 1
        return {"success": True, "url": "https://x.com/demo/status/transaction"}

    with patch("src.execution.social.worker_bridge.run_social_worker", side_effect=worker), patch(
        "src.social_scheduler._notify"
    ):
        review_thread = threading.Thread(target=social_scheduler.job_late_review)
        review_thread.start()
        assert metrics_started.wait(timeout=5)
        first = asyncio.run(
            ClawBotRPC._rpc_social_draft_publish(0, confirmation_token=token)
        )
        release_metrics.set()
        review_thread.join(timeout=5)
        assert not review_thread.is_alive()
        second = asyncio.run(
            ClawBotRPC._rpc_social_draft_publish(0, confirmation_token=token)
        )

    latest = social_scheduler._load_state()["drafts"][0]
    assert first["success"] is True
    assert second["success"] is False
    assert latest["status"] == "published"
    assert latest["confirmation_used"] is True
    assert publish_calls == 1


def test_x_auto_rebuild_preserves_authorized_draft(isolate_state_file, tmp_path):
    """自动重建同 ID 草稿时不能覆盖已审核快照和一次性令牌。"""
    from src.execution.social import x_auto_ops
    from src.execution.social.publish_gate import issue_publish_confirmation, seal_approved_draft

    state_path = tmp_path / "x-auto-authorized.json"
    approved = {
        "id": "xauto-stable",
        "platform": "x",
        "status": "approved",
        "review_status": "approved",
        "text": "已经审核的正文",
    }
    seal_approved_draft(approved)
    confirmation = issue_publish_confirmation(approved)
    x_auto_ops._save_state({"drafts": [approved]}, state_path)

    generated = {
        "id": "xauto-stable",
        "platform": "x",
        "status": "ready",
        "review_status": "pending",
        "text": "定时器新生成但不应覆盖的正文",
    }
    committed = x_auto_ops._mutate_state(
        state_path,
        lambda state: x_auto_ops._merge_generated_drafts(
            state,
            [generated],
            limit=80,
            rebuild=True,
        ),
    )

    latest = x_auto_ops._load_state(state_path)["drafts"][0]
    assert confirmation["success"] is True
    assert committed[0]["text"] == "已经审核的正文"
    assert latest["text"] == "已经审核的正文"
    assert latest["confirmation_token_hash"] == approved["confirmation_token_hash"]


def test_subprocesses_share_one_publish_transaction(isolate_state_file, tmp_path):
    """两个真实 Python 进程争用同一令牌时只能有一个调用发布器。"""
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")
    marker = tmp_path / "worker-calls.txt"
    x_state = tmp_path / "x_auto_ops.json"
    script = """
import asyncio
import json
import sys
import time
from pathlib import Path

import src.social_scheduler as social_scheduler
from src.execution.social import worker_bridge, x_auto_ops

social_scheduler._STATE_FILE = Path(sys.argv[1])
x_auto_ops._STATE_FILE = Path(sys.argv[2])
marker = Path(sys.argv[3])
token = sys.argv[4]

def worker(action, payload):
    with marker.open("a", encoding="utf-8") as handle:
        handle.write(f"{action}\\n")
    time.sleep(0.2)
    return {"success": True, "url": "https://x.com/demo/status/subprocess"}

worker_bridge.run_social_worker = worker
from src.api.rpc import ClawBotRPC

result = asyncio.run(ClawBotRPC._rpc_social_draft_publish(0, confirmation_token=token))
print(json.dumps(result, ensure_ascii=False))
"""
    args = [
        sys.executable,
        "-c",
        script,
        str(isolate_state_file),
        str(x_state),
        str(marker),
        confirmation["confirmation_token"],
    ]
    env = os.environ.copy()
    project_root = Path(__file__).resolve().parents[1]
    processes = [
        subprocess.Popen(
            args,
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    completed = [process.communicate(timeout=20) for process in processes]

    for process, (_stdout, stderr) in zip(processes, completed, strict=True):
        assert process.returncode == 0, stderr
    results = [json.loads(stdout.strip().splitlines()[-1]) for stdout, _stderr in completed]
    assert sum(1 for result in results if result.get("success")) == 1
    assert marker.read_text(encoding="utf-8").splitlines() == ["publish_x"]


def test_subprocess_draft_creates_do_not_lose_updates(tmp_path, monkeypatch):
    """两个进程同时创建草稿时，最终文件必须保留两条记录。"""
    drafts_file = tmp_path / "drafts.json"
    lock_path = tmp_path / "locks" / "social-publish.lock"
    start_file = tmp_path / "start"
    ready_dir = tmp_path / "ready"
    ready_dir.mkdir()
    monkeypatch.setenv("OPENCLAW_PUBLISH_LOCK_PATH", str(lock_path))
    script = """
import sys
import time
from pathlib import Path

from src.execution.social import drafts

drafts._DRAFTS_DIR = Path(sys.argv[1])
drafts._DRAFTS_FILE = Path(sys.argv[2])
ready = Path(sys.argv[3])
start = Path(sys.argv[4])
body = sys.argv[5]
original_load = drafts._load_drafts

def slow_load():
    state = original_load()
    time.sleep(0.25)
    return state

drafts._load_drafts = slow_load
ready.touch()
while not start.exists():
    time.sleep(0.01)
result = drafts.save_social_draft("x", "", body)
print(result["draft_id"])
"""
    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(tmp_path),
                str(drafts_file),
                str(ready_dir / f"{index}.ready"),
                str(start_file),
                f"并发草稿 {index}",
            ],
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(2)
    ]
    completed = []
    try:
        deadline = time.time() + 20
        while len(list(ready_dir.glob("*.ready"))) < 2 and time.time() < deadline:
            time.sleep(0.01)
        assert len(list(ready_dir.glob("*.ready"))) == 2
        start_file.touch()
        completed = [process.communicate(timeout=10) for process in processes]
    finally:
        # 断言或子进程失败时也必须解除等待并回收，避免污染后续测试。
        start_file.touch(exist_ok=True)
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)

    for process, (_stdout, stderr) in zip(processes, completed, strict=True):
        assert process.returncode == 0, stderr
    stored = json.loads(drafts_file.read_text(encoding="utf-8"))
    assert {item["body"] for item in stored} == {"并发草稿 0", "并发草稿 1"}


def test_draft_service_propagates_worker_failure(tmp_path, monkeypatch):
    from src.execution.social import drafts
    monkeypatch.setattr(drafts, "_DRAFTS_DIR", tmp_path)
    monkeypatch.setattr(drafts, "_DRAFTS_FILE", tmp_path / "drafts.json")
    saved = drafts.save_social_draft("x", "", "发布器失败不能误报成功")
    approval = drafts.update_social_draft_status(saved["draft_id"], "approved")
    confirmation = drafts.final_confirm_social_draft(saved["draft_id"])

    result = drafts.publish_social_draft(
        platform="x",
        draft_id=saved["draft_id"],
        confirmation_token=confirmation["confirmation_token"],
        worker_fn=lambda action, payload: {"success": False, "error": "浏览器不可用"},
    )

    assert approval["success"] is True
    assert confirmation["success"] is True
    assert result["success"] is False
    assert result["result"]["success"] is False
    assert "浏览器不可用" in result["error"]


def test_scheduler_state_save_failure_blocks_publish_worker(isolate_state_file):
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")

    with patch("src.social_scheduler._save_state", side_effect=OSError("disk full")), patch(
        "src.execution.social.worker_bridge.run_social_worker"
    ) as worker, pytest.raises(OSError, match="disk full"):
        asyncio.run(
            ClawBotRPC._rpc_social_draft_publish(
                0,
                confirmation_token=confirmation["confirmation_token"],
            )
        )

    worker.assert_not_called()


def test_publish_success_is_reported_when_completion_save_fails(isolate_state_file):
    _seed_draft()
    ClawBotRPC._rpc_social_draft_review(0, approved=True, reviewer="owner")
    confirmation = ClawBotRPC._rpc_social_draft_final_confirm(0, reviewer="owner")
    real_save = social_scheduler._save_state
    save_calls = 0

    def fail_completion_save(state):
        nonlocal save_calls
        save_calls += 1
        if save_calls == 2:
            raise OSError("disk full after publish")
        real_save(state)

    with patch(
        "src.social_scheduler._save_state",
        side_effect=fail_completion_save,
    ), patch(
        "src.execution.social.worker_bridge.run_social_worker",
        return_value={"success": True, "url": "https://x.com/demo/status/disk-full"},
    ) as worker:
        result = asyncio.run(
            ClawBotRPC._rpc_social_draft_publish(
                0,
                confirmation_token=confirmation["confirmation_token"],
            )
        )

    assert result["success"] is True
    assert result["external_result"]["url"] == "https://x.com/demo/status/disk-full"
    assert result["audit_persisted"] is False
    assert result["manual_reconciliation_required"] is True
    assert social_scheduler._load_state()["drafts"][0]["status"] == "publishing"
    worker.assert_called_once()


def test_local_draft_save_failure_blocks_publish_worker(tmp_path, monkeypatch):
    from src.execution.social import drafts

    monkeypatch.setattr(drafts, "_DRAFTS_DIR", tmp_path)
    monkeypatch.setattr(drafts, "_DRAFTS_FILE", tmp_path / "drafts.json")
    saved = drafts.save_social_draft("x", "", "落盘失败时绝不能外发")
    drafts.update_social_draft_status(saved["draft_id"], "approved")
    confirmation = drafts.final_confirm_social_draft(saved["draft_id"])
    worker = MagicMock()

    with patch.object(drafts, "_save_drafts", side_effect=OSError("read only")), pytest.raises(
        OSError,
        match="read only",
    ):
        drafts.publish_social_draft(
            platform="x",
            draft_id=saved["draft_id"],
            confirmation_token=confirmation["confirmation_token"],
            worker_fn=worker,
        )

    worker.assert_not_called()


def test_publish_worker_timeout_is_not_retried():
    from src.execution.social.worker_bridge import run_social_worker

    timeout = subprocess.TimeoutExpired(cmd="social_browser_worker", timeout=300)
    with patch("src.execution.social.worker_bridge.subprocess.run", side_effect=timeout) as runner, patch(
        "src.execution.social.worker_bridge.time.sleep"
    ) as sleeper:
        result = run_social_worker("publish_x", {"text": "只允许尝试一次"})

    assert result["success"] is False
    assert runner.call_count == 1
    sleeper.assert_not_called()


def test_launchagent_cli_cannot_publish_approved_draft_without_token():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "x_auto_morning_post.py"
    spec = importlib.util.spec_from_file_location("x_auto_morning_post_p0", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    approved = {
        "id": "xauto-approved-1",
        "platform": "x",
        "status": "approved",
        "review_status": "approved",
        "text": "只有最终确认令牌才能发布",
    }

    with patch.object(module, "get_or_build_next_ready_draft", return_value=approved), patch(
        "src.execution.social.x_platform.twikit_post_tweet",
        new_callable=AsyncMock,
    ) as twikit, patch(
        "src.execution.social.worker_bridge.run_social_worker"
    ) as worker:
        result = asyncio.run(module.publish_once())

    assert result["success"] is False
    assert result["requires_final_confirmation"] is True
    assert result["external_actions_locked"] is True
    twikit.assert_not_called()
    worker.assert_not_called()
