"""微信入口不得把聊天内容写日志，也不能让内存状态无限增长。"""

import logging
from unittest.mock import AsyncMock, patch

from src.api.routers import wechat


async def test_incoming_logs_only_metadata_not_raw_chat(caplog):
    user_id = "wx-sensitive-user-123456"
    message = "这是不能进入日志的私人问题"
    reply = "这是不能进入日志的私人回答"

    with patch.object(wechat, "_generate_wechat_reply", new=AsyncMock(return_value=reply)):
        with caplog.at_level(logging.INFO, logger="src.api.routers.wechat"):
            result = await wechat.wechat_incoming(
                wechat.WeChatIncomingRequest(from_user=user_id, text=message)
            )

    assert result.reply == reply
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert user_id not in log_text
    assert message not in log_text
    assert reply not in log_text
    assert "text_length=" in log_text


async def test_empty_sender_is_rejected_without_calling_llm():
    llm = AsyncMock(return_value="不应被调用")
    with patch.object(wechat, "_generate_wechat_reply", new=llm):
        result = await wechat.wechat_incoming(
            wechat.WeChatIncomingRequest(from_user="   ", text="你好")
        )

    assert "无法识别发送者" in result.reply
    llm.assert_not_awaited()


async def test_numbered_command_url_encodes_user_argument():
    self_call = AsyncMock(return_value={"symbol": "AAPL"})
    with patch.object(wechat, "_self_call_api", new=self_call):
        await wechat._execute_numbered_cmd(
            200,
            "AAPL&limit=999#fragment",
            from_user="wx-test-user",
        )

    called_path = self_call.await_args.args[0]
    assert "AAPL%26limit%3D999%23fragment" in called_path
    assert "&limit=999" not in called_path


def test_runtime_conversation_state_is_bounded():
    wechat._wechat_memory.clear()
    wechat._wechat_pending_actions.clear()
    try:
        for index in range(1050):
            wechat._add_to_history(f"wx-user-{index}", "user", "hello")
        assert len(wechat._wechat_memory) <= 1000
    finally:
        wechat._wechat_memory.clear()
        wechat._wechat_pending_actions.clear()
