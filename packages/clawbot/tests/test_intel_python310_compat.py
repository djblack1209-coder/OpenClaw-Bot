from __future__ import annotations

from pathlib import Path


def test_intel_worker_bundle_runtime_avoids_datetime_utc_for_python310():
    root = Path(__file__).resolve().parents[1]
    checked = list((root / "src" / "intel").rglob("*.py")) + list((root / "scripts").glob("intel_worker_*.py"))

    offenders = [str(path.relative_to(root)) for path in checked if "from datetime import UTC" in path.read_text(encoding="utf-8")]

    assert offenders == []
