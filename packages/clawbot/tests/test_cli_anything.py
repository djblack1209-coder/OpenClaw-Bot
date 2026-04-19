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
import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from src.integrations.cli_anything_bridge import (
    _is_valid_tool_name,
    discover_installed_clis,
    run_cli_command,
    install_cli_tool,
    CLIAnythingManager,
    _cli_cache,
    _CLI_CACHE_TTL,
)


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

        with patch(
            "src.integrations.cli_anything_bridge.discover_installed_clis",
            return_value=fake_tools,
        ), patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
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

        with patch(
            "src.integrations.cli_anything_bridge.discover_installed_clis",
            return_value=fake_tools,
        ), patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
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

        with patch(
            "src.integrations.cli_anything_bridge.discover_installed_clis",
            return_value=fake_tools,
        ), patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await run_cli_command("err", ["bad-arg"])

        assert result["success"] is False
        assert result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        """可执行文件不存在"""
        fake_tools = [{"name": "gone", "path": "/usr/bin/cli-anything-gone", "description": "gone"}]

        with patch(
            "src.integrations.cli_anything_bridge.discover_installed_clis",
            return_value=fake_tools,
        ), patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("No such file"),
        ):
            result = await run_cli_command("gone")

        assert result["success"] is False
        assert "不存在" in result["output"]


# ── 安装 CLI 工具 ──────────────────────────────────────


class TestInstallCLITool:
    """安装 CLI-Anything 工具"""

    @pytest.mark.asyncio
    async def test_invalid_name(self):
        """非法名称拒绝安装"""
        result = await install_cli_tool("bad name!")
        assert result["success"] is False
        assert "不合法" in result["message"]

    @pytest.mark.asyncio
    async def test_successful_install(self):
        """正常安装成功"""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Successfully installed cli-anything-test", b"")
        )
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await install_cli_tool("test-tool")

        assert result["success"] is True
        assert "成功" in result["message"]

    @pytest.mark.asyncio
    async def test_install_failure(self):
        """安装失败"""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"ERROR: No matching distribution found")
        )
        mock_proc.returncode = 1

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await install_cli_tool("nonexistent")

        assert result["success"] is False
        assert "失败" in result["message"]

    @pytest.mark.asyncio
    async def test_install_timeout(self):
        """安装超时"""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await install_cli_tool("slow-pkg")

        assert result["success"] is False
        assert "超时" in result["message"]


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

    def test_get_status_no_tools(self):
        """没有工具时的状态"""
        with patch("shutil.which", return_value=None), patch(
            "src.integrations.cli_anything_bridge.discover_installed_clis",
            return_value=[],
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
        with patch("shutil.which", return_value="/usr/bin/cli-anything"), patch(
            "src.integrations.cli_anything_bridge.discover_installed_clis",
            return_value=fake_tools,
        ):
            mgr = CLIAnythingManager.get_instance()
            status = mgr.get_status()

        assert status["available"] is True
        assert status["cli_anything_installed"] is True
        assert status["tool_count"] == 1


# ── Telegram 命令解析 ──────────────────────────────────


class TestTelegramCommandParsing:
    """测试命令 Mixin 的帮助文本和静态方法"""

    def test_help_text_content(self):
        """帮助文本包含所有子命令"""
        from src.bot.cmd_cli_mixin import CLICommandsMixin

        text = CLICommandsMixin._cli_help_text()
        assert "/cli list" in text
        assert "/cli run" in text
        assert "/cli install" in text
        assert "/cli help" in text
        assert "/cli status" in text

    def test_help_text_has_example(self):
        """帮助文本包含使用示例"""
        from src.bot.cmd_cli_mixin import CLICommandsMixin

        text = CLICommandsMixin._cli_help_text()
        assert "gimp" in text
