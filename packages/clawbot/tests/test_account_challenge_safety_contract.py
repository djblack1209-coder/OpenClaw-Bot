"""账号验证码、滑块和凭据轮换必须停在人工操作边界。"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_async_slider_solver_detects_but_never_drags(monkeypatch):
    from src.xianyu.slider_solver import SliderSolver

    solver = SliderSolver()
    monkeypatch.setattr(solver, "detect_slider", AsyncMock(return_value=True))
    page = MagicMock()

    assert await solver.solve(page) is False
    page.mouse.move.assert_not_called()
    page.mouse.down.assert_not_called()
    page.mouse.up.assert_not_called()


def test_sync_slider_solver_detects_but_never_drags(monkeypatch):
    from src.xianyu.slider_solver import SliderSolverSync

    solver = SliderSolverSync()
    monkeypatch.setattr(solver, "detect_slider", MagicMock(return_value=True))
    page = MagicMock()

    assert solver.solve(page) is False
    page.mouse.move.assert_not_called()
    page.mouse.down.assert_not_called()
    page.mouse.up.assert_not_called()


def test_xianyu_login_is_visible_manual_flow_without_stealth_or_auto_slider():
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "packages" / "clawbot" / "scripts" / "xianyu_login.py").read_text(encoding="utf-8")

    assert "STEALTH_JS" not in source
    assert "slider_solver.solve" not in source
    assert "--disable-blink-features=AutomationControlled" not in source
    assert "headless 模式已禁用" in source


def test_iflow_renewal_never_reads_messages_or_bypasses_captcha():
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "packages" / "clawbot" / "scripts" / "iflow_key_renew.py").read_text(encoding="utf-8")

    forbidden = {
        "MESSAGES_DB",
        "sqlite3",
        "ddddocr",
        "stealth_sync",
        "human_like_drag",
        "read_latest_sms_code",
        "wait_for_sms_code",
    }
    assert all(token not in source for token in forbidden)
    assert 'os.getenv("IFLOW_PHONE_NUMBER", "")' in source
    assert "请在浏览器内手动完成验证码、登录和 Key 轮换" in source
    assert "新 Key 已接收（不会显示或写入日志）" in source


def test_iflow_expiry_check_only_emits_manual_reminder():
    from src import litellm_router

    source = inspect.getsource(litellm_router._trigger_iflow_auto_renew)
    tree = ast.parse(source)
    calls = {
        getattr(node.func, "attr", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }

    assert "Popen" not in calls
    assert "Thread" not in calls
    assert "自动续期已禁用" in source


def test_self_heal_captcha_stops_for_human():
    from src.core.self_heal import KNOWN_SOLUTIONS

    for key in ("captcha", "验证码"):
        policy = KNOWN_SOLUTIONS[key]
        assert policy["action"] == "notify_human"
        assert "人工" in policy["solution"]
