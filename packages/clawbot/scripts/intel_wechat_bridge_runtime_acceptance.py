"""Weixin ClawBot 每日简报真实桥接证据验收 CLI。

该脚本不读取微信聊天内容、不调用微信网络、不保存用户 ID。它只读取 OpenClaw
Weixin 插件桥写出的脱敏证据文件，判断最近一次真实入站快捷词是否已经完成：
微信 → 插件桥 → 本机 `/wechat/incoming` → 回发微信。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intel.wechat_bridge_runtime import (  # noqa: E402
    default_wechat_bridge_evidence_path,
    wait_for_wechat_bridge_runtime_acceptance,
)

DEFAULT_OUTPUT = ROOT / "data" / "intel_evidence" / "phasefix" / "wechat-bridge" / "acceptance.json"


def main() -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="验收 Weixin ClawBot 每日简报真实桥接证据")
    parser.add_argument(
        "--evidence",
        default=os.environ.get("OPENCLAW_INTEL_BRIEF_WECHAT_EVIDENCE_FILE", str(default_wechat_bridge_evidence_path())),
        help="OpenClaw Weixin 插件桥写出的脱敏证据文件",
    )
    parser.add_argument("--max-age-seconds", type=int, default=900, help="证据最大允许年龄")
    parser.add_argument("--wait-seconds", type=int, default=0, help="等待真实微信桥接证据出现的秒数；默认不等待")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="等待模式轮询间隔")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="验收报告输出路径")
    args = parser.parse_args()

    result = wait_for_wechat_bridge_runtime_acceptance(
        evidence_path=args.evidence,
        max_age_seconds=args.max_age_seconds,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("verified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
