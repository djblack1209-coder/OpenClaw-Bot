"""Telegram 远程补号入口的最小脱敏合同。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.bot.cmd_jiyu_replenish_mixin import JiyuReplenishCommandsMixin
from src.sub2_replenish.runner import ReplenishRunner


class _Message:
    def __init__(self) -> None:
        self.replies: list[str] = []
        self.markups: list[object] = []

    async def reply_text(self, text: str, **kwargs: object) -> None:
        self.replies.append(text)
        self.markups.append(kwargs.get("reply_markup"))


class _Bot(JiyuReplenishCommandsMixin):
    def __init__(self) -> None:
        self._remote_replenish_runner = ReplenishRunner(dry_run=True)

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
async def test_remote_replenish_accepts_private_payload_without_echoing_secret():
    bot = _Bot()
    update = _update()
    context = SimpleNamespace(args=[])

    await bot.cmd_jiyu_replenish.__wrapped__(bot, update, context)
    assert "一键补号" in update.message.replies[-1]
    assert update.message.markups[-1].keyboard[0][0].text == "🧾 一键补号"

    raw = "person@example.test----never-log-password----JBSWY3DPEHPK3PXP"
    accepted = await bot._handle_jiyu_replenish_text(update, raw)
    await asyncio.sleep(0)

    assert accepted is True
    assert "已接收 1 个号源" in update.message.replies[-1]
    assert all(secret not in "\n".join(update.message.replies) for secret in ("never-log-password", "JBSWY3DPEHPK3PXP"))
    await bot._remote_replenish_runner.stop()


@pytest.mark.asyncio
async def test_remote_replenish_rejects_group_submission():
    bot = _Bot()
    update = _update()
    update.effective_chat.type = "group"
    accepted = await bot._handle_jiyu_replenish_text(update, "anything")
    assert accepted is False
