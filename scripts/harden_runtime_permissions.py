#!/usr/bin/env python3
"""只检查或收紧 OpenClaw 本机敏感运行文件权限，不读取文件内容。"""

from __future__ import annotations

import argparse
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class PermissionTarget:
    """记录需要检查的真实普通文件或目录。"""

    path: Path
    desired_mode: int
    is_directory: bool


def _project_root() -> Path:
    """允许测试和隔离工作区显式覆盖项目根目录。"""
    configured = os.environ.get("OPENCLAW_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _runtime_home() -> Path:
    """允许测试使用临时运行目录，默认使用当前用户的 ~/.openclaw。"""
    configured = os.environ.get("OPENCLAW_RUNTIME_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".openclaw").resolve()


def _desired_file_mode(path: Path) -> int:
    """敏感脚本保留仅所有者可执行，其他文件只允许所有者读写。"""
    current = stat.S_IMODE(path.lstat().st_mode)
    return 0o700 if current & 0o111 else 0o600


def _walk_private_tree(root: Path) -> Iterable[PermissionTarget]:
    """递归枚举明确属于运行数据的目录，不跟随符号链接。"""
    if not root.exists() or root.is_symlink():
        return
    yield PermissionTarget(root, 0o700, True)
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [name for name in directories if not (current_path / name).is_symlink()]
        for name in directories:
            directory = current_path / name
            yield PermissionTarget(directory, 0o700, True)
        for name in files:
            file_path = current_path / name
            if file_path.is_symlink() or not file_path.is_file():
                continue
            yield PermissionTarget(file_path, _desired_file_mode(file_path), False)


def _single_file(path: Path) -> Iterable[PermissionTarget]:
    """枚举一个存在且不是符号链接的敏感文件。"""
    if path.exists() and path.is_file() and not path.is_symlink():
        yield PermissionTarget(path, _desired_file_mode(path), False)


def collect_targets(project_root: Path, runtime_home: Path) -> list[PermissionTarget]:
    """收集项目已知的凭据、会话、记忆、数据库和运行证据路径。"""
    candidates: list[PermissionTarget] = []

    if runtime_home.exists() and not runtime_home.is_symlink():
        candidates.append(PermissionTarget(runtime_home, 0o700, True))
        for path in runtime_home.glob("*.json"):
            candidates.extend(_single_file(path))
        for name in (".env", "env"):
            candidates.extend(_single_file(runtime_home / name))
        for directory in (
            runtime_home / "memory",
            runtime_home / "credentials",
            runtime_home / "identity",
            runtime_home / "devices",
            runtime_home / "cache" / "yfinance",
        ):
            candidates.extend(_walk_private_tree(directory))
        candidates.extend(_single_file(runtime_home / "openclaw-weixin" / "accounts.json"))

    for path in (
        project_root / ".env",
        project_root / "packages" / "clawbot" / "config" / ".env",
    ):
        candidates.extend(_single_file(path))
    project_runtime = project_root / ".openclaw"
    if project_runtime.exists() and not project_runtime.is_symlink():
        candidates.append(PermissionTarget(project_runtime, 0o700, True))
        for path in project_runtime.glob("*.json"):
            candidates.extend(_single_file(path))
    candidates.extend(_walk_private_tree(project_runtime / "memory"))
    candidates.extend(_walk_private_tree(project_root / "packages" / "clawbot" / "data"))

    unique: dict[Path, PermissionTarget] = {}
    for target in candidates:
        unique[target.path] = target
    return sorted(unique.values(), key=lambda item: str(item.path))


def audit_targets(targets: Iterable[PermissionTarget], *, apply: bool) -> dict[str, int | bool]:
    """检查权限；显式 --apply 时只调用 chmod，不读取任何内容。"""
    checked = 0
    violations = 0
    changed_files = 0
    changed_directories = 0
    failed_changes = 0
    for target in targets:
        try:
            current_mode = stat.S_IMODE(target.path.lstat().st_mode)
        except FileNotFoundError:
            continue
        checked += 1
        if current_mode == target.desired_mode:
            continue
        violations += 1
        if not apply:
            continue
        try:
            os.chmod(target.path, target.desired_mode, follow_symlinks=False)
            if target.is_directory:
                changed_directories += 1
            else:
                changed_files += 1
        except OSError:
            failed_changes += 1
    remaining = violations if not apply else failed_changes
    return {
        "ok": remaining == 0,
        "apply": apply,
        "checked": checked,
        "violations": violations,
        "changed_files": changed_files,
        "changed_directories": changed_directories,
        "failed_changes": failed_changes,
        "remaining_violations": remaining,
        "contents_read": False,
    }


def build_parser() -> argparse.ArgumentParser:
    """默认只检查，只有显式 --apply 才改权限。"""
    parser = argparse.ArgumentParser(description="Audit OpenClaw runtime file permissions")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="只检查并在发现问题时返回非零")
    mode.add_argument("--apply", action="store_true", help="把已知敏感文件和目录收紧为仅所有者可访问")
    return parser


def main() -> int:
    """输出不含具体路径和文件内容的机器可读摘要。"""
    args = build_parser().parse_args()
    project_root = _project_root()
    runtime_home = _runtime_home()
    payload = audit_targets(
        collect_targets(project_root, runtime_home),
        apply=bool(args.apply),
    )
    if args.apply:
        verification = audit_targets(
            collect_targets(project_root, runtime_home),
            apply=False,
        )
        payload["remaining_violations"] = verification["violations"]
        payload["ok"] = verification["violations"] == 0
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
