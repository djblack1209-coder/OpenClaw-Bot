from __future__ import annotations


def test_write_private_env_file_redacts_report_and_sets_0600(tmp_path):
    from src.intel.private_env import write_private_env_file

    env_path = tmp_path / ".openclaw" / "intel-brief.production.env"

    report = write_private_env_file(
        env_path,
        values={
            "INTEL_BRIEF_TELEGRAM_BOT_TOKEN": "123456:SECRET-DO-NOT-LEAK",
            "INTEL_BRIEF_TELEGRAM_CHAT_ID": "987654321",
            "INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK": "I_UNDERSTAND_TELEGRAM_SANDBOX_SEND",
            "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED": "true",
        },
    )

    saved = env_path.read_text(encoding="utf-8")
    assert "INTEL_BRIEF_TELEGRAM_BOT_TOKEN=123456:SECRET-DO-NOT-LEAK" in saved
    assert "INTEL_BRIEF_TELEGRAM_CHAT_ID=987654321" in saved
    assert "SECRET" not in str(report)
    assert "987654321" not in str(report)
    assert report["redacted_env"]["INTEL_BRIEF_TELEGRAM_BOT_TOKEN"] is True
    assert report["redacted_env"]["INTEL_BRIEF_TELEGRAM_CHAT_ID"] is True
    assert oct(env_path.stat().st_mode & 0o777) == "0o600"


def test_load_private_env_file_parses_values_without_export(tmp_path):
    from src.intel.private_env import load_private_env_file

    env_path = tmp_path / "intel.env"
    env_path.write_text(
        "# comment\nINTEL_BRIEF_TELEGRAM_BOT_TOKEN='abc:def'\nINTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED=true\n",
        encoding="utf-8",
    )

    env = load_private_env_file(env_path)

    assert env["INTEL_BRIEF_TELEGRAM_BOT_TOKEN"] == "abc:def"
    assert env["INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED"] == "true"


def test_build_private_env_audit_reports_missing_required_keys(tmp_path):
    from src.intel.private_env import build_private_env_audit

    env_path = tmp_path / "intel.env"
    env_path.write_text("INTEL_BRIEF_TELEGRAM_BOT_TOKEN=x\n", encoding="utf-8")

    audit = build_private_env_audit(env_path)

    assert audit["status"] == "blocked"
    assert "INTEL_BRIEF_TELEGRAM_CHAT_ID" in audit["missing_keys"]
    assert audit["redacted_env"]["INTEL_BRIEF_TELEGRAM_BOT_TOKEN"] is True


def test_private_env_file_is_gitignored_for_default_path(tmp_path):
    from src.intel.private_env import default_private_env_path, is_default_private_env_gitignored

    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".openclaw/env\n.openclaw/*.env\n", encoding="utf-8")

    assert default_private_env_path(tmp_path) == tmp_path / ".openclaw" / "intel-brief.production.env"
    assert is_default_private_env_gitignored(tmp_path, gitignore_path=gitignore) is True


def test_intel_private_env_cli_writes_redacted_evidence_from_env(tmp_path, monkeypatch):
    from scripts.intel_private_env import main

    env_path = tmp_path / ".openclaw" / "intel-brief.production.env"
    evidence = tmp_path / "private-env-evidence.json"
    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_BOT_TOKEN", "123456:SECRET-DO-NOT-LEAK")
    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_CHAT_ID", "987654321")
    monkeypatch.setenv("INTEL_BRIEF_TELEGRAM_SANDBOX_SEND_ACK", "I_UNDERSTAND_TELEGRAM_SANDBOX_SEND")

    exit_code = main(
        [
            "--env-path",
            str(env_path),
            "--evidence",
            str(evidence),
            "--worker-placement-confirmed",
        ]
    )

    assert exit_code == 0
    assert env_path.exists()
    saved_evidence = evidence.read_text(encoding="utf-8")
    assert "SECRET" not in saved_evidence
    assert "987654321" not in saved_evidence
    assert "INTEL_BRIEF_WORKER_PLACEMENT_CONFIRMED=true" in env_path.read_text(encoding="utf-8")


def test_repository_gitignore_covers_default_private_env_path():
    from pathlib import Path

    from src.intel.private_env import is_default_private_env_gitignored

    project_root = Path(__file__).resolve().parents[3]

    assert is_default_private_env_gitignored(project_root) is True
