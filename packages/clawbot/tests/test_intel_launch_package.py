from __future__ import annotations

import json


def test_build_launchd_package_is_dry_run_and_references_private_env(tmp_path):
    from src.intel.launch_package import build_launchd_package

    env_path = tmp_path / ".openclaw" / "intel-brief.production.env"
    output_dir = tmp_path / "launch"

    report = build_launchd_package(
        output_dir=output_dir,
        project_root=tmp_path,
        env_path=env_path,
        summary_evidence_path=tmp_path / "summary.json",
        label="ai.openclaw.intel-brief.scheduler",
    )

    assert report["status"] == "generated"
    assert report["production_action"] == "none"
    assert report["installed"] is False
    plist = output_dir / "ai.openclaw.intel-brief.scheduler.plist"
    rollback = output_dir / "rollback.sh"
    assert plist.exists()
    assert rollback.exists()
    plist_text = plist.read_text(encoding="utf-8")
    assert str(env_path) in plist_text
    assert "intel_production_cycle.py" in plist_text
    assert "--output-dir" in plist_text
    assert "--evidence" in plist_text
    assert "launchctl load" not in rollback.read_text(encoding="utf-8")


def test_launch_package_cli_writes_redacted_evidence(tmp_path):
    from scripts.intel_launch_package import main

    output_dir = tmp_path / "launch"
    evidence = tmp_path / "launch-evidence.json"
    env_path = tmp_path / ".openclaw" / "intel-brief.production.env"

    exit_code = main(
        [
            "--output-dir",
            str(output_dir),
            "--evidence",
            str(evidence),
            "--project-root",
            str(tmp_path),
            "--env-path",
            str(env_path),
            "--summary-evidence",
            str(tmp_path / "summary.json"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["status"] == "generated"
    assert payload["production_action"] == "none"
    assert payload["network_calls"] == 0


def test_launch_package_cli_does_not_require_fixed_summary_for_production_cycle(tmp_path):
    from scripts.intel_launch_package import main

    output_dir = tmp_path / "launch"
    evidence = tmp_path / "launch-evidence.json"
    env_path = tmp_path / ".openclaw" / "intel-brief.production.env"

    exit_code = main(
        [
            "--output-dir",
            str(output_dir),
            "--evidence",
            str(evidence),
            "--project-root",
            str(tmp_path),
            "--env-path",
            str(env_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["status"] == "generated"
    plist_text = (output_dir / "ai.openclaw.intel-brief.scheduler.plist").read_text(encoding="utf-8")
    assert "intel_production_cycle.py" in plist_text
    assert "--summary-evidence" not in plist_text


def test_build_launchd_package_can_embed_explicit_production_ack_and_log_paths(tmp_path):
    from src.execution.intel_brief import PRODUCTION_ACK_VALUE
    from src.intel.launch_package import build_launchd_package

    output_dir = tmp_path / "launch"
    report = build_launchd_package(
        output_dir=output_dir,
        project_root=tmp_path,
        env_path=tmp_path / ".openclaw" / "intel-brief.production.env",
        include_production_ack=True,
    )

    plist_text = (output_dir / "ai.openclaw.intel-brief.scheduler.plist").read_text(encoding="utf-8")
    assert "INTEL_BRIEF_SCHEDULER_PRODUCTION_ACK" in plist_text
    assert PRODUCTION_ACK_VALUE in plist_text
    assert "StandardOutPath" in plist_text
    assert "StandardErrorPath" in plist_text
    assert report["production_ack_embedded"] is True
    assert report["stdout_path"].endswith("stdout.log")
    assert report["stderr_path"].endswith("stderr.log")


def test_build_launchd_package_resolves_relative_paths_against_project_root(tmp_path):
    from src.intel.launch_package import build_launchd_package

    report = build_launchd_package(
        output_dir="relative-launch",
        project_root=tmp_path,
        env_path=".openclaw/intel-brief.production.env",
        include_production_ack=True,
    )

    assert report["output_dir"] == str(tmp_path / "relative-launch")
    assert report["private_env_path"] == str(tmp_path / ".openclaw" / "intel-brief.production.env")
    plist_text = (tmp_path / "relative-launch" / "ai.openclaw.intel-brief.scheduler.plist").read_text(encoding="utf-8")
    assert str(tmp_path / "relative-launch" / "runs") in plist_text
    assert str(tmp_path / "relative-launch" / "logs" / "stdout.log") in plist_text
