#!/usr/bin/env python3
"""OpenClaw 统一离线最终审计入口。

只运行确定性的本地质量门和供应链扫描，不连接真实 Bot、交易、发货或社媒写入链路。
报告只保存状态、退出码和耗时，不保存子进程原始输出，避免把密钥或隐私带进证据文件。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence


REPORT_VERSION = 1
DEFAULT_JSON_OUTPUT = Path("output/final-audit/latest.json")
DEFAULT_SUMMARY_OUTPUT = Path("output/final-audit/latest.txt")


@dataclass(frozen=True)
class AuditCheck:
    """描述一个不会触发真实外部业务写入的审计项。"""

    name: str
    category: str
    command: tuple[str, ...]
    timeout_seconds: int
    skip_reason: str = ""


@dataclass(frozen=True)
class AuditResult:
    """保存单项执行结果；原始输出只留在内存中的脱敏诊断，不写报告。"""

    name: str
    category: str
    status: str
    exit_code: int | None
    duration_seconds: float
    diagnostic: str = ""
    skip_reason: str = ""


_AUTHORIZATION_RE = re.compile(r"(?i)\bauthorization\s*:\s*(?:bearer\s+)?[^\s,;]+")
_CREDENTIAL_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|cookie|session)"
    r"\s*[:=]\s*[^\s,;]+"
)
_LONG_SECRET_RE = re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs]|AIza)[-_A-Za-z0-9]{12,}\b")


def utc_now_iso() -> str:
    """返回不依赖本机时区的证据时间。"""
    return datetime.now(UTC).isoformat(timespec="seconds")


def scrub_text(value: str, *, home: Path | None = None, limit: int = 1200) -> str:
    """脱敏失败摘要；不会把该摘要写入机器报告。"""
    text = str(value or "")
    text = _AUTHORIZATION_RE.sub("Authorization: <redacted>", text)
    text = _CREDENTIAL_RE.sub("<credential>=<redacted>", text)
    text = _LONG_SECRET_RE.sub("<redacted>", text)
    home_path = str(home or Path.home())
    if home_path:
        text = text.replace(home_path, "~")
    compact = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    return compact[-limit:]


def _command_exists(command: str, *, cwd: Path) -> bool:
    """判断命令是否可执行，支持绝对路径和 PATH 命令。"""
    candidate = Path(command)
    if candidate.is_absolute() or "/" in command:
        resolved = candidate if candidate.is_absolute() else cwd / candidate
        return resolved.is_file() and os.access(resolved, os.X_OK)
    return shutil.which(command) is not None


def _diagnostic_from_process(stdout: str, stderr: str) -> str:
    """只为当前终端排障生成短脱敏摘要，不进入 JSON/TXT 证据。"""
    combined = "\n".join(part for part in (stdout, stderr) if part)
    return scrub_text(combined)


def prepare_worktree_snapshot(repo_root: Path, destination: Path) -> int:
    """复制 Git 管理和待纳入的普通文件，避免扫描忽略目录与固定上游 submodule。"""
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for raw_path in completed.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = Path(os.fsdecode(raw_path))
        if relative.is_absolute() or ".." in relative.parts:
            continue
        source = repo_root / relative
        # submodule 是目录；依赖目录符号链接也不应被递归复制到本项目密钥扫描面。
        if source.is_symlink() or not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied += 1
    return copied


def run_checks(
    checks: Sequence[AuditCheck],
    *,
    cwd: Path,
    show_progress: bool = False,
) -> list[AuditResult]:
    """顺序运行审计项；任何失败都会保留并继续，以便一次看到完整失败清单。"""
    results: list[AuditResult] = []
    base_env = os.environ.copy()
    base_env.update(
        {
            "TESTING": "true",
            "LITELLM_LOG": "ERROR",
            "OPENCLAW_FINAL_AUDIT": "1",
        }
    )
    total = len(checks)
    for index, check in enumerate(checks, start=1):
        if show_progress:
            print(f"[{index}/{total}] {check.name} ...", flush=True)
        if check.skip_reason:
            result = AuditResult(
                name=check.name,
                category=check.category,
                status="skipped",
                exit_code=None,
                duration_seconds=0.0,
                skip_reason=check.skip_reason,
            )
            results.append(result)
            if show_progress:
                print(f"  SKIP: {check.skip_reason}", flush=True)
            continue
        if not check.command or not _command_exists(check.command[0], cwd=cwd):
            result = AuditResult(
                name=check.name,
                category=check.category,
                status="failed",
                exit_code=127,
                duration_seconds=0.0,
                diagnostic=f"缺少必需命令：{check.command[0] if check.command else '<empty>'}",
            )
            results.append(result)
            if show_progress:
                print(f"  FAIL: {result.diagnostic}", flush=True)
            continue

        started = time.monotonic()
        try:
            completed = subprocess.run(
                check.command,
                cwd=cwd,
                env=base_env,
                text=True,
                capture_output=True,
                timeout=check.timeout_seconds,
                check=False,
            )
            duration = time.monotonic() - started
            status = "passed" if completed.returncode == 0 else "failed"
            diagnostic = "" if status == "passed" else _diagnostic_from_process(completed.stdout, completed.stderr)
            result = AuditResult(
                name=check.name,
                category=check.category,
                status=status,
                exit_code=int(completed.returncode),
                duration_seconds=duration,
                diagnostic=diagnostic,
            )
        except subprocess.TimeoutExpired as error:
            duration = time.monotonic() - started
            stdout = error.stdout if isinstance(error.stdout, str) else ""
            stderr = error.stderr if isinstance(error.stderr, str) else ""
            result = AuditResult(
                name=check.name,
                category=check.category,
                status="failed",
                exit_code=124,
                duration_seconds=duration,
                diagnostic=_diagnostic_from_process(stdout, stderr) or f"超过 {check.timeout_seconds} 秒超时",
            )
        results.append(result)
        if show_progress:
            print(f"  {result.status.upper()} ({result.duration_seconds:.2f}s)", flush=True)
            if result.status == "failed" and result.diagnostic:
                print(f"  脱敏诊断：{result.diagnostic}", flush=True)
    return results


def build_default_checks(
    *,
    repo_root: Path,
    python_executable: str,
    temp_dir: Path,
    worktree_scan_root: Path | None = None,
) -> list[AuditCheck]:
    """构建统一离线门；所有命令都只读源码或写入可丢弃构建/临时目录。"""
    python_value = str(Path(python_executable).expanduser())
    make_python = f"PYTHON={python_value}"
    gitleaks_worktree_report = temp_dir / "gitleaks-working-tree.json"
    gitleaks_history_report = temp_dir / "gitleaks-history.json"
    scan_root = worktree_scan_root or repo_root
    return [
        AuditCheck("git-diff-check", "repository", ("git", "diff", "--check"), 30),
        AuditCheck(
            "git-submodules",
            "repository",
            (
                "bash",
                "-c",
                "git submodule status --recursive | grep -E '^[+-U]' >/dev/null && exit 1; "
                "git submodule foreach --quiet --recursive "
                "'test -z \"$(git status --porcelain --untracked-files=all)\"'",
            ),
            60,
        ),
        AuditCheck("docs-governance", "documentation", ("make", "ci-docs"), 60),
        AuditCheck("python-ruff", "python", ("make", "lint", make_python), 180),
        AuditCheck("python-syntax", "python", ("make", "syntax-check", make_python), 180),
        AuditCheck("python-tests", "python", ("make", "test-ci", make_python), 600),
        AuditCheck(
            "backup-restore-contract",
            "recovery",
            ("make", "backup-restore-test", make_python),
            120,
        ),
        AuditCheck(
            "runtime-permissions-contract",
            "security",
            ("make", "runtime-permissions-test", make_python),
            60,
        ),
        AuditCheck(
            "runtime-permissions-local",
            "security",
            ("make", "runtime-permissions-check", make_python),
            120,
        ),
        AuditCheck(
            "renewal-reminder-contract",
            "operations",
            ("make", "renewals-check", make_python),
            60,
        ),
        AuditCheck("frontend-eslint", "frontend", ("make", "frontend-lint"), 240),
        AuditCheck("frontend-typescript", "frontend", ("make", "typecheck"), 240),
        AuditCheck(
            "frontend-static-contracts",
            "frontend",
            ("make", "frontend-static-test"),
            120,
        ),
        AuditCheck("frontend-build", "frontend", ("make", "frontend-build"), 360),
        AuditCheck(
            "chrome-extension-safety-tests",
            "frontend",
            ("make", "chrome-extension-test"),
            120,
        ),
        AuditCheck("frist-api-tests", "frist-api", ("make", "frist-api-test"), 240),
        AuditCheck(
            "gitleaks-working-tree",
            "security",
            (
                "gitleaks",
                "dir",
                "--redact",
                "--no-banner",
                "--no-color",
                "--report-format=json",
                f"--report-path={gitleaks_worktree_report}",
                str(scan_root),
            ),
            300,
        ),
        AuditCheck(
            "gitleaks-history",
            "security",
            (
                "gitleaks",
                "git",
                "--redact",
                "--no-banner",
                "--no-color",
                "--report-format=json",
                f"--report-path={gitleaks_history_report}",
                ".",
            ),
            600,
        ),
        AuditCheck(
            "python-dependency-audit",
            "security",
            (
                python_value,
                "-m",
                "pip_audit",
                "-r",
                "packages/clawbot/requirements.txt",
                "-r",
                "packages/clawbot/requirements-dev.txt",
                "--vulnerability-service",
                "pypi",
                "--progress-spinner",
                "off",
                "--cache-dir",
                str(temp_dir / "pip-audit-cache"),
                "--timeout",
                "10",
            ),
            600,
        ),
        AuditCheck(
            "frontend-dependency-audit",
            "security",
            ("npm", "audit", "--prefix", "apps/openclaw-manager-src", "--audit-level=high"),
            300,
        ),
        AuditCheck(
            "frist-api-dependency-audit",
            "security",
            ("npm", "audit", "--prefix", "apps/frist-api", "--audit-level=high"),
            300,
        ),
    ]


def build_report(results: Sequence[AuditResult], *, started_at: str, duration_seconds: float) -> dict:
    """生成只含状态、计数和耗时的机器报告。"""
    counts = {
        "total": len(results),
        "passed": sum(result.status == "passed" for result in results),
        "failed": sum(result.status == "failed" for result in results),
        "skipped": sum(result.status == "skipped" for result in results),
    }
    return {
        "version": REPORT_VERSION,
        "status": "ready" if counts["failed"] == 0 and counts["skipped"] == 0 else "blocked",
        "started_at": started_at,
        "generated_at": utc_now_iso(),
        "duration_seconds": round(float(duration_seconds), 3),
        "summary": counts,
        "checks": [
            {
                "name": result.name,
                "category": result.category,
                "status": result.status,
                "exit_code": result.exit_code,
                "duration_seconds": round(result.duration_seconds, 3),
                **({"skip_reason": result.skip_reason} if result.skip_reason else {}),
            }
            for result in results
        ],
    }


def write_report(report: dict, *, json_output: Path, summary_output: Path) -> None:
    """原子写入机器 JSON 和人类摘要，避免中断后留下半份绿色报告。"""
    json_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    json_tmp = json_output.with_suffix(f"{json_output.suffix}.tmp")
    summary_tmp = summary_output.with_suffix(f"{summary_output.suffix}.tmp")
    json_tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    lines = [
        f"OpenClaw final audit: {report['status']}",
        (
            f"total={summary['total']} passed={summary['passed']} "
            f"failed={summary['failed']} skipped={summary['skipped']} duration={report['duration_seconds']:.3f}s"
        ),
    ]
    lines.extend(
        f"- [{item['status']}] {item['name']} ({item['duration_seconds']:.3f}s)"
        for item in report["checks"]
    )
    summary_tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_tmp.replace(json_output)
    summary_tmp.replace(summary_output)


def _resolve_output(repo_root: Path, value: Path) -> Path:
    """把相对证据路径固定在仓库的已忽略 output 目录下。"""
    return value if value.is_absolute() else repo_root / value


def _default_python(repo_root: Path) -> str:
    """优先复用项目 Python 3.12 环境；缺失时回退 PATH。"""
    candidate = repo_root / "packages" / "clawbot" / ".venv312" / "bin" / "python"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    for command in ("python3.12", "python3"):
        found = shutil.which(command)
        if found:
            return found
    return "python3"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析命令行参数；不提供跳过失败的阈值开关。"""
    parser = argparse.ArgumentParser(description="运行 OpenClaw 脱敏统一离线最终审计")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--python", dest="python_executable", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """运行完整审计；任一失败或跳过都返回非零。"""
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    python_executable = args.python_executable or _default_python(repo_root)
    started_at = utc_now_iso()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="openclaw-final-audit-") as temp_path:
        temp_dir = Path(temp_path)
        worktree_scan_root = temp_dir / "git-owned-worktree"
        prepare_worktree_snapshot(repo_root, worktree_scan_root)
        checks = build_default_checks(
            repo_root=repo_root,
            python_executable=python_executable,
            temp_dir=temp_dir,
            worktree_scan_root=worktree_scan_root,
        )
        results = run_checks(checks, cwd=repo_root, show_progress=True)
    report = build_report(results, started_at=started_at, duration_seconds=time.monotonic() - started)
    json_output = _resolve_output(repo_root, args.json_output)
    summary_output = _resolve_output(repo_root, args.summary_output)
    write_report(report, json_output=json_output, summary_output=summary_output)
    summary = report["summary"]
    print(
        f"OpenClaw final audit: {report['status']} — "
        f"passed={summary['passed']} failed={summary['failed']} skipped={summary['skipped']}"
    )
    print(f"JSON: {json_output}")
    print(f"Summary: {summary_output}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
