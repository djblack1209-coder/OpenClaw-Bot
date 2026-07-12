"""项目源码快照必须脱敏、可校验，并能恢复到可丢弃目录。"""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_local_source_backup_and_disposable_restore_drill(tmp_path):
    repo_root = _repo_root()
    backup_dir = tmp_path / "backups"
    env = os.environ.copy()
    env["OPENCLAW_BACKUP_DIR"] = str(backup_dir)
    env["OPENCLAW_BACKUP_RETENTION_DAYS"] = "30"

    before_agents = hashlib.sha256((repo_root / "AGENTS.md").read_bytes()).hexdigest()
    backup = subprocess.run(
        ["bash", "scripts/local_backup.sh"],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert backup.returncode == 0, backup.stderr
    payload = json.loads(backup.stdout.strip().splitlines()[-1])
    archive = Path(payload["archive"])
    checksum_path = Path(payload["checksum_file"])
    assert archive.is_file()
    assert checksum_path.is_file()
    assert archive.stat().st_mode & 0o077 == 0
    assert checksum_path.stat().st_mode & 0o077 == 0
    expected_digest = checksum_path.read_text(encoding="utf-8").split()[0]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected_digest

    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getnames()
    assert "AGENTS.md" in members
    assert "Makefile" in members
    assert "scripts/local_backup.sh" in members
    assert all(not name.startswith("/") and ".." not in Path(name).parts for name in members)
    assert all("node_modules" not in Path(name).parts for name in members)
    assert all(
        Path(name).name.endswith(".env.example") or not Path(name).name.startswith(".env")
        for name in members
    )
    assert all(Path(name).suffix not in {".db", ".sqlite", ".sqlite3"} for name in members)

    restore_dir = tmp_path / "restored-source"
    restore = subprocess.run(
        [
            "bash",
            "scripts/disaster_recovery.sh",
            "--archive",
            str(archive),
            "--target-dir",
            str(restore_dir),
            "--confirm",
        ],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert restore.returncode == 0, restore.stderr
    restore_payload = json.loads(restore.stdout.strip().splitlines()[-1])
    assert restore_payload["ok"] is True
    assert restore_payload["checksum_verified"] is True
    assert restore_payload["target_is_project_root"] is False
    assert (restore_dir / "AGENTS.md").is_file()
    assert (restore_dir / "Makefile").is_file()
    assert hashlib.sha256((repo_root / "AGENTS.md").read_bytes()).hexdigest() == before_agents


def _write_checksum(archive: Path, digest: str | None = None) -> Path:
    """为测试归档生成与生产脚本一致的 SHA-256 sidecar。"""
    checksum = Path(f"{archive}.sha256")
    checksum.write_text(
        f"{digest or hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n",
        encoding="utf-8",
    )
    return checksum


def _run_restore(repo_root: Path, archive: Path, target: Path) -> subprocess.CompletedProcess[str]:
    """执行只写可丢弃目录的源码恢复。"""
    return subprocess.run(
        [
            "bash",
            "scripts/disaster_recovery.sh",
            "--archive",
            str(archive),
            "--target-dir",
            str(target),
            "--confirm",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_source_restore_rejects_checksum_mismatch(tmp_path):
    repo_root = _repo_root()
    archive = tmp_path / "openeverything-corrupt.tgz"
    with tarfile.open(archive, "w:gz") as bundle:
        payload = b"safe"
        member = tarfile.TarInfo("AGENTS.md")
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))
    _write_checksum(archive, "0" * 64)

    target = tmp_path / "checksum-target"
    restore = _run_restore(repo_root, archive, target)

    assert restore.returncode != 0
    assert json.loads(restore.stdout.strip().splitlines()[-1])["error"] == "backup_checksum_mismatch"
    assert not target.exists()


def test_source_restore_rejects_path_traversal_before_writing(tmp_path):
    repo_root = _repo_root()
    archive = tmp_path / "openeverything-traversal.tgz"
    with tarfile.open(archive, "w:gz") as bundle:
        payload = b"must-not-escape"
        member = tarfile.TarInfo("../escaped.txt")
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))
    _write_checksum(archive)

    target = tmp_path / "traversal-target"
    restore = _run_restore(repo_root, archive, target)

    assert restore.returncode != 0
    assert json.loads(restore.stdout.strip().splitlines()[-1])["error"] == "unsafe_archive_path"
    assert not target.exists()
    assert not (tmp_path / "escaped.txt").exists()


def test_source_backup_refuses_concurrent_run(tmp_path):
    repo_root = _repo_root()
    backup_dir = tmp_path / "locked-backups"
    backup_dir.mkdir()
    lock_path = backup_dir / ".source-backup.lock"
    env = os.environ.copy()
    env["OPENCLAW_BACKUP_DIR"] = str(backup_dir)

    with lock_path.open("a+") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = subprocess.run(
            ["bash", "scripts/local_backup.sh"],
            cwd=repo_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )

    assert backup.returncode == 73
    assert json.loads(backup.stdout.strip().splitlines()[-1])["error"] == "source_backup_already_running"
    assert not list(backup_dir.glob("openeverything-*.tgz"))
