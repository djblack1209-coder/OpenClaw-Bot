#!/usr/bin/env python3
"""Audit each lock independently; preserve reports and fail after every scan.

Only public registry metadata is requested. npm audit reads temporary copies of
the manifests and locks and never installs into the active workspace.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def audit_environment(directory):
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}}
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("npmrc", "npm-globalrc"):
        (directory / name).write_text("")
    env.update(
        NPM_CONFIG_USERCONFIG=str(directory / "npmrc"),
        NPM_CONFIG_GLOBALCONFIG=str(directory / "npm-globalrc"),
        NPM_CONFIG_CACHE=str(directory / "npm-cache"),
        NPM_CONFIG_REGISTRY="https://registry.npmjs.org/",
        PYTHON_DOTENV_DISABLED="1",
        PYTHONNOUSERSITE="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
    )
    return env


def classify(kind, data):
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("invalid audit report")
    if kind == "npm":
        counts = data["metadata"]["vulnerabilities"]
        if not isinstance(counts, dict) or not {"high", "critical"} <= counts.keys():
            raise ValueError("missing npm counts")
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValueError("invalid npm counts")
        return counts, counts["high"] + counts["critical"] > 0
    if kind == "python":
        dependencies = data["dependencies"]
        if not isinstance(dependencies, list) or not dependencies:
            raise ValueError("missing Python dependencies")
        for package in dependencies:
            if (not isinstance(package, dict) or not package.get('name') or not package.get('version')
                    or not isinstance(package.get('vulns'), list)
                    or any(not isinstance(item, dict) or not item.get('id') for item in package['vulns'])):
                raise ValueError("invalid Python package report")
        count = sum(len(package["vulns"]) for package in dependencies)
        return {"packages": len(dependencies), "vulnerabilities": count}, count > 0
    vulnerabilities = data["vulnerabilities"]["count"]
    warnings = data["warnings"]
    if (type(vulnerabilities) is not int or vulnerabilities < 0 or not isinstance(warnings, dict)
            or any(not isinstance(items, list) for items in warnings.values())):
        raise ValueError("invalid RustSec report")
    return {
        "vulnerabilities": vulnerabilities,
        "warnings": sum(len(items) for items in warnings.values()),
        "warnings_by_kind": {key: len(items) for key, items in warnings.items()},
    }, vulnerabilities > 0


def run_audits(specs, output, *, runner=subprocess.run, timeout=180, env=None, versions=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in specs:
        row = {
            "name": spec["name"], "kind": spec["kind"], "command": spec["command"],
            "lock_sha256": hashlib.sha256(Path(spec["lock"]).read_bytes()).hexdigest(),
            "started_at": datetime.now(timezone.utc).isoformat(), "status": "incomplete",
            "tool_version": (versions or {}).get(spec["kind"], "not recorded"),
        }
        raw_path = output / f'{spec["name"]}.json'
        stderr_path = output / f'{spec["name"]}.stderr'
        row.update(report=str(raw_path), stderr=str(stderr_path))
        try:
            process = runner(spec["command"], cwd=spec["cwd"], env=env, text=True, capture_output=True, timeout=timeout)
            row["exit_code"] = process.returncode
            raw_path.write_text(process.stdout)
            stderr_path.write_text(process.stderr)
            try:
                data = json.loads(process.stdout)
                counts, failed_gate = classify(spec["kind"], data)
                row["counts"] = counts
                if process.returncode not in (0, 1) or (process.returncode == 1 and not failed_gate):
                    row["failure"] = "unexpected_exit"
                else:
                    row["status"] = "findings" if failed_gate else "passed"
            except (ValueError, KeyError, TypeError):
                row["failure"] = "invalid_report"
        except FileNotFoundError:
            row.update(exit_code=None, failure="tool_missing")
        except subprocess.TimeoutExpired as exc:
            row.update(exit_code=None, failure="timeout")
            for path, content in ((raw_path, exc.stdout), (stderr_path, exc.stderr)):
                path.write_text(content.decode(errors="replace") if isinstance(content, bytes) else content or "")
        except OSError as exc:
            row.update(exit_code=None, failure=type(exc).__name__)
        row["finished_at"] = datetime.now(timezone.utc).isoformat()
        results.append(row)
        print(f'{row["name"]}: {row["status"]}; exit={row.get("exit_code")}; {row.get("counts", row.get("failure"))}', flush=True)
    code = int(any(row["status"] != "passed" for row in results))
    (output / "summary.json").write_text(json.dumps({"exit_code": code, "results": results}, indent=2) + "\n")
    return results, code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--without-rust", action="store_true", help="Rust is audited by a separate CI job; report scope explicitly")
    args = parser.parse_args()
    args.python = os.path.abspath(args.python) if os.sep in args.python else (shutil.which(args.python) or args.python)
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir or Path(tempfile.mkdtemp(prefix="oe-dependency-audit-"))
    output.mkdir(parents=True, exist_ok=True)
    env = audit_environment(output / "tool-config")
    with tempfile.TemporaryDirectory(prefix="oe-audit-locks-") as temporary:
        work = Path(temporary)
        specs = []
        for name, relative in (
            ("desktop", "apps/openclaw-manager-src"),
            ("runtime", "apps/openclaw-manager-src/src-tauri/npm-runtime-lock"),
            ("weixin", ".openclaw/extensions/openclaw-weixin"),
        ):
            copied = work / name
            copied.mkdir()
            for file in ("package.json", "package-lock.json"):
                shutil.copyfile(root / relative / file, copied / file)
            for scope in ("all", "production"):
                command = ["npm", "audit", "--package-lock-only", "--prefix", str(copied), "--audit-level=high", "--json"]
                if scope == "production":
                    command.append("--omit=dev")
                specs.append({"name": f"{name}-{scope}", "kind": "npm", "command": command,
                              "lock": root / relative / "package-lock.json", "cwd": copied})
        for platform, file in (("linux", "requirements-lock.txt"), ("macos", "requirements-lock-macos.txt")):
            lock = root / "packages/clawbot" / file
            command = [args.python, "-m", "pip_audit", "--disable-pip", "--no-deps", "-r", str(lock),
                       "--vulnerability-service", "pypi", "--progress-spinner", "off", "--cache-dir", str(output / "pip-cache"),
                       "--timeout", "10", "--format", "json"]
            specs.append({"name": f"python-{platform}", "kind": "python", "command": command, "lock": lock, "cwd": work})
        if not args.without_rust:
            lock = root / "apps/openclaw-manager-src/src-tauri/Cargo.lock"
            specs.append({"name": "rust", "kind": "rust", "command": ["cargo", "audit", "--file", str(lock), "--json"],
                          "lock": lock, "cwd": work})
        versions = {}
        for kind, command in (("npm", ["npm", "--version"]), ("python", [args.python, "-m", "pip_audit", "--version"]),
                              ("rust", ["cargo", "audit", "--version"])):
            if kind == "rust" and args.without_rust:
                continue
            try:
                result = subprocess.run(command, text=True, capture_output=True, env=env, timeout=20)
                versions[kind] = result.stdout.strip() if result.returncode == 0 else "unavailable"
            except (OSError, subprocess.TimeoutExpired):
                versions[kind] = "unavailable"
        print(f'Audit scope: {"npm and Python; Rust remains in separate job" if args.without_rust else "all six groups"}', flush=True)
        print(f"Reports: {output}", flush=True)
        _, code = run_audits(specs, output, timeout=args.timeout, env=env, versions=versions)
        return code


if __name__ == "__main__":
    raise SystemExit(main())
