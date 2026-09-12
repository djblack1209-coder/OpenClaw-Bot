"""Validate effective default paths inside the repository's offline runner."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif("OE_TEST_HOME" not in os.environ, reason="local offline-runner contract")


def test_user_state_defaults_and_dotenv_are_isolated():
    from src.execution.social import drafts, publish_gate
    from src.litellm_router import _IFLOW_TIMESTAMP_FILE

    temporary = Path(os.environ["OE_TEST_HOME"])
    assert Path.home() == temporary
    assert Path(os.path.expanduser("~")) == temporary
    for state_path in (drafts._DRAFTS_FILE, publish_gate._lock_path(), _IFLOW_TIMESTAMP_FILE):
        assert state_path.is_relative_to(temporary)
    assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
    assert "HOME" not in os.environ and "CODEX_HOME" not in os.environ
