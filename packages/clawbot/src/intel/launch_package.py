"""Dry-run launch package for Intel Brief production scheduler.

This module generates reviewable launchd assets but never installs or loads
them. It is a production-closure artifact, not a deployment action. The plist
points at the fresh production cycle, not a fixed summary replay.
"""

from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.execution.intel_brief import PRODUCTION_ACK_VALUE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10 worker compatibility


def _plist_xml(
    *,
    label: str,
    project_root: Path,
    env_path: Path,
    evidence_dir: Path,
    stdout_path: Path,
    stderr_path: Path,
    include_production_ack: bool = False,
) -> str:
    python_path = project_root / "packages" / "clawbot" / ".venv312" / "bin" / "python"
    production_cycle = project_root / "packages" / "clawbot" / "scripts" / "intel_production_cycle.py"
    evidence_path = evidence_dir / "latest-production-cycle.json"
    ack_xml = ""
    if include_production_ack:
        ack_xml = f"""
    <key>INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK</key>
    <string>{PRODUCTION_ACK_VALUE}</string>"""
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>WorkingDirectory</key>
  <string>{project_root}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>INTEL_BRIEF_PRIVATE_ENV</key>
    <string>{env_path}</string>{ack_xml}
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>{python_path}</string>
    <string>{production_cycle}</string>
    <string>--output-dir</string>
    <string>{evidence_dir}</string>
    <string>--evidence</string>
    <string>{evidence_path}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>8</integer>
    <key>Minute</key><integer>30</integer>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key>
  <string>{stdout_path}</string>
  <key>StandardErrorPath</key>
  <string>{stderr_path}</string>
</dict>
</plist>
"""


def build_launchd_package(
    *,
    output_dir: str | Path,
    project_root: str | Path,
    env_path: str | Path,
    summary_evidence_path: str | Path | None = None,
    label: str = "ai.openclaw.intel-brief.scheduler",
    include_production_ack: bool = False,
) -> dict[str, Any]:
    """Generate launchd package files without installing them."""
    root = Path(project_root).resolve()
    out = Path(output_dir)
    if not out.is_absolute():
        out = root / out
    env = Path(env_path)
    if not env.is_absolute():
        env = root / env
    out.mkdir(parents=True, exist_ok=True)
    plist_path = out / f"{label}.plist"
    rollback_path = out / "rollback.sh"
    readme_path = out / "README.md"
    evidence_dir = out / "runs"
    logs_dir = out / "logs"
    stdout_path = logs_dir / "stdout.log"
    stderr_path = logs_dir / "stderr.log"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    plist_path.write_text(
        _plist_xml(
            label=label,
            project_root=root,
            env_path=env,
            evidence_dir=evidence_dir,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            include_production_ack=include_production_ack,
        ),
        encoding="utf-8",
    )
    rollback_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"# Dry-run rollback helper for {label}",
                f"launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/{label}.plist 2>/dev/null || true",
                f"rm -f ~/Library/LaunchAgents/{label}.plist",
                "echo rollback_complete",
                "",
            ]
        ),
        encoding="utf-8",
    )
    os.chmod(rollback_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    readme_path.write_text(
        "\n".join(
            [
                "# Intel Brief launchd package (dry-run)",
                "",
                "This package is generated for review only. It has not been installed or loaded.",
                "",
                f"- plist: `{plist_path}`",
                f"- private env: `{env}`",
                f"- run evidence dir: `{evidence_dir}`",
                f"- stdout log: `{stdout_path}`",
                f"- stderr log: `{stderr_path}`",
                f"- production ack embedded: `{include_production_ack}`",
                f"- rollback helper: `{rollback_path}`",
                "",
                "Install requires a separate explicit production action.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "timestamp": _now_iso(),
        "status": "generated",
        "production_action": "none",
        "installed": False,
        "label": label,
        "output_dir": str(out),
        "plist_path": str(plist_path),
        "rollback_path": str(rollback_path),
        "readme_path": str(readme_path),
        "private_env_path": str(env),
        "run_evidence_dir": str(evidence_dir),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "production_ack_embedded": bool(include_production_ack),
        "limits": [
            "Generated package only; not copied to ~/Library/LaunchAgents.",
            "No launchctl bootstrap/load/kickstart command is run.",
            "No scheduler/cron/systemd is enabled.",
            "No token or chat id values are embedded in the plist.",
        ],
    }
