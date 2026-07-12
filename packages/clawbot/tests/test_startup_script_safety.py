from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "packages" / "clawbot" / "scripts"


def test_tauri_fallback_launchers_are_path_independent_and_never_kill_existing_processes() -> None:
    clawbot = (SCRIPTS / "start_clawbot.sh").read_text(encoding="utf-8")
    xianyu = (SCRIPTS / "start_xianyu.sh").read_text(encoding="utf-8")

    for content in (clawbot, xianyu):
        assert "${BASH_SOURCE[0]}" in content
        assert "/Users/" not in content
        assert "pkill" not in content
        assert "pip install" not in content
        assert "umask 077" in content
        assert 'exec "$PYTHON"' in content

    assert "multi_main.py" in clawbot
    assert "scripts/xianyu_main.py" in xianyu
    assert "src.xianyu.xianyu_live" not in xianyu


def test_obsolete_all_in_one_and_broken_installer_entrypoints_are_removed() -> None:
    removed = {
        "start.sh",
        "start_all.sh",
        "start_omega.sh",
        "stop_all.sh",
        "pack_deploy_bundle.sh",
        "pack_final.sh",
        "pack_web_installer.sh",
    }
    assert all(not (SCRIPTS / name).exists() for name in removed)
    assert not (REPO_ROOT / "packages" / "clawbot" / "tools" / "package.sh").exists()
