import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "final_audit.py"


def _load_module():
    assert AUDIT_SCRIPT.exists(), "统一最终审计入口尚未实现"
    spec = importlib.util.spec_from_file_location("openclaw_final_audit", AUDIT_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_final_audit_report_never_embeds_raw_process_output(tmp_path) -> None:
    audit = _load_module()
    checks = [
        audit.AuditCheck(
            name="safe-success",
            category="test",
            command=(sys.executable, "-c", "print('token=do-not-store')"),
            timeout_seconds=10,
        ),
        audit.AuditCheck(
            name="safe-failure",
            category="test",
            command=(sys.executable, "-c", "import sys; print('password=do-not-store'); sys.exit(3)"),
            timeout_seconds=10,
        ),
    ]

    results = audit.run_checks(checks, cwd=tmp_path)
    report = audit.build_report(results, started_at="2026-07-12T00:00:00+00:00", duration_seconds=0.25)
    serialized = json.dumps(report, ensure_ascii=False)

    assert [item["status"] for item in report["checks"]] == ["passed", "failed"]
    assert report["summary"] == {"total": 2, "passed": 1, "failed": 1, "skipped": 0}
    assert "do-not-store" not in serialized
    assert "token=" not in serialized
    assert "password=" not in serialized


def test_final_audit_scrubs_credentials_and_private_home_path() -> None:
    audit = _load_module()

    scrubbed = audit.scrub_text(
        "Authorization: Bearer private-value token=private-token /Users/blackdj/secret/file",
        home=Path("/Users/blackdj"),
    )

    assert "private-value" not in scrubbed
    assert "private-token" not in scrubbed
    assert "/Users/blackdj" not in scrubbed
    assert "<redacted>" in scrubbed
    assert "~/secret/file" in scrubbed


def test_default_final_audit_covers_all_offline_quality_and_security_gates(tmp_path) -> None:
    audit = _load_module()
    checks = audit.build_default_checks(
        repo_root=REPO_ROOT,
        python_executable=sys.executable,
        temp_dir=tmp_path,
    )
    names = {check.name for check in checks}

    assert {
        "git-diff-check",
        "docs-governance",
        "python-ruff",
        "python-syntax",
        "python-tests",
        "frontend-eslint",
        "frontend-typescript",
        "frontend-static-contracts",
        "frontend-build",
        "chrome-extension-safety-tests",
        "frist-api-tests",
        "gitleaks-working-tree",
        "gitleaks-history",
        "python-dependency-audit",
        "frontend-dependency-audit",
        "frist-api-dependency-audit",
        "backup-restore-contract",
        "runtime-permissions-contract",
        "runtime-permissions-local",
        "renewal-reminder-contract",
    } <= names


def test_worktree_secret_scan_uses_git_owned_snapshot_and_excludes_ignored_files(tmp_path) -> None:
    """当前树密钥扫描只覆盖 Git 管理或待纳入的项目文件，不递归第三方 submodule/忽略目录。"""
    audit = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text("ignored.txt\nignored-dir/\n", encoding="utf-8")
    (repo / "tracked.txt").write_text("tracked", encoding="utf-8")
    (repo / "untracked.txt").write_text("untracked", encoding="utf-8")
    (repo / "ignored.txt").write_text("ignored", encoding="utf-8")
    (repo / "ignored-dir").mkdir()
    (repo / "ignored-dir" / "secret.txt").write_text("ignored", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "tracked.txt"], cwd=repo, check=True)

    snapshot = tmp_path / "snapshot"
    copied = audit.prepare_worktree_snapshot(repo, snapshot)

    assert copied == 3
    assert (snapshot / ".gitignore").is_file()
    assert (snapshot / "tracked.txt").is_file()
    assert (snapshot / "untracked.txt").is_file()
    assert not (snapshot / "ignored.txt").exists()
    assert not (snapshot / "ignored-dir").exists()

    checks = audit.build_default_checks(
        repo_root=repo,
        python_executable=sys.executable,
        temp_dir=tmp_path,
        worktree_scan_root=snapshot,
    )
    gitleaks = next(check for check in checks if check.name == "gitleaks-working-tree")
    assert gitleaks.command[-1] == str(snapshot)
