"""Telegram 鉴权与启动配置的安全边界测试。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.callback_mixin import CallbackMixin
from src.bot.cmd_basic.callback_mixin import _CallbackMixin
from src.bot.cmd_basic.help_mixin import _HelpMixin
from src.bot.cmd_basic.memory_mixin import _MemoryMixin
from src.bot.cmd_basic.onboarding_mixin import _OnboardingMixin
from src.bot.cmd_basic.settings_mixin import _SettingsMixin
from src.bot.cmd_basic.tools_mixin import _ToolsMixin
from src.bot.cmd_intel_mixin import IntelCommandMixin
from src.bot.cmd_invest_mixin import InvestCommandsMixin
from src.bot.cmd_ops_mixin import OpsCommandsMixin
from src.bot.cmd_social_mixin import SocialCommandsMixin
from src.bot.config import parse_ids
from src.bot.multi_bot import MultiBot
from src.bot.ocr_mixin import OCRHandlerMixin
from src.bot.voice_handler import VoiceHandlerMixin
from src.core import config_validator
from src.gateway.telegram_gateway import OpenClawGateway, start_gateway


def test_parse_ids_only_accepts_positive_numeric_ids():
    assert parse_ids("abc, 123, -5, 0, 456x") == {123}


def test_multibot_empty_whitelist_denies_everyone(monkeypatch):
    monkeypatch.setattr("src.bot.multi_bot.ALLOWED_USER_IDS", set())
    assert MultiBot._is_authorized(None, 123) is False


def test_gateway_empty_whitelist_denies_everyone():
    gateway = OpenClawGateway(token="token", admin_user_ids=[])
    assert gateway._check_authorized(123) is False


@pytest.mark.asyncio
async def test_standalone_gateway_refuses_invalid_whitelist(monkeypatch):
    monkeypatch.setenv("OMEGA_GATEWAY_BOT_TOKEN", "configured-token")
    monkeypatch.delenv("ALLOWED_USER_IDS", raising=False)
    monkeypatch.setenv("OMEGA_ADMIN_USER_IDS", "invalid,0,-1")

    assert await start_gateway() is None


@pytest.mark.asyncio
async def test_direct_gateway_start_refuses_empty_whitelist(monkeypatch):
    """直接实例化也必须在构建 PTB Application 前拒绝空白名单。"""
    builder = MagicMock()
    monkeypatch.setattr("src.gateway.telegram_gateway.Application.builder", builder)
    gateway = OpenClawGateway(token="configured-token", admin_user_ids=[])

    await gateway.start()

    assert gateway._app is None
    builder.assert_not_called()


def test_invalid_whitelist_is_startup_error(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "invalid,still-invalid")

    errors, _warnings = config_validator.validate_startup_config()

    assert any("ALLOWED_USER_IDS" in error for error in errors)


def test_valid_whitelist_is_not_startup_error(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "123,456")

    errors, _warnings = config_validator.validate_startup_config()

    assert not any("ALLOWED_USER_IDS" in error for error in errors)


def test_require_valid_startup_config_raises_on_errors(monkeypatch):
    monkeypatch.setattr(
        config_validator,
        "validate_startup_config",
        lambda: (["ALLOWED_USER_IDS 无有效用户"], []),
    )
    monkeypatch.setattr(config_validator, "log_validation_results", lambda errors, warnings: False)

    with pytest.raises(config_validator.StartupConfigError):
        config_validator.require_valid_startup_config()


def test_env_only_deployment_does_not_require_dotenv_file(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "123")
    monkeypatch.setenv("QWEN235B_TOKEN", "telegram-token")
    monkeypatch.setenv("SILICONFLOW_KEYS", "llm-key")
    original_exists = Path.exists

    def _exists(path):
        if path.name == ".env":
            return False
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", _exists)

    errors, warnings = config_validator.validate_startup_config()

    assert not any("config/.env" in error for error in errors)
    assert any("config/.env" in warning for warning in warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "callback",
    [
        _MemoryMixin.handle_feedback_callback,
        _MemoryMixin.handle_memory_callback,
        _HelpMixin.handle_help_callback,
        _CallbackMixin.handle_card_action_callback,
        _CallbackMixin.handle_clarification_callback,
        _SettingsMixin.handle_settings_callback,
        IntelCommandMixin.handle_intel_callback,
        _OnboardingMixin.onboard_interests,
        _OnboardingMixin.onboard_style,
        _OnboardingMixin.onboard_cancel,
        _OnboardingMixin._onboard_text_fallback,
    ],
)
async def test_callback_entry_points_deny_before_business_logic(callback):
    """群聊中的未授权成员点击按钮时，不得进入任何回调业务。"""
    query = SimpleNamespace(answer=AsyncMock(), data="untrusted")
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        callback_query=query,
    )
    context = SimpleNamespace(args=[], user_data={})
    handler = SimpleNamespace(_is_authorized=MagicMock(return_value=False))

    await callback(handler, update, context)

    handler._is_authorized.assert_called_once_with(999)
    query.answer.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("callback", "callback_data"),
    [
        (CallbackMixin.handle_suggest_callback, "suggest:继续"),
        (CallbackMixin.handle_trade_callback, "itrade_cancel:test"),
        (_CallbackMixin.handle_notify_action_callback, "cmd:/status"),
        (SocialCommandsMixin.handle_social_confirm_callback, "social_confirm:publish"),
        (OpsCommandsMixin.handle_ops_menu_callback, "ops_task"),
        (InvestCommandsMixin.handle_quote_action_callback, "buy_AAPL"),
    ],
)
async def test_manually_guarded_callbacks_deny_before_dispatch(callback, callback_data):
    """未授权按钮只能返回告警，不得进入对应业务分发。"""
    query = SimpleNamespace(answer=AsyncMock(), data=callback_data)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        callback_query=query,
    )
    handler = SimpleNamespace(_is_authorized=MagicMock(return_value=False))

    await callback(handler, update, SimpleNamespace(args=[], user_data={}))

    handler._is_authorized.assert_called_once_with(999)
    assert query.answer.await_count == 2


@pytest.mark.asyncio
async def test_voice_denies_before_download_or_transcription():
    """语音入口必须在下载音频和调用转写服务前鉴权。"""
    get_file = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        effective_chat=SimpleNamespace(id=1),
        message=SimpleNamespace(
            voice=SimpleNamespace(file_id="voice-file"),
            audio=None,
        ),
    )
    context = SimpleNamespace(bot=SimpleNamespace(get_file=get_file), user_data={})
    handler = SimpleNamespace(_is_authorized=MagicMock(return_value=False))

    await VoiceHandlerMixin.handle_voice(handler, update, context)

    handler._is_authorized.assert_called_once_with(999)
    get_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_inline_query_denies_before_search(monkeypatch):
    stock_quote = AsyncMock(return_value={})
    crypto_quote = AsyncMock(return_value={})
    memory_search = MagicMock(return_value={"results": []})
    monkeypatch.setattr("src.invest_tools.get_stock_quote", stock_quote)
    monkeypatch.setattr("src.invest_tools.get_crypto_quote", crypto_quote)
    monkeypatch.setattr(
        "src.smart_memory.get_smart_memory",
        MagicMock(return_value=SimpleNamespace(memory=SimpleNamespace(search=memory_search))),
    )
    query = SimpleNamespace(query="AAPL", answer=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        inline_query=query,
    )
    handler = SimpleNamespace(_is_authorized=MagicMock(return_value=False))

    await _ToolsMixin.handle_inline_query(handler, update, SimpleNamespace())

    handler._is_authorized.assert_called_once_with(999)
    query.answer.assert_not_awaited()
    stock_quote.assert_not_awaited()
    crypto_quote.assert_not_awaited()
    memory_search.assert_not_called()


@pytest.mark.asyncio
async def test_claude_prompt_never_reaches_terminal_subprocess():
    """即使授权用户构造 Shell 片段，也只能收到禁用提示。"""
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(id=1),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace(
        args=["code", '\\"; /bin/echo TELEGRAM_PROMPT_INJECTION; #'],
        bot=SimpleNamespace(send_chat_action=AsyncMock()),
    )
    handler = SimpleNamespace(_is_authorized=MagicMock(return_value=True))

    with patch("subprocess.Popen") as popen:
        await _ToolsMixin.cmd_claude_code(handler, update, context)

    popen.assert_not_called()
    assert "已关闭带消息启动" in update.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_photo_denies_before_download(monkeypatch):
    download = AsyncMock()
    get_file = AsyncMock(return_value=SimpleNamespace(download_to_memory=download))
    reply_text = AsyncMock(return_value=SimpleNamespace(delete=AsyncMock()))
    monkeypatch.setattr(
        "src.bot.ocr_mixin.ocr_image",
        AsyncMock(return_value=SimpleNamespace(ok=False, error="stop", text="", cached=False)),
    )
    monkeypatch.setattr("src.tools.vision.analyze_image", AsyncMock(return_value=""))
    monkeypatch.setattr("src.bot.ocr_mixin.send_long_message", AsyncMock())
    context = SimpleNamespace(bot=SimpleNamespace(get_file=get_file))
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        effective_chat=SimpleNamespace(id=1, type="private"),
        message=SimpleNamespace(
            caption="",
            message_id=1,
            photo=[SimpleNamespace(file_id="photo", file_unique_id="photo-unique")],
            reply_text=reply_text,
        ),
    )
    handler = SimpleNamespace(_is_authorized=MagicMock(return_value=False))

    await OCRHandlerMixin.handle_photo(handler, update, context)

    handler._is_authorized.assert_called_once_with(999)
    get_file.assert_not_awaited()
    download.assert_not_awaited()


@pytest.mark.asyncio
async def test_document_denies_before_download(monkeypatch):
    download = AsyncMock()
    get_file = AsyncMock(return_value=SimpleNamespace(download_to_memory=download))
    reply_text = AsyncMock(return_value=SimpleNamespace(delete=AsyncMock()))
    monkeypatch.setattr(
        "src.bot.ocr_mixin.ocr_image",
        AsyncMock(return_value=SimpleNamespace(ok=False, error="stop", text="", cached=False)),
    )
    monkeypatch.setattr("src.bot.ocr_mixin.send_long_message", AsyncMock())
    context = SimpleNamespace(bot=SimpleNamespace(get_file=get_file))
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=999),
        effective_chat=SimpleNamespace(id=1, type="private"),
        message=SimpleNamespace(
            caption="",
            message_id=1,
            reply_text=reply_text,
            document=SimpleNamespace(
                file_id="document",
                file_unique_id="document-unique",
                file_name="document.png",
                file_size=10,
                mime_type="image/png",
            ),
        ),
    )
    handler = SimpleNamespace(_is_authorized=MagicMock(return_value=False))

    await OCRHandlerMixin.handle_document_ocr(handler, update, context)

    handler._is_authorized.assert_called_once_with(999)
    get_file.assert_not_awaited()
    download.assert_not_awaited()
