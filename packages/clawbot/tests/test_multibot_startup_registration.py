import pytest

from src.bot.globals import chat_router, health_checker
from src.bot.cmd_cli_mixin import CLICommandsMixin
from src.bot.multi_bot import MultiBot


@pytest.mark.asyncio
async def test_missing_token_bot_does_not_leave_phantom_health_or_route():
    """启动前失败的 Bot 不应残留在健康检查和群聊路由里。"""
    bot_id = "startup_missing_token_regression"
    health_checker._bot_status.pop(bot_id, None)
    chat_router.bots.pop(bot_id, None)

    bot = MultiBot(
        {
            "id": bot_id,
            "token": "",
            "username": "startup_missing_token_regression_bot",
            "model": "test-model",
            "api_type": "free_pool",
            "is_claude": False,
            "keywords": ["startup-missing-token"],
            "commands": [],
        }
    )

    assert bot_id not in health_checker.get_status()
    assert bot_id not in chat_router.bots

    result = await bot.run_async()

    assert result is None
    assert bot_id not in health_checker.get_status()
    assert bot_id not in chat_router.bots


def test_cli_command_mixin_is_registered_on_multibot_and_command_table():
    """CLICommandsMixin 不再是死代码，MultiBot 需要注册 /cli 命令入口。"""
    source = __import__("inspect").getsource(MultiBot.run_async)

    assert issubclass(MultiBot, CLICommandsMixin)
    assert 'CommandHandler("cli", self.cmd_cli)' in source
