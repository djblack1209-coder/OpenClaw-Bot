"""Intel Brief Phase B worker 证据脚手架。

该脚本只生成/写入验证证据 JSON，不直接连接服务器、不读取密钥、不触发部署。
真实远端调用由后续 SSH 命令执行后，把脱敏样本填入本结构。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.intel.runtime_policy import resolve_runtime_policy

EVIDENCE_SCHEMA = "intel_phaseb_probe_v1"


def build_probe_result(
    source: str,
    *,
    status: str = "not_run",
    sample: str = "",
    limit: str = "not_verified",
    worker_override: str | None = None,
    evidence_path: str = "",
    error: str = "",
) -> dict[str, Any]:
    """构造统一 Phase B 验证证据，不包含密钥或 Cookie。"""
    policy = resolve_runtime_policy(source)
    worker = worker_override or policy.preferred_worker
    return {
        "evidence_schema": EVIDENCE_SCHEMA,
        "source": policy.source_name or str(source),
        "worker": worker,
        "region_hint": policy.region_hint,
        "requires_overseas_egress": policy.requires_overseas_egress,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),  # noqa: UP017 - Python 3.10 worker compatibility
        "status": status,
        "sample": sample,
        "limit": limit,
        "policy_reason": policy.reason,
        "evidence_path": evidence_path,
        "error": error,
    }


def write_probe_result(
    source: str,
    output_path: str | Path,
    *,
    status: str = "not_run",
    sample: str = "",
    limit: str = "not_verified",
    worker_override: str | None = None,
    error: str = "",
) -> dict[str, Any]:
    """把 Phase B 验证证据写入 JSON 文件。"""
    path = Path(output_path)
    result = build_probe_result(
        source,
        status=status,
        sample=sample,
        limit=limit,
        worker_override=worker_override,
        evidence_path=str(path),
        error=error,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    """命令行入口：生成一条证据 JSON。"""
    parser = argparse.ArgumentParser(description="Write Intel Brief Phase B probe evidence JSON")
    parser.add_argument("source")
    parser.add_argument("output_path")
    parser.add_argument("--status", default="not_run")
    parser.add_argument("--sample", default="")
    parser.add_argument("--limit", default="not_verified")
    parser.add_argument("--worker-override", default=None)
    parser.add_argument("--error", default="")
    args = parser.parse_args()
    result = write_probe_result(
        args.source,
        args.output_path,
        status=args.status,
        sample=args.sample,
        limit=args.limit,
        worker_override=args.worker_override,
        error=args.error,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
