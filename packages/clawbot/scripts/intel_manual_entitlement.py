"""Grant or preview Intel Brief manual subscription entitlement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.manual_entitlement import DEFAULT_MANUAL_PLAN, grant_manual_entitlement  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grant or preview Intel Brief manual entitlement")
    parser.add_argument("--db", default=str(ROOT / "data" / "intel_brief.db"))
    parser.add_argument("--telegram-user-id", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--order-ref", required=True)
    parser.add_argument("--duration-days", type=int, default=30)
    parser.add_argument("--plan-name", default=DEFAULT_MANUAL_PLAN)
    parser.add_argument("--category", action="append", dest="categories")
    parser.add_argument("--starts-at", default="")
    parser.add_argument("--source", default="manual_order")
    parser.add_argument("--delivery-time", default="08:30")
    parser.add_argument("--timezone", default="America/Denver")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--evidence", default="")
    args = parser.parse_args(argv)

    result = grant_manual_entitlement(
        db_path=args.db,
        telegram_user_id=args.telegram_user_id,
        chat_id=args.chat_id,
        order_ref=args.order_ref,
        duration_days=args.duration_days,
        plan_name=args.plan_name,
        categories=args.categories,
        starts_at=args.starts_at or None,
        source=args.source,
        apply=args.apply,
        delivery_time=args.delivery_time,
        timezone_name=args.timezone,
    )
    if args.evidence:
        evidence_path = Path(args.evidence)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "applied": result["applied"],
                "plan_name": result["planned"]["plan_name"],
                "expires_at": result["planned"]["expires_at"],
                "categories": result["planned"]["categories"],
                "network_calls": result["network_calls"],
                "evidence": args.evidence,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"dry_run", "success"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
