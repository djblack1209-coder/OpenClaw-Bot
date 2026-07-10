from __future__ import annotations

import json
from pathlib import Path

from scripts.intel_worker_remote_run import RemoteRunResult, run_remote_worker_request


class _FakeRunner:
    def __init__(self):
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs):
        self.commands.append(cmd)
        joined = " ".join(cmd)
        if "scripts/intel_worker_cli.py" in joined:
            return _Completed(0, '{"request_id":"remote-test","source":"senate_trading","status":"success","raw_count":1,"items":[{"ticker":"BYND"}],"error":"","worker":"overseas","evidence_path":"phaseb/senate.jsonl"}\n', "")
        if "source_health" in joined:
            return _Completed(0, '{"source_name":"senate_trading","failure_count":0}\n', "")
        if "remote_stage_absent" in joined:
            return _Completed(0, "remote_stage_absent\n", "")
        if "rm -rf" in joined:
            return _Completed(0, "cleanup_ok\n", "")
        return _Completed(0, "", "")


class _Completed:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_remote_runner_stages_executes_queries_health_and_cleans_up(tmp_path):
    runner = _FakeRunner()
    output_path = tmp_path / "remote-evidence.json"

    result = run_remote_worker_request(
        source="senate_trading",
        ssh_target="oracle-arm1",
        worker_label="oracle-arm1-overseas-fallback",
        output_path=output_path,
        request_id="remote-test",
        command_runner=runner,
        stamp="20260707T001000Z",
    )

    assert isinstance(result, RemoteRunResult)
    assert result.status == "success"
    assert result.cleanup == "cleanup_ok"
    assert result.cleanup_verify == "remote_stage_absent"
    assert any("mkdir -p /tmp/openclaw-intel-worker-20260707T001000Z" in " ".join(cmd) for cmd in runner.commands)
    assert any("scripts/intel_worker_cli.py" in " ".join(cmd) for cmd in runner.commands)
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["worker"] == "oracle-arm1-overseas-fallback"
    assert saved["response"]["items"][0]["ticker"] == "BYND"
    assert saved["rollback"] == "rm -rf /tmp/openclaw-intel-worker-20260707T001000Z"


def test_remote_runner_uses_system_python_without_venv_when_no_pip_packages(tmp_path):
    runner = _FakeRunner()
    output_path = tmp_path / "remote-system-python.json"

    result = run_remote_worker_request(
        source="senate_trading",
        ssh_target="oracle-sg-west",
        worker_label="oracle-sg-west-preferred-overseas",
        output_path=output_path,
        request_id="remote-system-python-test",
        command_runner=runner,
        stamp="20260707T002222Z",
    )

    assert result.status == "success"
    exec_commands = [" ".join(cmd) for cmd in runner.commands if "scripts/intel_worker_cli.py" in " ".join(cmd)]
    assert len(exec_commands) == 1
    assert "python3 -m venv" not in exec_commands[0]
    assert "python3 scripts/intel_worker_cli.py" in exec_commands[0]


def test_remote_runner_records_failure_but_still_cleans_up(tmp_path):
    class FailingRunner(_FakeRunner):
        def __call__(self, cmd: list[str], **kwargs):
            self.commands.append(cmd)
            joined = " ".join(cmd)
            if "scripts/intel_worker_cli.py" in joined:
                return _Completed(2, "", "boom")
            if "source_health" in joined:
                return _Completed(0, "{}\n", "")
            if "rm -rf" in joined:
                return _Completed(0, "cleanup_ok\n", "")
            return _Completed(0, "", "")

    output_path = tmp_path / "remote-failed.json"
    result = run_remote_worker_request(
        source="akshare",
        ssh_target="root@example",
        worker_label="yanhuoyun-domestic",
        output_path=output_path,
        request_id="remote-fail",
        command_runner=FailingRunner(),
        stamp="20260707T001111Z",
    )

    assert result.status == "failed"
    assert result.cleanup == "cleanup_ok"
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["remote_returncode"] == 2
    assert saved["stderr_excerpt"] == "boom"


def test_remote_runner_fails_fast_when_initial_ssh_stage_cannot_be_created(tmp_path):
    class MkirFailRunner(_FakeRunner):
        def __call__(self, cmd: list[str], **kwargs):
            self.commands.append(cmd)
            joined = " ".join(cmd)
            if "mkdir -p" in joined:
                return _Completed(255, "", "ssh: connect to host 149.118.53.164 port 22: Operation timed out")
            raise AssertionError(f"runner should fail fast after mkdir failure, got: {joined}")

    runner = MkirFailRunner()
    output_path = tmp_path / "remote-mkdir-failed.json"
    result = run_remote_worker_request(
        source="senate_trading",
        ssh_target="oracle-sg-west",
        worker_label="oracle-sg-west-preferred-overseas",
        output_path=output_path,
        request_id="remote-mkdir-fail",
        command_runner=runner,
        stamp="20260707T122005Z",
    )

    assert result.status == "failed"
    assert result.cleanup == "not_attempted_mkdir_failed"
    assert result.cleanup_verify == "not_applicable_mkdir_failed"
    assert len(runner.commands) == 1
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["remote_returncode"] == 255
    assert "Operation timed out" in saved["stderr_excerpt"]
    assert saved["response"]["stage_error"] == "mkdir_failed"


def test_remote_runner_script_help_executes_directly():
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "intel_worker_remote_run.py"), "--help"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "--ssh-target" in proc.stdout
