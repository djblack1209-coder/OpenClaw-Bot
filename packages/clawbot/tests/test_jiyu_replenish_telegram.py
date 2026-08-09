"""Telegram 补号安全门面的最小保护合同。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.bot.cmd_jiyu_replenish_mixin import JiyuReplenishCommandsMixin


class _Message:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.markups: list[object] = []

    async def reply_text(self, text: str, **kwargs: object) -> None:
        self.replies.append(text)
        self.markups.append(kwargs.get("reply_markup"))


class _Bot(JiyuReplenishCommandsMixin):
    def _is_authorized(self, user_id: int) -> bool:
        return user_id == 7


def _update(text: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=7),
        effective_chat=SimpleNamespace(id=9, type="private"),
        message=_Message(),
        text=text,
    )


@pytest.mark.asyncio
async def test_remote_replenish_consumes_next_private_text_without_reading_it():
    bot = _Bot()
    update = _update()
    context = SimpleNamespace(args=[])

    await bot.cmd_jiyu_replenish.__wrapped__(bot, update, context)
    assert "远程补号材料提交和远程批次控制均已禁用" in update.message.replies[-1]
    assert update.message.markups[-1] is None

    raw = object()
    accepted = await bot._handle_jiyu_replenish_text(update, raw)

    assert accepted is True
    assert "远程提交内容不会被读取" in update.message.replies[-1]
    assert not hasattr(bot, "_remote_replenish_runner")
    assert 9 not in bot._jiyu_replenish_waiting()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["status", "stop"])
async def test_remote_replenish_status_and_stop_only_report_local_boundary(action: str):
    bot = _Bot()
    update = _update()

    await bot.cmd_jiyu_replenish.__wrapped__(bot, update, SimpleNamespace(args=[action]))

    assert "Telegram 无法查看或控制本地补号批次" in update.message.replies[-1]
    assert not hasattr(bot, "_remote_replenish_runner")


@pytest.mark.asyncio
async def test_legacy_replenish_keyboard_only_reports_local_boundary():
    bot = _Bot()
    update = _update()

    accepted = await bot._handle_jiyu_replenish_text(update, "📊 补号状态")

    assert accepted is True
    assert "Telegram 无法查看或控制本地补号批次" in update.message.replies[-1]
    assert not hasattr(bot, "_remote_replenish_runner")


@pytest.mark.asyncio
async def test_remote_replenish_cancel_only_clears_protection_waiting_state():
    bot = _Bot()
    update = _update()
    bot._jiyu_replenish_waiting().add(update.effective_chat.id)

    await bot.cmd_jiyu_replenish.__wrapped__(bot, update, SimpleNamespace(args=["cancel"]))

    assert update.message.replies[-1] == "已取消保护等待状态。"
    assert update.effective_chat.id not in bot._jiyu_replenish_waiting()


@pytest.mark.asyncio
async def test_remote_replenish_rejects_group_submission():
    bot = _Bot()
    update = _update()
    update.effective_chat.type = "group"
    accepted = await bot._handle_jiyu_replenish_text(update, "anything")
    assert accepted is False
