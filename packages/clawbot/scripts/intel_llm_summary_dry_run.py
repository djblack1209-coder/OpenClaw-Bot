"""Build Intel Brief LLM summary dry-run evidence from brief dry-run JSON."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.llm_summary import DEFAULT_PROFILE, build_llm_summary_dry_run  # noqa: E402
from src.llm_routing_config import get_routing_profile, load_routing_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Intel Brief LLM summary dry-run evidence")
    parser.add_argument("--dry-run-json", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--stamp")
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--mode", choices=["real", "fallback-only"], default="real")
    parser.add_argument("--family", help="Override model family, e.g. intel_local for local Ollama dry-run")
    parser.add_argument("--max-tokens", type=int, help="Override profile max_tokens for bounded dry-run calls")
    args = parser.parse_args(argv)

    profile = None
    if args.max_tokens is not None:
        profile = get_routing_profile(load_routing_config(), args.profile)
        profile["max_tokens"] = max(1, int(args.max_tokens))

    result = asyncio.run(
        build_llm_summary_dry_run(
            dry_run_json_path=args.dry_run_json,
            markdown_output_path=args.markdown_output,
            json_output_path=args.json_output,
            stamp=args.stamp,
            profile_name=args.profile,
            profile=profile,
            llm_attempted=args.mode == "real",
            family_override=args.family,
        )
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "llm": {
                    "attempted": result["llm"]["llm_attempted"],
                    "success": result["llm"]["llm_success"],
                    "family": result["llm"]["model_family"],
                    "usage": result["llm"]["usage"],
                },
                "markdown_output": args.markdown_output,
                "json_output": args.json_output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] in {"success", "partial_fallback"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
