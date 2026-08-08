"""JIYU Sub2 本地补号助手命令行入口。"""

from __future__ import annotations

import argparse

from .app import run


def main() -> None:
    parser = argparse.ArgumentParser(description="启动只绑定 127.0.0.1 的 JIYU Sub2 补号助手")
    parser.add_argument("--dry-run", action="store_true", help="只验证粘贴、解析和页面，不登录或创建账号")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
