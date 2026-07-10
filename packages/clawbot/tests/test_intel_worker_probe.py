import json
from pathlib import Path

from scripts.intel_worker_probe import build_probe_result, write_probe_result


def test_build_probe_result_routes_domestic_source_to_domestic_worker():
    result = build_probe_result("xiaohongshu", status="not_run")

    assert result["source"] == "xiaohongshu"
    assert result["worker"] == "domestic"
    assert result["region_hint"] == "cn"
    assert result["status"] == "not_run"
    assert result["limit"] == "not_verified"


def test_build_probe_result_routes_overseas_source_to_overseas_worker():
    result = build_probe_result("sec_edgar", status="success", sample="13F-HR")

    assert result["source"] == "sec_edgar"
    assert result["worker"] == "overseas"
    assert result["region_hint"] == "global"
    assert result["status"] == "success"
    assert result["sample"] == "13F-HR"


def test_write_probe_result_creates_json_evidence(tmp_path: Path):
    output_path = tmp_path / "probe.json"

    result = write_probe_result("senate_trading", output_path, status="success", sample="BYND")

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == result
    assert saved["worker"] == "overseas"
    assert saved["evidence_schema"] == "intel_phaseb_probe_v1"
