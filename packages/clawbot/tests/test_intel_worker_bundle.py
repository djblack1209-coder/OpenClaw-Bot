from __future__ import annotations

import json
import subprocess
import sys

from scripts.intel_worker_bundle import build_worker_bundle


def test_build_worker_bundle_copies_cli_and_runtime_modules(tmp_path):
    bundle_dir = tmp_path / "intel-worker-bundle"

    manifest = build_worker_bundle(bundle_dir)

    assert (bundle_dir / "scripts" / "intel_worker_cli.py").is_file()
    assert (bundle_dir / "src" / "intel" / "worker_runner.py").is_file()
    assert (bundle_dir / "src" / "intel" / "sources" / "registry.py").is_file()
    assert (bundle_dir / "src" / "intel" / "db" / "intel_brief_schema.sql").is_file()
    assert manifest["bundle_schema"] == "intel_worker_bundle_v1"
    assert "scripts/intel_worker_cli.py" in manifest["files"]
    assert manifest["rollback"]["cleanup"] == f"rm -rf {bundle_dir}"


def test_worker_bundle_cli_runs_without_project_checkout(tmp_path):
    bundle_dir = tmp_path / "intel-worker-bundle"
    build_worker_bundle(bundle_dir)
    request = {
        "request_id": "bundle-unknown",
        "source": "unknown_feed",
        "worker": "controller",
        "region_hint": "auto",
        "limit": 1,
        "dispatch_mode": "remote_worker_contract",
        "metadata": {},
    }

    proc = subprocess.run(
        [sys.executable, str(bundle_dir / "scripts" / "intel_worker_cli.py")],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        cwd=bundle_dir,
        check=False,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["request_id"] == "bundle-unknown"
    assert payload["error"] == "unsupported_source: unknown_feed"


def test_worker_bundle_includes_verified_source_adapters(tmp_path):
    bundle_dir = tmp_path / "intel-worker-bundle"

    manifest = build_worker_bundle(bundle_dir)

    assert (bundle_dir / "src" / "intel" / "sources" / "astock_flow.py").is_file()
    assert (bundle_dir / "src" / "intel" / "sources" / "ai_model_updates.py").is_file()
    assert (bundle_dir / "src" / "intel" / "sources" / "github_trending.py").is_file()
    assert (bundle_dir / "src" / "intel" / "sources" / "institutional_13f.py").is_file()
    assert (bundle_dir / "src" / "intel" / "sources" / "weather_monitor.py").is_file()
    assert "src/intel/sources/astock_flow.py" in manifest["files"]
    assert "src/intel/sources/ai_model_updates.py" in manifest["files"]
    assert "src/intel/sources/github_trending.py" in manifest["files"]
    assert "src/intel/sources/institutional_13f.py" in manifest["files"]
    assert "src/intel/sources/weather_monitor.py" in manifest["files"]
