"""微信编号命令覆盖回归。"""

from src.api.routers import wechat


def test_numbered_commands_do_not_fall_back_to_generic_llm_without_explanation():
    """每个编号命令要么接真实 API/安全本地处理，要么显式说明为什么不能执行。"""
    special = set(wechat._LOCAL_COMMAND_HANDLERS) | set(wechat._EXPLICIT_UNAVAILABLE_COMMANDS)
    uncovered = []
    for number, (_desc, _needs_arg, func_name) in wechat.NUMBERED_COMMANDS.items():
        if func_name not in wechat._CMD_API_MAP and number not in special:
            uncovered.append(number)

    assert uncovered == []


def test_social_publish_numbered_commands_are_review_only_or_blocked():
    """社媒编号命令不能绕过人工审核闸口直接外发。"""
    for number in (301, 302, 303):
        message = wechat._EXPLICIT_UNAVAILABLE_COMMANDS[number]
        assert "不会自动发布" in message
        assert "人工" in message
