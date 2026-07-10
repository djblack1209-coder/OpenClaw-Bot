"""Private Intel Brief environment file helpers.

The default path lives under ``.openclaw/`` and is gitignored by the repository.
Reports from this module only expose key presence booleans; secret values are
written to the private env file but never returned in evidence payloads.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

REQUIRED_PRIVATE_ENV_KEYS = (
    "INTEL_BRIEF_TELEGRAM_BOT_TOKEN",
    "INTEL_BRIEF_TELEGRAM_CHAT_ID",
    "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK",
    "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED",
)


def default_private_env_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".openclaw" / "intel-brief.production.env"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _quote_env_value(value: str) -> str:
    return shlex.quote(str(value))


def _redacted_env(values: dict[str, str]) -> dict[str, bool]:
    return {key: bool(_clean(values.get(key))) for key in REQUIRED_PRIVATE_ENV_KEYS}


def write_private_env_file(path: str | Path, *, values: dict[str, str]) -> dict[str, Any]:
    """Write a private env file and return a redacted report."""
    env_path = Path(path)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    ordered_keys = [key for key in REQUIRED_PRIVATE_ENV_KEYS if key in values]
    extra_keys = sorted(key for key in values if key not in REQUIRED_PRIVATE_ENV_KEYS)
    lines = [
        "# OpenEverything Intel Brief private runtime env",
        "# Contains secrets/chat ids. Gitignored. Do not commit or paste.",
    ]
    for key in [*ordered_keys, *extra_keys]:
        lines.append(f"{key}={_quote_env_value(values[key])}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    present = _redacted_env({key: values.get(key, "") for key in REQUIRED_PRIVATE_ENV_KEYS})
    missing = [key for key, is_present in present.items() if not is_present]
    return {
        "status": "ready" if not missing else "blocked",
        "path": str(env_path),
        "exists": True,
        "mode": oct(env_path.stat().st_mode & 0o777),
        "redacted_env": present,
        "missing_keys": missing,
        "secrets_written": True,
        "limits": [
            "Report is redacted; token and chat id values are not returned.",
            "Private env file is intended to remain gitignored and local to the runtime host.",
        ],
    }


def load_private_env_file(path: str | Path) -> dict[str, str]:
    """Parse simple KEY=value env files without exporting to the process."""
    env_path = Path(path)
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        try:
            parsed = shlex.split(value)
        except ValueError:
            parsed = [value]
        values[key] = parsed[0] if parsed else ""
    return values


def build_private_env_audit(path: str | Path) -> dict[str, Any]:
    """Return a redacted readiness audit for a private Intel Brief env file."""
    env_path = Path(path)
    values = load_private_env_file(env_path)
    present = _redacted_env(values)
    missing = [key for key, is_present in present.items() if not is_present]
    return {
        "status": "ready" if env_path.exists() and not missing else "blocked",
        "path": str(env_path),
        "exists": env_path.exists(),
        "mode": oct(env_path.stat().st_mode & 0o777) if env_path.exists() else "",
        "redacted_env": present,
        "missing_keys": missing,
        "limits": [
            "Audit does not print env values.",
            "Production ack is intentionally not a required private-env key; it remains an explicit launch-time gate.",
        ],
    }


def is_default_private_env_gitignored(
    project_root: str | Path,
    *,
    gitignore_path: str | Path | None = None,
) -> bool:
    """Best-effort check that default private env is covered by .gitignore."""
    root = Path(project_root)
    target = default_private_env_path(root).relative_to(root).as_posix()
    gitignore = Path(gitignore_path) if gitignore_path is not None else root / ".gitignore"
    if not gitignore.exists():
        return False
    patterns = [line.strip() for line in gitignore.read_text(encoding="utf-8").splitlines()]
    for pattern in patterns:
        if not pattern or pattern.startswith("#"):
            continue
        if pattern == target:
            return True
        if pattern.endswith("*.env") and target.startswith(pattern[: -len("*.env")]) and target.endswith(".env"):
            return True
        if pattern.endswith("/") and target.startswith(pattern):
            return True
    return False
