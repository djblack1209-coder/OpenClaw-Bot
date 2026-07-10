from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.intel.db.store import get_source_health
from src.intel.worker_contract import build_worker_request

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "intel_worker_cli.py"


def _run_cli(args: list[str], *, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )


def test_worker_cli_executes_request_from_stdin_and_records_db(tmp_path):
    db_path = tmp_path / "intel.db"
    request = build_worker_request("senate_trading", limit=1, request_id="cli-stdin")

    result = _run_cli(["--db", str(db_path)], stdin=request.to_json())

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["request_id"] == "cli-stdin"
    assert payload["source"] == "senate_trading"
    assert payload["status"] == "success"
    assert payload["raw_count"] == 1
    assert get_source_health(db_path, "senate_trading")["failure_count"] == 0


def test_worker_cli_executes_request_from_file(tmp_path):
    db_path = tmp_path / "intel.db"
    request_path = tmp_path / "request.json"
    request_path.write_text(build_worker_request("senate_trading", limit=1, request_id="cli-file").to_json(), encoding="utf-8")

    result = _run_cli(["--input", str(request_path), "--db", str(db_path)])

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["request_id"] == "cli-file"
    assert payload["status"] == "success"


def test_worker_cli_unknown_source_returns_nonzero_and_records_failure(tmp_path):
    db_path = tmp_path / "intel.db"
    request = build_worker_request("unknown_feed", limit=1, request_id="cli-unknown")

    result = _run_cli(["--db", str(db_path)], stdin=request.to_json())

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["error"] == "unsupported_source: unknown_feed"
    assert get_source_health(db_path, "unknown_feed")["failure_count"] == 1


def test_worker_cli_invalid_json_returns_parse_error():
    result = _run_cli([], stdin="not-json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "invalid request json" in result.stderr
