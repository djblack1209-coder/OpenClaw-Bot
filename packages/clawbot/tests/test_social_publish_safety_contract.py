"""社媒外部写操作必须经过当前操作的最终人工确认。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.rpc import ClawBotRPC
from src.execution.social.worker_bridge import run_social_worker
from src.sau_bridge import publish_video


def test_browser_worker_publish_is_blocked_before_subprocess(monkeypatch):
    subprocess_run = MagicMock()
    monkeypatch.setattr("src.execution.social.worker_bridge.subprocess.run", subprocess_run)

    result = run_social_worker("publish_x", {"text": "不能自动外发"})

    assert result["success"] is False
    assert result["requires_human_confirmation"] is True
    assert result["code"] == "social_publish_confirmation_required"
    subprocess_run.assert_not_called()


@pytest.mark.asyncio
async def test_rpc_raw_publish_is_blocked_without_final_confirmation(monkeypatch):
    worker = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("src.execution.social.worker_bridge.run_social_worker_async", worker)

    result = await ClawBotRPC._rpc_social_publish("x", "不能自动外发")

    assert result["success"] is False
    assert result["requires_human_confirmation"] is True
    worker.assert_not_awaited()


@pytest.mark.asyncio
async def test_sau_video_publish_is_blocked_before_cli(monkeypatch, tmp_path):
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"demo")
    sau = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("src.sau_bridge._run_sau_cmd", sau)

    result = await publish_video("douyin", str(video), "测试")

    assert result["success"] is False
    assert result["requires_human_confirmation"] is True
    sau.assert_not_awaited()


@pytest.mark.asyncio
async def test_platform_adapters_are_blocked_without_final_confirmation():
    from src.execution.social.x_adapter import XPlatformAdapter
    from src.execution.social.xhs_adapter import XhsPlatformAdapter

    x_worker = MagicMock()
    x_result = await XPlatformAdapter().publish("不能自动外发", worker_fn=x_worker)
    xhs_result = await XhsPlatformAdapter().publish(
        "标题\n不能自动外发",
        worker_fn=x_worker,
    )

    assert x_result["requires_human_confirmation"] is True
    assert xhs_result["requires_human_confirmation"] is True
    x_worker.assert_not_called()


@pytest.mark.asyncio
async def test_brain_publish_executor_reports_block_instead_of_false_success():
    from src.core.brain_exec_social import SocialExecutorMixin

    result = await SocialExecutorMixin()._exec_social_publish({
        "platform": "x",
        "draft": "模型不能绕过最终确认",
    })

    assert result["success"] is False
    assert result["requires_human_confirmation"] is True


def test_telegram_legacy_post_commands_are_draft_only_and_describe_it_honestly():
    """旧“发文”命令名可以兼容，但提示和实现都不能冒充已经外发。"""
    import ast
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[1] / "src"
    command_path = src_root / "bot" / "cmd_social_mixin.py"
    command_source = command_path.read_text(encoding="utf-8")
    tree = ast.parse(command_source, filename=str(command_path))

    method_sources: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
            "cmd_xhs",
            "cmd_post",
            "cmd_xpost",
            "cmd_xhspost",
            "cmd_publish",
        }:
            method_sources[node.name] = ast.get_source_segment(command_source, node) or ""

    assert set(method_sources) == {
        "cmd_xhs",
        "cmd_post",
        "cmd_xpost",
        "cmd_xhspost",
        "cmd_publish",
    }
    for name, source in method_sources.items():
        assert "final_confirmed=True" not in source, name
        assert "_publish_social_package" not in source, name
    assert "待审草稿" in method_sources["cmd_xhs"]
    assert "待审草稿" in method_sources["cmd_post"]
    assert "未提交真实发布" in method_sources["cmd_xpost"]
    assert "未提交真实发布" in method_sources["cmd_xhspost"]
    assert "publish_video" not in method_sources["cmd_publish"]
    assert "publish_note" not in method_sources["cmd_publish"]
    assert "小红书热点发布中" not in method_sources["cmd_xhs"]
    assert "📱 双平台发文:" not in method_sources["cmd_post"]

    help_source = (src_root / "bot" / "cmd_basic" / "help_mixin.py").read_text(encoding="utf-8")
    ops_source = (src_root / "bot" / "cmd_ops_mixin.py").read_text(encoding="utf-8")
    for stale_text in (
        "抓热点 + 自动发文",
        "X 直接发布",
        "小红书直接发布",
        "自动拉起专用浏览器并双发",
        "自动拉起专用浏览器发 X",
        "自动拉起专用浏览器发小红书",
    ):
        assert stale_text not in help_source
        assert stale_text not in ops_source


def test_final_confirmation_true_is_limited_to_guarded_manual_paths():
    import ast
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[1] / "src"
    sites: set[tuple[str, str]] = set()
    for path in src_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not any(
                keyword.arg == "final_confirmed"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            ):
                continue
            current: ast.AST | None = node
            function_name = "<module>"
            while current in parents:
                current = parents[current]
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function_name = current.name
                    break
            sites.add((path.relative_to(src_root).as_posix(), function_name))

    assert sites == {
        ("api/rpc.py", "_rpc_social_draft_publish"),
        ("api/rpc.py", "_rpc_social_publish"),
        ("bot/cmd_social_mixin.py", "handle_social_confirm_callback"),
        ("execution/__init__.py", "_publish_social_package"),
        ("execution/social/drafts.py", "publish_social_draft"),
        ("execution/social/x_platform.py", "publish_x_post"),
        ("execution/social/x_platform.py", "reply_to_x_post"),
        ("execution/social/xhs_platform.py", "publish_xhs_article"),
        ("execution/social/xhs_platform.py", "reply_to_xhs_comment"),
        ("execution/social/xhs_platform.py", "update_xhs_profile"),
        ("sau_bridge.py", "_publish_one"),
    }


def test_manager_publish_confirmation_reaches_backend_only_from_confirm_dialog():
    """桌面端二次确认必须显式传到 Web/Tauri 后端，普通调用保持默认拒绝。"""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    manager_root = repo_root / "apps" / "openclaw-manager-src"
    api_source = (manager_root / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    ipc_source = (manager_root / "src" / "lib" / "tauri-ipc.ts").read_text(encoding="utf-8")
    component_source = (manager_root / "src" / "components" / "Social" / "index.tsx").read_text(encoding="utf-8")
    rust_source = (manager_root / "src-tauri" / "src" / "commands" / "clawbot_api.rs").read_text(encoding="utf-8")

    assert "clawbotSocialDraftPublish: (index: number, finalConfirmed = false)" in api_source
    assert "/publish?confirmed=${finalConfirmed}" in api_source
    assert "ipc.clawbotSocialDraftPublish(index, finalConfirmed)" in api_source

    assert "clawbotSocialDraftPublish = (index: number, finalConfirmed = false)" in ipc_source
    assert "{ index, finalConfirmed }" in ipc_source

    assert "final_confirmed: bool" in rust_source
    assert '"/social/drafts/{}/publish?confirmed={}"' in rust_source

    confirmed_call = "api.clawbotSocialDraftPublish(pendingAction.index, true)"
    assert component_source.count(confirmed_call) == 1
    assert "onConfirm={handleConfirmAction}" in component_source


@pytest.mark.asyncio
async def test_reply_and_profile_writes_are_blocked_before_custom_worker():
    from src.execution.social.x_platform import reply_to_x_post
    from src.execution.social.xhs_platform import reply_to_xhs_comment, update_xhs_profile

    worker = MagicMock(return_value={"success": True})

    x_reply = await reply_to_x_post("https://x.com/demo/status/1", "不能自动回复", worker_fn=worker)
    xhs_reply = await reply_to_xhs_comment("https://www.xiaohongshu.com/explore/1", "不能自动回复", worker_fn=worker)
    profile = await update_xhs_profile("不能自动改资料", worker_fn=worker)

    assert x_reply["requires_human_confirmation"] is True
    assert xhs_reply["requires_human_confirmation"] is True
    assert profile["requires_human_confirmation"] is True
    worker.assert_not_called()


def test_worker_bridge_confirmed_write_passes_explicit_cli_confirmation(monkeypatch):
    completed = MagicMock(
        returncode=0,
        stdout='{"success": true}',
        stderr="",
    )
    subprocess_run = MagicMock(return_value=completed)
    monkeypatch.setattr("src.execution.social.worker_bridge.subprocess.run", subprocess_run)

    result = run_social_worker(
        "publish_x",
        {"text": "已完成本次最终确认"},
        final_confirmed=True,
    )

    assert result["success"] is True
    argv = subprocess_run.call_args.args[0]
    assert argv[-1] == "--final-confirmed"


def test_all_browser_worker_mutations_require_confirmation():
    from src.execution.social.publish_safety import is_external_social_write

    actions = {
        "publish_x",
        "reply_x",
        "reply_xhs",
        "publish_xhs",
        "update_xhs_profile",
        "delete_x",
    }

    assert all(is_external_social_write(action) for action in actions)


def test_direct_browser_worker_cli_blocks_write_without_final_confirmation(monkeypatch, capsys):
    import importlib.util
    import json
    import sys
    from pathlib import Path

    worker_path = Path(__file__).resolve().parents[1] / "scripts" / "social_browser_worker.py"
    spec = importlib.util.spec_from_file_location("social_browser_worker_safety_test", worker_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    publish = MagicMock(return_value={"success": True})
    monkeypatch.setattr(module, "publish_x", publish)
    monkeypatch.setattr(sys, "argv", [str(worker_path), "publish_x", json.dumps({"text": "不能直调"})])

    assert module.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["requires_human_confirmation"] is True
    publish.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_x_schedule_cannot_publish_without_current_confirmation(monkeypatch):
    import importlib.util
    from pathlib import Path

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "x_auto_morning_post.py"
    spec = importlib.util.spec_from_file_location("x_auto_morning_post_safety_test", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    draft = {"id": "approved", "text": "已审核但未最终确认", "review_status": "approved"}
    monkeypatch.setattr(module, "get_or_build_next_ready_draft", lambda: draft)
    publisher = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(module, "_publish_with_twikit_or_worker", publisher)

    result = await module.publish_once()

    assert result["requires_human_confirmation"] is True
    publisher.assert_not_awaited()


def test_launchd_social_schedule_is_review_only():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "execution"
        / "social"
        / "x_auto_ops.py"
    ).read_text(encoding="utf-8")

    assert "<string>--pending-review</string>" in source
    assert "<string>--publish-next</string>" not in source
