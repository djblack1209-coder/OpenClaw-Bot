import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = REPO_ROOT / "Makefile"


def test_github_ci_rejects_every_deterministic_test_failure() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "预存失败" not in workflow
    assert "FAILED_COUNT" not in workflow
    assert "pytest-output.txt" not in workflow
    assert "paths-ignore:" not in workflow
    for target in ("ci-python", "ci-frontend", "ci-frist-api", "ci-docs"):
        assert f"make {target}" in workflow


def test_local_ci_uses_the_same_complete_quality_targets() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")

    for target in ("ci-python:", "ci-frontend:", "ci-frist-api:", "ci-docs:"):
        assert target in makefile
    assert "ci-local: ci-python ci-frontend ci-frist-api ci-docs" in makefile
    assert "npm run lint" in makefile
    assert "npm run build" in makefile
    assert "frontend-static-test:" in makefile
    assert "social-growth-feedback.static.test.mjs" in makefile
    assert "layout-responsive.static.test.mjs" in makefile
    assert "npm test" in makefile
    assert "chrome-extension-test:" in makefile
    assert "test/social-page-runner.test.mjs" in makefile
    assert "test/popup-static.test.mjs" in makefile


def test_github_actions_are_pinned_to_immutable_full_commit_shas() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    uses = re.findall(r"^\s*-?\s*uses:\s+([^#\s]+)", workflow, flags=re.MULTILINE)

    assert uses, "CI workflow should contain third-party actions"
    for action in uses:
        assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action), (
            f"GitHub Action must be pinned to an immutable full commit SHA: {action}"
        )


def test_deep_clean_never_deletes_registered_worktrees() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    deep_clean = makefile.split("deep-clean:", 1)[1].split("## ─── CI", 1)[0]

    assert "git worktree remove" not in deep_clean
    assert "rm -rf .worktrees" not in deep_clean
    assert "git worktree prune" in deep_clean
