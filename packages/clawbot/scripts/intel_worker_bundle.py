"""Build a minimal Intel Brief worker CLI bundle.

The bundle is designed for temporary target-node staging: copy it to a bounded
directory, run scripts/intel_worker_cli.py, collect evidence, then delete the
bundle directory as rollback cleanup. It does not include secrets, cookies,
configuration files, or service units.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BUNDLE_SCHEMA = "intel_worker_bundle_v1"

_REQUIRED_FILES = (
    "scripts/intel_worker_cli.py",
    "src/__init__.py",
    "src/intel/__init__.py",
    "src/intel/runtime_policy.py",
    "src/intel/worker_contract.py",
    "src/intel/worker_runner.py",
    "src/intel/db/__init__.py",
    "src/intel/db/store.py",
    "src/intel/db/intel_brief_schema.sql",
    "src/intel/sources/__init__.py",
    "src/intel/sources/ai_model_updates.py",
    "src/intel/sources/base.py",
    "src/intel/sources/astock_flow.py",
    "src/intel/sources/congress_trading.py",
    "src/intel/sources/github_trending.py",
    "src/intel/sources/institutional_13f.py",
    "src/intel/sources/weather_monitor.py",
    "src/intel/sources/registry.py",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_worker_bundle(bundle_dir: str | Path, *, project_root: str | Path | None = None) -> dict[str, Any]:
    """Copy the minimal worker runtime into `bundle_dir` and write a manifest."""
    root = Path(project_root) if project_root is not None else _project_root()
    output = Path(bundle_dir)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for rel in _REQUIRED_FILES:
        dst = output / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel == "src/__init__.py":
            dst.write_text("# Minimal package initializer for Intel worker bundle.\n", encoding="utf-8")
            copied.append(rel)
            continue
        src = root / rel
        if not src.exists():
            raise FileNotFoundError(f"required worker bundle file missing: {src}")
        shutil.copy2(src, dst)
        copied.append(rel)

    manifest = {
        "bundle_schema": BUNDLE_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Python 3.10 worker compatibility
        "files": copied,
        "secrets_included": False,
        "production_action": "none",
        "rollback": {
            "cleanup": f"rm -rf {output}",
            "notes": "Temporary worker bundle only; remove the staging directory to roll back.",
        },
    }
    (output / "intel_worker_bundle_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a minimal Intel Brief worker CLI bundle")
    parser.add_argument("bundle_dir")
    args = parser.parse_args(argv)
    manifest = build_worker_bundle(args.bundle_dir)
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
