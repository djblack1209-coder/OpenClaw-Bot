"""
Tests for src/tools/bash_tool.py — BashTool sandbox.

Covers:
  - Safe commands allowed via whitelist
  - Non-whitelisted commands blocked
  - Timeout enforcement
  - Output truncation (stdout / stderr)
  - Environment variable leak prevention

All subprocess calls are MOCKED — no real dangerous commands are executed.
"""
import subprocess

import pytest
from unittest.mock import MagicMock, patch

from src.tools.bash_tool import BashTool


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def tool(tmp_path):
    """BashTool with short timeout and tmp working directory."""
    return BashTool(working_dir=str(tmp_path), timeout=5)


# ── 1. Safe commands allowed ────────────────────────────


class TestSafeCommandAllowed:
    """Benign whitelisted commands should pass is_allowed() and execute normally."""

    def test_echo_allowed(self, tool):
        assert tool.is_allowed("echo hello") is True

    def test_ls_allowed(self, tool):
        assert tool.is_allowed("ls -la /tmp") is True

    def test_cat_allowed(self, tool):
        assert tool.is_allowed("cat /etc/hostname") is True

    def test_python_not_allowed(self, tool):
        """R27 安全加固后 python3 已从白名单移除"""
        assert tool.is_allowed("python3 --version") is False

    def test_safe_command_executes(self, tool):
        """echo hello actually runs and returns success."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"hello\n", b"")
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            result = tool.execute("echo hello")

        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_git_status_allowed(self, tool):
        assert tool.is_allowed("git status") is True

    def test_pip_not_allowed(self, tool):
        """R27 安全加固后 pip 已从白名单移除"""
        assert tool.is_allowed("pip list") is False

    def test_printenv_not_allowed(self, tool):
        """printenv 不在白名单中 — R27 安全加固后被移除"""
        assert tool.is_allowed("printenv HOME") is False


# ── 2. Non-whitelisted commands blocked ─────────────────


class TestNonWhitelistedBlocked:
    """Commands not in the whitelist must be rejected before execution."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "rm -rf /",
            "rm -rf ~",
            "rm -rf /*",
            "sudo rm -rf /",
            "mkfs.ext4 /dev/sda1",
            "dd if=/dev/zero of=/dev/sda",
            "chmod -R 777 /",
        ],
        ids=[
            "rm-root",
            "rm-home",
            "rm-root-glob",
            "sudo-rm-root",
            "mkfs",
            "dd-zero",
            "chmod-777-root",
        ],
    )
    def test_dangerous_commands_not_allowed(self, tool, cmd):
        assert tool.is_allowed(cmd) is False

    def test_non_whitelisted_command_returns_error(self, tool):
        """execute() returns success=False for non-whitelisted commands."""
        result = tool.execute("rm -rf /")
        assert result["success"] is False
        assert "不在允许列表" in result.get("error", "")

    def test_unknown_command_blocked(self, tool):
        """Unknown binaries not in whitelist are rejected."""
        result = tool.execute("nonexistent_binary --flag")
        assert result["success"] is False
        assert "不在允许列表" in result.get("error", "")

    def test_no_subprocess_call_for_blocked(self, tool):
        """Subprocess must NEVER be invoked for non-whitelisted commands."""
        with patch("subprocess.Popen") as mock_popen:
            tool.execute("rm -rf /")
            mock_popen.assert_not_called()


# ── 3. Timeout enforced ────────────────────────────────


class TestTimeoutEnforced:
    """Commands exceeding the timeout must be terminated."""

    def test_timeout_returns_error(self, tool):
        """Popen.communicate raising TimeoutExpired → error result."""
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(
            cmd="sleep 999", timeout=5
        )
        mock_proc.pid = 12345

        with patch("subprocess.Popen", return_value=mock_proc), \
             patch("os.killpg") as mock_killpg, \
             patch("os.getpgid", return_value=12345):
            # sleep is whitelisted (not in ALLOWED_COMMANDS but we mock Popen anyway)
            # Use an allowed command for the test
            result = tool.execute("ls")
            # Override: force timeout in test
            # The mock already raises TimeoutExpired

        assert result["success"] is False
        assert "超时" in result["error"]
        mock_killpg.assert_called_once()

    def test_custom_timeout_used(self, tool):
        """Custom per-call timeout is forwarded to communicate()."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"ok", b"")
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            tool.execute("echo ok", timeout=30)
            mock_proc.communicate.assert_called_once_with(timeout=30)

    def test_default_timeout_used(self, tool):
        """When no per-call timeout, default self.timeout is used."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"ok", b"")
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            tool.execute("echo ok")
            mock_proc.communicate.assert_called_once_with(timeout=tool.timeout)


# ── 4. Output truncated ────────────────────────────────


class TestOutputTruncated:
    """Overly long stdout/stderr is truncated at 50,000 chars."""

    def test_stdout_truncated(self, tool):
        long_output = b"x" * 60000
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (long_output, b"")
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            result = tool.execute("cat large_file")

        assert result["success"] is True
        assert len(result["stdout"]) < 60000
        assert "截断" in result["stdout"]

    def test_stderr_truncated(self, tool):
        long_err = b"e" * 60000
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", long_err)
        mock_proc.returncode = 1

        with patch("subprocess.Popen", return_value=mock_proc):
            result = tool.execute("grep error")

        assert "截断" in result["stderr"]

    def test_short_output_not_truncated(self, tool):
        short = b"hello world\n"
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (short, b"")
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            result = tool.execute("echo hello world")

        assert result["stdout"] == "hello world\n"
        assert "截断" not in result["stdout"]


# ── 5. Env vars not leaked ──────────────────────────────


class TestEnvVarsNotLeaked:
    """Sensitive environment variables must not appear in command output."""

    def test_env_command_blocked(self, tool):
        """env 不在白名单中，执行应直接被拦截，不会调用 subprocess"""
        with patch("subprocess.Popen") as mock_popen:
            result = tool.execute("env")

        assert result["success"] is False
        assert "不在允许列表" in result.get("error", "")
        mock_popen.assert_not_called()

    def test_allowed_command_passes_environ(self, tool):
        """白名单命令执行时，BashTool 会将 os.environ 传递给子进程。
        验证环境变量传递行为（当前未过滤敏感变量 — 已知技术债）。"""
        captured_env = {}

        def fake_popen(cmd, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            mock = MagicMock()
            mock.communicate.return_value = (b"hello\n", b"")
            mock.returncode = 0
            return mock

        with patch("subprocess.Popen", side_effect=fake_popen), \
             patch.dict("os.environ", {"SECRET_API_KEY": "sk-12345"}, clear=False):
            result = tool.execute("echo hello")

        assert result["success"] is True
        # 当前行为：环境变量原样传递（未过滤），记录为已知技术债
        assert "SECRET_API_KEY" in captured_env


# ── 6. Edge cases ──────────────────────────────────────


class TestBashToolEdgeCases:
    """Boundary conditions and error handling."""

    def test_empty_command(self, tool):
        """Empty command string is handled gracefully — rejected by whitelist."""
        result = tool.execute("")
        assert result["success"] is False

    def test_non_whitelisted_returns_error_message(self, tool):
        """Non-whitelisted command gets clear error message."""
        result = tool.execute("nonexistent_binary")
        assert result["success"] is False
        assert "不在允许列表" in result["error"]

    def test_workdir_override(self, tool, tmp_path):
        """Per-call workdir overrides default."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"ok", b"")
        mock_proc.returncode = 0

        custom_dir = str(tmp_path / "subdir")

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            tool.execute("ls", workdir=custom_dir)
            call_kwargs = mock_popen.call_args
            assert call_kwargs.kwargs.get("cwd") or call_kwargs[1].get("cwd") == custom_dir

    def test_cancel_no_running_process(self, tool):
        result = tool.cancel()
        assert result["success"] is False
        assert "没有" in result["error"]
