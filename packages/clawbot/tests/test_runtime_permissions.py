"""敏感运行文件权限检查不得读取内容，并且必须可重复修复。"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "harden_runtime_permissions.py"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_runtime_permission_audit_and_apply(tmp_path):
    runtime_home = tmp_path / "runtime-home"
    project_root = tmp_path / "project"
    runtime_home.mkdir(mode=0o755)
    project_root.mkdir()

    cookie_file = runtime_home / "x_cookies.json"
    cookie_file.write_text("must-not-appear", encoding="utf-8")
    cookie_file.chmod(0o644)
    memory_file = runtime_home / "memory" / "main.sqlite"
    memory_file.parent.mkdir()
    memory_file.write_bytes(b"private-db")
    memory_file.chmod(0o644)
    project_data = project_root / "packages" / "clawbot" / "data"
    project_data.mkdir(parents=True)
    state_file = project_data / "state.json"
    state_file.write_text("private-state", encoding="utf-8")
    state_file.chmod(0o644)
    rollback = project_data / "rollback.sh"
    rollback.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    rollback.chmod(0o755)

    env = os.environ.copy()
    env["OPENCLAW_RUNTIME_HOME"] = str(runtime_home)
    env["OPENCLAW_PROJECT_ROOT"] = str(project_root)

    check = subprocess.run(
        [str(SCRIPT), "--check"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert check.returncode == 1
    check_payload = json.loads(check.stdout)
    assert check_payload["violations"] >= 4
    assert "must-not-appear" not in check.stdout
    assert "private-state" not in check.stdout
    assert check_payload["contents_read"] is False

    apply = subprocess.run(
        [str(SCRIPT), "--apply"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert apply.returncode == 0, apply.stderr
    apply_payload = json.loads(apply.stdout)
    assert apply_payload["ok"] is True
    assert apply_payload["failed_changes"] == 0
    assert _mode(runtime_home) == 0o700
    assert _mode(cookie_file) == 0o600
    assert _mode(memory_file) == 0o600
    assert _mode(state_file) == 0o600
    assert _mode(rollback) == 0o700

    recheck = subprocess.run(
        [str(SCRIPT), "--check"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert recheck.returncode == 0
    assert json.loads(recheck.stdout)["violations"] == 0


def test_importing_clawbot_sets_private_default_umask(tmp_path):
    """ClawBot 进程新建的运行文件默认不得向同机其他账号开放。"""
    output = tmp_path / "runtime.json"
    probe = subprocess.run(
        [
            str(REPO_ROOT / "packages" / "clawbot" / ".venv312" / "bin" / "python"),
            "-c",
            (
                "import os,sys; from pathlib import Path; "
                "os.umask(0o022); sys.path.insert(0, 'packages/clawbot'); "
                "import src; Path(sys.argv[1]).write_text('safe', encoding='utf-8')"
            ),
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert probe.returncode == 0, probe.stderr
    assert _mode(output) == 0o600
