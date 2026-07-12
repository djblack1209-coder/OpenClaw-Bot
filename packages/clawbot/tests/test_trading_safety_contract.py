"""交易高风险写操作的静态安全合同。"""

from __future__ import annotations

import ast
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def _confirmed_call_sites() -> set[tuple[str, str]]:
    """收集生产代码中所有硬编码 human_confirmed=True 的函数位置。"""
    sites: set[tuple[str, str]] = set()
    for path in SRC_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            confirmed = any(
                keyword.arg == "human_confirmed"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
            if not confirmed:
                continue

            current: ast.AST | None = node
            function_name = "<module>"
            while current in parents:
                current = parents[current]
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function_name = current.name
                    break
            sites.add((path.relative_to(SRC_ROOT).as_posix(), function_name))
    return sites


def test_live_trade_confirmation_can_only_be_granted_by_existing_manual_paths():
    """新增调用方不能靠布尔值自行把自动任务升级为实盘交易。"""
    assert _confirmed_call_sites() == {
        ("auto_trader.py", "confirm_proposal"),
        ("bot/callback_mixin.py", "handle_trade_callback"),
        ("trading_pipeline.py", "execute_proposal"),
    }


def _function_calls(path: Path, function_name: str) -> set[str]:
    """返回指定函数中的调用名称，供关键入口做静态回归保护。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            calls: set[str] = set()
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                    calls.add(f"{call.func.value.id}.{call.func.attr}")
            return calls
    raise AssertionError(f"未找到函数: {function_name}")


def test_buy_and_sell_commands_are_simulation_only():
    """普通 /buy、/sell 不能偷偷尝试实盘，也不能发布真实成交事件。"""
    path = SRC_ROOT / "bot" / "cmd_invest_mixin.py"
    for function_name in ("cmd_buy", "cmd_sell"):
        calls = _function_calls(path, function_name)
        assert "ibkr.buy" not in calls
        assert "ibkr.sell" not in calls
        assert "bus.publish" not in calls
