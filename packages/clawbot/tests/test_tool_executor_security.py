"""ToolExecutor、BashTool 与自主 Agent 组合边界测试。"""

from unittest.mock import MagicMock, patch

import pytest

from src.tool_executor import ToolExecutor


@pytest.mark.asyncio
async def test_bash_dispatch_uses_bash_tool_execute(tmp_path):
    executor = ToolExecutor(working_dir=str(tmp_path))
    executor.bash_tool.execute = MagicMock(
        return_value={"success": True, "stdout": str(tmp_path), "stderr": "", "returncode": 0}
    )

    result = await executor.execute("bash", {"command": "pwd"})

    assert result["success"] is True
    executor.bash_tool.execute.assert_called_once_with("pwd", None)


def test_smolagent_uses_tool_calls_without_local_code_executor():
    """自主 Agent 只能调用显式工具，不能让模型生成本地 Python。"""
    from src import agent_tools

    agent = MagicMock()
    agent.run.return_value = "只读分析完成"
    with patch.object(agent_tools, "LiteLLMModel", return_value=MagicMock()), patch.object(
        agent_tools,
        "ToolCallingAgent",
        return_value=agent,
    ) as constructor:
        result = agent_tools._run_agent_sync("分析 AAPL", "test-model", [])

    assert result == "只读分析完成"
    constructor.assert_called_once()
    kwargs = constructor.call_args.kwargs
    assert kwargs["tools"] == []
    assert kwargs["max_tool_threads"] == 1
    assert "additional_authorized_imports" not in kwargs
