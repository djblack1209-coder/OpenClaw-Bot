"""CodeTool Python 沙箱的可运行性与 fail-closed 测试。"""

from unittest.mock import MagicMock

from src.tools import code_tool as code_tool_module
from src.tools.code_tool import CodeTool


def test_python_sandbox_runs_safe_code():
    result = CodeTool(timeout=5).execute_python("print(2 + 2)")

    assert result["success"] is True
    assert result["stdout"].strip() == "4"


def test_python_sandbox_blocks_imports():
    result = CodeTool(timeout=5).execute_python("import math\nprint(math.sqrt(16))")

    assert result["success"] is False
    assert "ImportError" in result["stderr"] or "import" in result["stderr"].lower()


def test_restricted_python_unexpected_error_is_fail_closed(monkeypatch):
    tool = CodeTool(timeout=5)
    tool._has_restricted_python = True
    execute = MagicMock()
    monkeypatch.setattr(tool, "_execute_in_subprocess", execute)
    monkeypatch.setattr(
        code_tool_module,
        "_try_compile_restricted",
        MagicMock(side_effect=ValueError("compiler failure")),
    )

    result = tool.execute_python("print('safe')")

    assert result["success"] is False
    assert "安全检查" in result["error"]
    execute.assert_not_called()


def test_missing_restricted_python_is_fail_closed(monkeypatch):
    tool = CodeTool(timeout=5)
    tool._has_restricted_python = False
    execute = MagicMock()
    monkeypatch.setattr(tool, "_execute_in_subprocess", execute)

    result = tool.execute_python("print('safe')")

    assert result["success"] is False
    assert "RestrictedPython" in result["error"]
    execute.assert_not_called()


def test_python_sandbox_blocks_dangerous_import():
    result = CodeTool(timeout=5).execute_python("import os\nprint(os.getcwd())")

    assert result["success"] is False
    assert "ImportError" in result["stderr"] or "import" in result["stderr"].lower()


def test_python_sandbox_blocks_allowed_module_escape():
    code = (
        "import dataclasses\n"
        "print(dataclasses.sys.modules['builtins'].open('/etc/hosts').read())"
    )

    result = CodeTool(timeout=5).execute_python(code)

    assert result["success"] is False
    assert "localhost" not in result.get("stdout", "")


def test_node_execution_is_disabled():
    code = "console.log(require('fs').readFileSync('/etc/hosts', 'utf8'))"

    result = CodeTool(timeout=5).execute_node(code)

    assert result["success"] is False
    assert "禁用" in result["error"]
    assert "localhost" not in result.get("stdout", "")
