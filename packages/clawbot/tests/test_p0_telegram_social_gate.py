"""Telegram 社媒命令不得绕过不可变草稿发布门。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.bot.cmd_social_mixin import SocialCommandsMixin
from src.bot.globals import execution_hub


def _telegram_objects(args: list[str]):
    """构造最小 Telegram update/context 桩。"""
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=123),
        effective_user=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        args=args,
        user_data={},
        bot=SimpleNamespace(send_chat_action=AsyncMock()),
    )
    return update, context


async def test_multimedia_publish_command_never_calls_sau_publishers():
    bot = SocialCommandsMixin()
    update, context = _telegram_objects(["douyin", "/tmp/video.mp4", "标题"])

    with patch("src.sau_bridge.publish_video", new_callable=AsyncMock) as video, patch(
        "src.sau_bridge.publish_note",
        new_callable=AsyncMock,
    ) as note:
        await SocialCommandsMixin.cmd_publish.__wrapped__(bot, update, context)

    video.assert_not_called()
    note.assert_not_called()
    assert "已阻止多媒体直发" in update.message.reply_text.await_args.args[0]


async def test_legacy_preview_callback_only_approves_before_second_confirmation():
    bot = SocialCommandsMixin()
    bot._is_authorized = lambda _user_id: True
    query = SimpleNamespace(
        data="social_confirm:publish",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        args=[],
        user_data={
            "pending_social_package": {
                "results": {"x": {"draft": {"draft_id": "draft-x-1"}}}
            }
        },
    )

    with patch.object(
        execution_hub,
        "update_social_draft_status",
        return_value={"success": True},
    ) as approve, patch.object(
        execution_hub,
        "_publish_social_package",
        create=True,
    ) as legacy_publish, patch.object(
        execution_hub,
        "publish_social_draft",
    ) as publish:
        await bot.handle_social_confirm_callback(update, context)

    approve.assert_called_once_with("draft-x-1", "approved")
    legacy_publish.assert_not_called()
    publish.assert_not_called()
    assert context.user_data["pending_social_final_drafts"] == [
        {"draft_id": "draft-x-1", "platform": "x"}
    ]


async def test_preview_second_confirmation_signs_token_and_publishes_once():
    bot = SocialCommandsMixin()
    bot._is_authorized = lambda _user_id: True
    query = SimpleNamespace(
        data="social_confirm:final_all",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_user=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        args=[],
        user_data={
            "pending_social_final_drafts": [
                {"draft_id": "draft-x-1", "platform": "x"}
            ]
        },
    )

    with patch.object(
        execution_hub,
        "final_confirm_social_draft",
        return_value={"success": True, "confirmation_token": "one-time-token"},
    ) as confirm, patch.object(
        execution_hub,
        "publish_social_draft",
        return_value={"success": True, "url": "https://x.com/demo/status/1"},
    ) as publish:
        await bot.handle_social_confirm_callback(update, context)

    confirm.assert_called_once_with("draft-x-1", "telegram")
    publish.assert_called_once_with("x", "draft-x-1", "one-time-token")
    assert "pending_social_final_drafts" not in context.user_data


@pytest.mark.parametrize(
    ("platform", "command_platform"),
    [("x", "x"), ("xiaohongshu", "xiaohongshu")],
)
async def test_x_and_xhs_commands_follow_approve_then_token_publish(
    platform,
    command_platform,
):
    bot = SocialCommandsMixin()
    update, context = _telegram_objects(["approve", "draft-1"])
    draft = {"id": "draft-1", "platform": platform, "review_status": "pending"}

    with patch.object(execution_hub, "get_social_draft", return_value=draft), patch.object(
        execution_hub,
        "update_social_draft_status",
        return_value={"success": True},
    ) as approve, patch.object(
        execution_hub,
        "final_confirm_social_draft",
        return_value={"success": True, "confirmation_token": "token-1"},
    ) as confirm, patch.object(
        execution_hub,
        "publish_social_draft",
        return_value={"success": True, "url": "https://example.test/post"},
    ) as publish:
        await bot._cmd_gated_social_post(update, context, command_platform)
        context.args = ["publish", "draft-1"]
        await bot._cmd_gated_social_post(update, context, command_platform)

    approve.assert_called_once_with("draft-1", "approved")
    confirm.assert_called_once_with("draft-1", "telegram")
    publish.assert_called_once_with(platform, "draft-1", "token-1")
