"""Run an Intel Brief worker bundle on a remote host with cleanup evidence.

This script codifies the temporary staging pattern used for Phase E evidence:
build a minimal bundle, stage it under /tmp, execute one worker request, query
source_health, remove the staging directory, and write a JSON evidence file. It
is not a service deployer and does not create systemd/cron/config/secret files.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.intel_worker_bundle import build_worker_bundle  # noqa: E402
from src.intel.worker_contract import build_worker_request  # noqa: E402

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class RemoteRunResult:
    status: str
    evidence_path: str
    cleanup: str
    cleanup_verify: str


def _default_runner(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False, **kwargs)


def _run_ssh(
    runner: CommandRunner,
    ssh_target: str,
    remote_command: str,
    *,
    ssh_args: list[str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return runner(["ssh", *(ssh_args or []), ssh_target, remote_command], input=stdin)


def _json_or_raw(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    return {"raw": stripped}


def _build_tarball(bundle_dir: Path, tar_path: Path) -> None:
    with tarfile.open(tar_path, "w:gz") as tar:
        for child in bundle_dir.iterdir():
            tar.add(child, arcname=child.name)


def run_remote_worker_request(
    *,
    source: str,
    ssh_target: str,
    worker_label: str,
    output_path: str | Path,
    request_id: str,
    limit: int = 1,
    ssh_args: list[str] | None = None,
    remote_python: str = "python3",
    pip_packages: list[str] | None = None,
    command_runner: CommandRunner = _default_runner,
    stamp: str | None = None,
) -> RemoteRunResult:
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017 - Python 3.10 worker compatibility
    remote_dir = f"/tmp/openclaw-intel-worker-{stamp}"
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    ssh_args = list(ssh_args or [])
    pip_packages = list(pip_packages or [])

    request_json = build_worker_request(source, limit=limit, request_id=request_id).to_json()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bundle_dir = tmp_path / "bundle"
        tar_path = tmp_path / "bundle.tgz"
        manifest = build_worker_bundle(bundle_dir)
        _build_tarball(bundle_dir, tar_path)

        mkdir = _run_ssh(command_runner, ssh_target, f"rm -rf {remote_dir} && mkdir -p {remote_dir}", ssh_args=ssh_args)
        if mkdir.returncode == 0:
            # Use base64-free streaming via tar over ssh in the real runner. Tests can
            # ignore the tar command output because command_runner is injectable.
            if command_runner is _default_runner:
                with tar_path.open("rb") as fh:
                    subprocess.run(
                        ["ssh", *ssh_args, ssh_target, f"tar -xzf - -C {remote_dir}"],
                        stdin=fh,
                        text=False,
                        capture_output=True,
                        check=False,
                    )
            else:
                command_runner(["tar-stream", str(tar_path), ssh_target, remote_dir])
        else:
            cleanup = "not_attempted_mkdir_failed"
            cleanup_verify = "not_applicable_mkdir_failed"
            evidence = {
                "timestamp": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Python 3.10 worker compatibility
                "phase": "E",
                "scope": "remote_worker_runner_execution",
                "status": "failed",
                "worker": worker_label,
                "source": source,
                "remote_stage_dir": remote_dir,
                "remote_returncode": mkdir.returncode,
                "response": {"status": "failed", "stage_error": "mkdir_failed"},
                "stderr_excerpt": (mkdir.stderr or "").strip()[:1000],
                "source_health": {},
                "cleanup": cleanup,
                "cleanup_verify": cleanup_verify,
                "rollback": f"rm -rf {remote_dir}",
                "bundle_manifest": manifest,
                "limits": [
                    "Temporary /tmp staging only; not a production service deployment.",
                    "Initial SSH staging failed; runner fails fast to avoid repeated SSH timeouts.",
                    "No systemd unit, cron, production config, token, cookie, or persistent project checkout is created.",
                ],
            }
            output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            return RemoteRunResult(
                status="failed",
                evidence_path=str(output),
                cleanup=cleanup,
                cleanup_verify=cleanup_verify,
            )

    if pip_packages:
        install = f" {remote_dir}/venv/bin/python -m pip install -q " + " ".join(pip_packages) + ";"
        remote_exec = (
            f"set -e; cd {remote_dir}; {remote_python} -m venv venv;"
            f"{install} {remote_dir}/venv/bin/python scripts/intel_worker_cli.py --db {remote_dir}/intel_worker.db"
        )
    else:
        remote_exec = f"set -e; cd {remote_dir}; {remote_python} scripts/intel_worker_cli.py --db {remote_dir}/intel_worker.db"
    run = _run_ssh(command_runner, ssh_target, remote_exec, ssh_args=ssh_args, stdin=request_json)
    health_query = (
        f"python3 - <<'PY'\n"
        "import json, sqlite3\n"
        "from pathlib import Path\n"
        f"p=Path('{remote_dir}/intel_worker.db')\n"
        "if not p.exists():\n    print('{}')\n"
        "else:\n"
        "    conn=sqlite3.connect(p)\n"
        f"    row=conn.execute('select source_name,last_success_at,last_failure_at,last_failure_reason,failure_count,updated_at from source_health where source_name=?', ('{source}',)).fetchone()\n"
        "    print(json.dumps(dict(zip(['source_name','last_success_at','last_failure_at','last_failure_reason','failure_count','updated_at'], row)) if row else {}, ensure_ascii=False))\n"
        "PY"
    )
    health = _run_ssh(command_runner, ssh_target, health_query, ssh_args=ssh_args)
    cleanup = _run_ssh(
        command_runner,
        ssh_target,
        f"rm -rf {remote_dir} && if [ ! -e {remote_dir} ]; then echo cleanup_ok; else echo cleanup_failed; fi",
        ssh_args=ssh_args,
    )
    verify = _run_ssh(
        command_runner,
        ssh_target,
        f"if [ ! -e {remote_dir} ]; then echo remote_stage_absent; else echo remote_stage_still_exists; fi",
        ssh_args=ssh_args,
    )

    response = _json_or_raw(run.stdout)
    status = "success" if run.returncode == 0 and response.get("status") == "success" else "failed"
    evidence = {
        "timestamp": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Python 3.10 worker compatibility
        "phase": "E",
        "scope": "remote_worker_runner_execution",
        "status": status,
        "worker": worker_label,
        "source": source,
        "remote_stage_dir": remote_dir,
        "remote_returncode": run.returncode,
        "response": response,
        "stderr_excerpt": (run.stderr or "").strip()[:1000],
        "source_health": _json_or_raw(health.stdout),
        "cleanup": (cleanup.stdout or "").strip(),
        "cleanup_verify": (verify.stdout or "").strip(),
        "rollback": f"rm -rf {remote_dir}",
        "bundle_manifest": manifest,
        "limits": [
            "Temporary /tmp staging only; not a production service deployment.",
            "No systemd unit, cron, production config, token, cookie, or persistent project checkout is created.",
            "Cleanup command removes the remote staging directory after evidence collection.",
        ],
    }
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return RemoteRunResult(status=status, evidence_path=str(output), cleanup=evidence["cleanup"], cleanup_verify=evidence["cleanup_verify"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Intel Brief worker bundle on a remote host temporarily")
    parser.add_argument("--source", required=True)
    parser.add_argument("--ssh-target", required=True)
    parser.add_argument("--worker-label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--ssh-arg", action="append", default=[])
    parser.add_argument("--pip-package", action="append", default=[])
    args = parser.parse_args(argv)
    result = run_remote_worker_request(
        source=args.source,
        ssh_target=args.ssh_target,
        worker_label=args.worker_label,
        output_path=args.output,
        request_id=args.request_id,
        limit=args.limit,
        ssh_args=args.ssh_arg,
        pip_packages=args.pip_package,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, sort_keys=True))
    return 0 if result.status == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
