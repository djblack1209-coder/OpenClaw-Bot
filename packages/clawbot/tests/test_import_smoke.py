"""导入烟雾测试 — 确保所有核心模块可被正常导入

不测试功能逻辑，只验证:
1. 模块无语法错误
2. 依赖链完整（无 ImportError）
3. 顶层代码无运行时异常
"""
import pytest
import importlib


# 所有需要验证的模块路径
MODULES_TO_TEST = [
    "src.agent_tools",
    "src.alpaca_bridge",
    "src.charts",
    "src.data_providers",
    "src.invest_tools",
    "src.message_format",
    "src.monitoring",
    "src.news_fetcher",
    "src.ocr_processors",
    "src.resilience",
    "src.shared_memory",
    "src.smart_memory",
    "src.social_tools",
    "src.strategy_engine",
    "src.telegram_markdown",
    "src.telegram_ux",
    "src.tool_executor",
    "src.universe",
    "src.notify_style",
    "src.message_sender",
    # 新增: 架构重构后的5个拆分Mixin
    "src.bot.cmd_social_mixin",
    "src.bot.cmd_xianyu_mixin",
    "src.bot.cmd_life_mixin",
    "src.bot.cmd_novel_mixin",
    "src.bot.cmd_ops_mixin",
    # 新增: 交易子模块
    "src.trading.reentry_queue",
    # 新增: 核心执行模块
    "src.execution.life_automation",
    "src.deployer.deploy_client",
]


@pytest.mark.parametrize("module_path", MODULES_TO_TEST)
def test_module_import(module_path: str):
    """验证模块可被正常导入"""
    try:
        mod = importlib.import_module(module_path)
        assert mod is not None
    except ImportError as e:
        # 可选依赖缺失是允许的（如 freqtrade, ib_insync）
        if any(pkg in str(e) for pkg in [
            "freqtrade", "ib_insync", "composio", "skyvern",
            "browser_use", "crewai", "langfuse", "docling",
        ]):
            pytest.skip(f"可选依赖缺失: {e}")
        raise
