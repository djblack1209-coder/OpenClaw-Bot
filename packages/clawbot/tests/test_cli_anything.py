"""CLI-Anything 桥接层单元测试

覆盖:
- discover_installed_clis: PATH 扫描、缓存、错误处理
- run_cli_command: 安全校验、超时、正常执行
- install_cli_tool: 名称校验、pip 调用
- CLIAnythingManager: 单例、状态查询
- Telegram 命令解析
"""

import asyncio
import os
import queue
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import APIServer
from src.integrations.cli_anything_bridge import (
    CLI_REMOTE_INSTALL_DISABLED_MESSAGE,
    CLIAnythingManager,
    _is_valid_tool_name,
    discover_installed_clis,
    install_cli_tool,
    run_cli_command,
)


def _run_async_in_thread(
    coroutine_factory: Callable[[], Awaitable[Any]],
    result_queue: queue.Queue[tuple[str, Any]],
    loop_queue: queue.Queue[asyncio.AbstractEventLoop],
) -> threading.Thread:
    """在独立线程和事件循环中运行协程，并回传结果或异常。"""

    def worker() -> None:
        loop = asyncio.new_event_loop()
        loop.set_debug(True)
        loop_queue.put(loop)
        try:
            result = loop.run_until_complete(coroutine_factory())
        except BaseException as exc:
            result_queue.put(("error", exc))
        else:
            result_queue.put(("ok", result))
        finally:
            loop.close()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


def _stop_stuck_loop(
    thread: threading.Thread,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """红测路径兜底停止被跨循环锁卡住的事件循环。"""
    if thread.is_alive():
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1)


# ── 工具名校验 ──────────────────────────────────────────


class TestToolNameValidation:
    """工具名称合法性校验"""

    def test_valid_names(self):
        assert _is_valid_tool_name("gimp") is True
        assert _is_valid_tool_name("blender") is True
        assert _is_valid_tool_name("my-tool") is True
        assert _is_valid_tool_name("tool123") is True
        assert _is_valid_tool_name("a") is True

    def test_invalid_names(self):
        # 空名称
        assert _is_valid_tool_name("") is False
        # 特殊字符（防注入）
        assert _is_valid_tool_name("tool;rm -rf /") is False
        assert _is_valid_tool_name("tool&&echo") is False
        assert _is_valid_tool_name("../etc/passwd") is False
        assert _is_valid_tool_name("tool name") is False
        # 以连字符开头
        assert _is_valid_tool_name("-tool") is False
        # 过长名称
        assert _is_valid_tool_name("a" * 65) is False


# ── 发现已安装工具 ──────────────────────────────────────


class TestDiscoverInstalledCLIs:
    """扫描 PATH 中的 CLI-Anything 工具"""

    def setup_method(self):
        """每个测试前清除缓存"""
        import src.integrations.cli_anything_bridge as mod

        mod._cli_cache = []
        mod._cli_cache_ts = 0.0

    @patch("os.listdir")
    @patch("os.path.isdir", return_value=True)
    @patch("os.access", return_value=True)
    @patch("subprocess.run")
    def test_discover_finds_tools(self, mock_run, mock_access, mock_isdir, mock_listdir):
        """正常发现工具"""
        mock_listdir.return_value = ["cli-anything-gimp", "cli-anything-blender", "other-binary"]
        mock_run.return_value = MagicMock(
            stdout="GIMP CLI tool - 控制 GIMP 图像编辑器\nUsage: ...",
            returncode=0,
        )

        with patch.dict(os.environ, {"PATH": "/usr/local/bin"}):
            tools = discover_installed_clis()

        assert len(tools) == 2
        assert tools[0]["name"] == "gimp"
        assert tools[1]["name"] == "blender"
        assert "GIMP" in tools[0]["description"]

    @patch("os.listdir")
    @patch("os.path.isdir", return_value=True)
    @patch("os.access", return_value=True)
    @patch("subprocess.run")
    def test_discover_uses_cache(self, mock_run, mock_access, mock_isdir, mock_listdir):
        """缓存生效时不重新扫描"""
        mock_listdir.return_value = ["cli-anything-test"]
        mock_run.return_value = MagicMock(stdout="test tool", returncode=0)

        with patch.dict(os.environ, {"PATH": "/usr/local/bin"}):
            # 第一次调用：实际扫描
            tools1 = discover_installed_clis()
            assert len(tools1) == 1

            # 第二次调用：使用缓存
            mock_listdir.return_value = ["cli-anything-test", "cli-anything-new"]
            tools2 = discover_installed_clis()
            assert len(tools2) == 1  # 还是 1，因为用了缓存

    def test_discover_empty_path(self):
        """PATH 为空时返回空列表"""
        with patch.dict(os.environ, {"PATH": ""}):
            tools = discover_installed_clis()
        assert tools == []

    @patch("os.listdir")
    @patch("os.path.isdir", return_value=True)
    @patch("os.access", return_value=True)
    @patch("subprocess.run", side_effect=Exception("boom"))
    def test_discover_help_failure(self, mock_run, mock_access, mock_isdir, mock_listdir):
        """--help 执行失败时也能正常返回工具（描述为占位文本）"""
        mock_listdir.return_value = ["cli-anything-broken"]

        with patch.dict(os.environ, {"PATH": "/usr/local/bin"}):
            tools = discover_installed_clis()

        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0]["name"] == "broken"
        assert "无法获取描述" in tools[0]["description"]


# ── 执行 CLI 命令 ──────────────────────────────────────


class TestRunCLICommand:
    """执行 CLI-Anything 工具命令"""

    def setup_method(self):
        import src.integrations.cli_anything_bridge as mod

        mod._cli_cache = []
        mod._cli_cache_ts = 0.0

    @pytest.mark.asyncio
    async def test_invalid_tool_name(self):
        """非法工具名直接拒绝"""
        result = await run_cli_command("rm -rf /")
        assert result["success"] is False
        assert "不合法" in result["output"]

    @pytest.mark.asyncio
    async def test_tool_not_installed(self):
        """工具未安装时报错"""
        with patch(
            "src.integrations.cli_anything_bridge.discover_installed_clis",
            return_value=[],
        ):
            result = await run_cli_command("nonexistent")
        assert result["success"] is False
        assert "未安装" in result["output"]

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """正常执行成功"""
        fake_tools = [{"name": "gimp", "path": "/usr/bin/cli-anything-gimp", "description": "GIMP"}]

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b'{"result": "ok"}', b""))
        mock_proc.returncode = 0
        mock_proc.kill = MagicMock()

        with (
            patch(
                "src.integrations.cli_anything_bridge.discover_installed_clis",
                return_value=fake_tools,
            ),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ),
        ):
            result = await run_cli_command("gimp", ["project", "new"])

        assert result["success"] is True
        assert "ok" in result["output"]
        assert result["exit_code"] == 0
        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execution_timeout(self):
        """超时处理"""
        fake_tools = [{"name": "slow", "path": "/usr/bin/cli-anything-slow", "description": "slow"}]

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.kill = MagicMock()

        with (
            patch(
                "src.integrations.cli_anything_bridge.discover_installed_clis",
                return_value=fake_tools,
            ),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ),
        ):
            result = await run_cli_command("slow", [], timeout=1)

        assert result["success"] is False
        assert "超时" in result["output"]

    @pytest.mark.asyncio
    async def test_execution_failure(self):
        """命令执行失败（非零退出码）"""
        fake_tools = [{"name": "err", "path": "/usr/bin/cli-anything-err", "description": "err"}]

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Error: something went wrong"))
        mock_proc.returncode = 1
        mock_proc.kill = MagicMock()

        with (
            patch(
                "src.integrations.cli_anything_bridge.discover_installed_clis",
                return_value=fake_tools,
            ),
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ),
        ):
            result = await run_cli_command("err", ["bad-arg"])

        assert result["success"] is False
        assert result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        """可执行文件不存在"""
        fake_tools = [{"name": "gone", "path": "/usr/bin/cli-anything-gone", "description": "gone"}]

        with (
            patch(
                "src.integrations.cli_anything_bridge.discover_installed_clis",
                return_value=fake_tools,
            ),
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=FileNotFoundError("No such file"),
            ),
        ):
            result = await run_cli_command("gone")

        assert result["success"] is False
        assert "不存在" in result["output"]


# ── 安装 CLI 工具 ──────────────────────────────────────


class TestInstallCLITool:
    """安装 CLI-Anything 工具"""

    @pytest.mark.parametrize(
        "tool_name",
        ["arbitrary-dependency", "test-tool", "nonexistent", "slow-pkg", "bad name!"],
    )
    @pytest.mark.asyncio
    async def test_remote_install_is_disabled_without_pinned_allowlist(self, tool_name):
        """没有可信精确版本清单时，任意输入都不得触发 pip。"""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=AssertionError("远程安装不得启动子进程"),
        ) as create_subprocess:
            result = await install_cli_tool(tool_name)

        assert result == {
            "success": False,
            "reason": "remote_install_disabled",
            "message": (
                "远程安装已禁用：仓库没有经过审核并固定精确版本的 CLI-Anything 包清单。"
                "请由本机管理员在隔离环境预装工具，再使用 /cli list 发现并通过 /cli run 执行。"
            ),
        }
        create_subprocess.assert_not_awaited()


def test_api_remote_install_fails_with_forbidden_policy(monkeypatch):
    monkeypatch.delenv("OPENCLAW_API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setattr("src.api.auth._API_TOKEN", "")
    client = TestClient(APIServer().app)

    response = client.post(
        "/api/v1/cli/install",
        json={"tool": "arbitrary-dependency"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": CLI_REMOTE_INSTALL_DISABLED_MESSAGE}


# ── CLIAnythingManager 单例 ──────────────────────────────


class TestCLIAnythingManager:
    """管理器单例和状态查询"""

    def setup_method(self):
        # 重置单例
        CLIAnythingManager._instance = None
        import src.integrations.cli_anything_bridge as mod

        mod._cli_cache = []
        mod._cli_cache_ts = 0.0

    def test_singleton(self):
        """单例模式"""
        mgr1 = CLIAnythingManager.get_instance()
        mgr2 = CLIAnythingManager.get_instance()
        assert mgr1 is mgr2

    def test_serializes_calls_across_two_thread_event_loops(self):
        """两个线程的事件循环共享单例时仍严格串行。"""
        manager = CLIAnythingManager.get_instance()
        start = threading.Barrier(3)
        state_lock = threading.Lock()
        active = 0
        peak_active = 0

        async def fake_run(tool_name, args, timeout):
            nonlocal active, peak_active
            with state_lock:
                active += 1
                peak_active = max(peak_active, active)
            try:
                await asyncio.sleep(0.05)
                return {"success": True, "output": tool_name}
            finally:
                with state_lock:
                    active -= 1

        async def invoke(tool_name: str):
            await asyncio.to_thread(start.wait)
            return await manager.run(tool_name)

        results: queue.Queue[tuple[str, Any]] = queue.Queue()
        first_loop: queue.Queue[asyncio.AbstractEventLoop] = queue.Queue()
        second_loop: queue.Queue[asyncio.AbstractEventLoop] = queue.Queue()
        with patch(
            "src.integrations.cli_anything_bridge.run_cli_command",
            side_effect=fake_run,
        ):
            first = _run_async_in_thread(lambda: invoke("first"), results, first_loop)
            second = _run_async_in_thread(lambda: invoke("second"), results, second_loop)
            loops = [first_loop.get(timeout=1), second_loop.get(timeout=1)]
            start.wait(timeout=1)
            first.join(timeout=1)
            second.join(timeout=1)
            for thread, loop in zip((first, second), loops, strict=True):
                _stop_stuck_loop(thread, loop)

        outcomes = [results.get(timeout=1) for _ in range(2)]
        assert not first.is_alive()
        assert not second.is_alive()
        assert [status for status, _ in outcomes] == ["ok", "ok"]
        assert {result["output"] for _, result in outcomes} == {"first", "second"}
        assert peak_active == 1

    def test_cancelled_cross_loop_waiter_does_not_leak_gate(self):
        """跨循环等待超时取消后，串行门仍可被后续调用获取。"""
        manager = CLIAnythingManager.get_instance()
        holder_started = threading.Event()
        release_holder = threading.Event()
        waiter_timed_out = threading.Event()
        entered_tools: list[str] = []
        entered_lock = threading.Lock()

        async def fake_run(tool_name, args, timeout):
            with entered_lock:
                entered_tools.append(tool_name)
            if tool_name == "holder":
                holder_started.set()
                await asyncio.to_thread(release_holder.wait, 1)
            return {"success": True, "output": tool_name}

        async def wait_then_cancel():
            await asyncio.to_thread(holder_started.wait, 1)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(manager.run("cancelled"), timeout=0.05)
            waiter_timed_out.set()
            return "cancelled"

        results: queue.Queue[tuple[str, Any]] = queue.Queue()
        holder_loop: queue.Queue[asyncio.AbstractEventLoop] = queue.Queue()
        waiter_loop: queue.Queue[asyncio.AbstractEventLoop] = queue.Queue()
        with patch(
            "src.integrations.cli_anything_bridge.run_cli_command",
            side_effect=fake_run,
        ):
            holder = _run_async_in_thread(lambda: manager.run("holder"), results, holder_loop)
            assert holder_started.wait(timeout=1)
            waiter = _run_async_in_thread(wait_then_cancel, results, waiter_loop)
            loops = [holder_loop.get(timeout=1), waiter_loop.get(timeout=1)]
            assert waiter_timed_out.wait(timeout=1)
            release_holder.set()
            holder.join(timeout=1)
            waiter.join(timeout=1)
            recovery = asyncio.run(manager.run("recovery"))
            for thread, loop in zip((holder, waiter), loops, strict=True):
                _stop_stuck_loop(thread, loop)

        outcomes = [results.get(timeout=1) for _ in range(2)]
        assert [status for status, _ in outcomes] == ["ok", "ok"]
        assert recovery["output"] == "recovery"
        assert "cancelled" not in entered_tools
        assert entered_tools == ["holder", "recovery"]

    def test_cross_loop_exception_releases_gate(self):
        """一个循环内操作抛错后，另一个循环仍可继续执行。"""
        manager = CLIAnythingManager.get_instance()
        failure_started = threading.Event()
        release_failure = threading.Event()

        async def fake_run(tool_name, args, timeout):
            if tool_name == "failure":
                failure_started.set()
                await asyncio.to_thread(release_failure.wait, 1)
                raise RuntimeError("expected failure")
            return {"success": True, "output": tool_name}

        results: queue.Queue[tuple[str, Any]] = queue.Queue()
        failure_loop: queue.Queue[asyncio.AbstractEventLoop] = queue.Queue()
        recovery_loop: queue.Queue[asyncio.AbstractEventLoop] = queue.Queue()
        with patch(
            "src.integrations.cli_anything_bridge.run_cli_command",
            side_effect=fake_run,
        ):
            failure = _run_async_in_thread(lambda: manager.run("failure"), results, failure_loop)
            assert failure_started.wait(timeout=1)
            recovery = _run_async_in_thread(lambda: manager.run("recovery"), results, recovery_loop)
            loops = [failure_loop.get(timeout=1), recovery_loop.get(timeout=1)]
            time.sleep(0.05)
            release_failure.set()
            failure.join(timeout=1)
            recovery.join(timeout=1)
            for thread, loop in zip((failure, recovery), loops, strict=True):
                _stop_stuck_loop(thread, loop)

        outcomes = [results.get(timeout=1) for _ in range(2)]
        errors = [value for status, value in outcomes if status == "error"]
        successes = [value for status, value in outcomes if status == "ok"]
        assert len(errors) == 1
        assert isinstance(errors[0], RuntimeError)
        assert str(errors[0]) == "expected failure"
        assert successes == [{"success": True, "output": "recovery"}]

    def test_get_status_no_tools(self):
        """没有工具时的状态"""
        with (
            patch("shutil.which", return_value=None),
            patch(
                "src.integrations.cli_anything_bridge.discover_installed_clis",
                return_value=[],
            ),
        ):
            mgr = CLIAnythingManager.get_instance()
            status = mgr.get_status()

        assert status["available"] is False
        assert status["tool_count"] == 0
        assert status["tools"] == []

    def test_get_status_with_tools(self):
        """有工具时的状态"""
        fake_tools = [
            {"name": "gimp", "path": "/usr/bin/cli-anything-gimp", "description": "GIMP CLI"},
        ]
        with (
            patch("shutil.which", return_value="/usr/bin/cli-anything"),
            patch(
                "src.integrations.cli_anything_bridge.discover_installed_clis",
                return_value=fake_tools,
            ),
        ):
            mgr = CLIAnythingManager.get_instance()
            status = mgr.get_status()

        assert status["available"] is True
        assert status["cli_anything_installed"] is True
        assert status["tool_count"] == 1


# ── Telegram 命令解析 ──────────────────────────────────


class TestTelegramCommandParsing:
    """测试命令 Mixin 的帮助文本和静态方法"""

    @pytest.mark.asyncio
    async def test_remote_install_command_returns_disabled_policy_directly(self):
        from src.bot.cmd_cli_mixin import CLICommandsMixin

        update = MagicMock()
        update.message.reply_text = AsyncMock()

        await CLICommandsMixin()._cli_install(update, None, "arbitrary-dependency")

        update.message.reply_text.assert_awaited_once_with(CLI_REMOTE_INSTALL_DISABLED_MESSAGE)

    def test_help_text_content(self):
        """帮助文本包含所有子命令"""
        from src.bot.cmd_cli_mixin import CLICommandsMixin

        text = CLICommandsMixin._cli_help_text()
        assert "/cli list" in text
        assert "/cli run" in text
        assert "/cli install" in text
        assert "/cli help" in text
        assert "/cli status" in text
        assert "远程安装已禁用" in text
        assert "本机管理员" in text
        assert "pip install" not in text

    def test_help_text_has_example(self):
        """帮助文本包含使用示例"""
        from src.bot.cmd_cli_mixin import CLICommandsMixin

        text = CLICommandsMixin._cli_help_text()
        assert "gimp" in text
