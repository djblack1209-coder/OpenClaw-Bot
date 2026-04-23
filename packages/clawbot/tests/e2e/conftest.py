"""
e2e 测试共享 fixtures — Telegram Update/Context 工厂 + 环境 Mock

提供 FakeUpdate / FakeContext 模拟 python-telegram-bot 的 Update 和
CallbackContext，让 e2e 测试无需启动真正的 Telegram Bot 就能驱动
handler 全链路。
"""

import os
import sys
import pytest
from typing import Optional
from unittest.mock import MagicMock, AsyncMock, patch

# 让 src/ 可以直接 import（e2e/ 比 tests/ 多嵌套一层）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


# ============================================================================
# FakeUpdate — 模拟 telegram.Update
# ============================================================================


class _Obj:
    """万能属性容器，按 kwargs 赋值后可以 dot-access。"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeUpdate:
    """
    模拟 python-telegram-bot 的 Update 对象。

    支持的属性路径（与真实代码一致）：
      update.effective_chat.id / .type
      update.effective_user.id / .first_name
      update.message.text / .reply_text() / .reply_html()
      update.message.chat.send_action()
      update.message.edit_text()
      update.callback_query  (普通消息为 None)
    """

    def __init__(
        self,
        text: str = "/start",
        chat_id: int = 12345,
        chat_type: str = "private",
        user_id: int = 67890,
        user_first_name: str = "测试用户",
        callback_query=None,
        message_id: int = 1,
    ):
        # ── effective_chat ──
        self.effective_chat = _Obj(id=chat_id, type=chat_type)

        # ── effective_user ──
        self.effective_user = _Obj(id=user_id, first_name=user_first_name)

        # ── message ──
        self._reply_calls: list[dict] = []  # 记录所有 reply 调用

        # reply_text / reply_html / edit_text 都是 async，
        # 返回一个带 message_id 的假 Message 对象
        self.message = _Obj(
            text=text,
            message_id=message_id,
            chat=_Obj(send_action=AsyncMock()),
            reply_text=self._make_reply_recorder("reply_text"),
            reply_html=self._make_reply_recorder("reply_html"),
            edit_text=self._make_reply_recorder("edit_text"),
        )

        # ── callback_query ──
        self.callback_query = callback_query

    # ── 内部工具 ──

    def _make_reply_recorder(self, method_name: str):
        """创建一个 AsyncMock，同时把调用参数记到 _reply_calls。"""

        async def _recorder(*args, **kwargs):
            # 第一个 positional 参数或 'text' kwarg 视为消息文本
            text_content = args[0] if args else kwargs.get("text", "")
            self._reply_calls.append(
                {
                    "method": method_name,
                    "text": text_content,
                    "kwargs": kwargs,
                }
            )
            # 返回一个假的 Message（某些代码会读 .message_id）
            return _Obj(message_id=self.message.message_id + len(self._reply_calls))

        mock = AsyncMock(side_effect=_recorder)
        return mock

    # ── 便捷查询方法 ──

    def get_reply_text(self) -> str:
        """提取最后一次 reply 调用的文本内容。"""
        if not self._reply_calls:
            return ""
        return self._reply_calls[-1]["text"]

    def get_all_reply_texts(self) -> list[str]:
        """返回所有 reply 调用的文本列表。"""
        return [c["text"] for c in self._reply_calls]

    def get_reply_markup(self):
        """提取最后一次 reply 调用中的 reply_markup 键盘。"""
        if not self._reply_calls:
            return None
        return self._reply_calls[-1]["kwargs"].get("reply_markup")


# ============================================================================
# FakeContext — 模拟 telegram.ext.CallbackContext
# ============================================================================


class FakeContext:
    """
    模拟 python-telegram-bot 的 CallbackContext。

    支持的属性：
      context.args             命令参数列表
      context.bot.username     Bot 用户名
      context.bot.send_message(...)   async
      context.bot.edit_message_text(...)  async
      context.bot.edit_message_reply_markup(...)  async
      context.bot.send_chat_action(...)  async
      context.bot.get_file(...)  async
      context.bot.get_me()     async
      context.bot.send_document(...)  async
      context.bot.send_photo(...)  async
      context.user_data        用户级别数据字典
      context.chat_data        聊天级别数据字典
    """

    def __init__(
        self,
        args: Optional[list] = None,
        bot_username: str = "test_bot",
    ):
        self.args = args or []
        self.user_data: dict = {}
        self.chat_data: dict = {}

        # 构造 bot 对象，所有方法都是 AsyncMock
        bot = MagicMock()
        bot.username = bot_username
        bot.send_message = AsyncMock(
            return_value=_Obj(message_id=999)
        )
        bot.edit_message_text = AsyncMock(
            return_value=_Obj(message_id=999)
        )
        bot.edit_message_reply_markup = AsyncMock()
        bot.send_chat_action = AsyncMock()
        bot.get_file = AsyncMock(
            return_value=_Obj(
                file_path="fake/path.ogg",
                download_to_drive=AsyncMock(),
            )
        )
        bot.get_me = AsyncMock(
            return_value=_Obj(username=bot_username)
        )
        bot.send_document = AsyncMock()
        bot.send_photo = AsyncMock()
        self.bot = bot


# ============================================================================
# Pytest Fixtures
# ============================================================================


@pytest.fixture
def make_update():
    """
    工厂 fixture：创建 FakeUpdate，可自定义所有字段。

    用法:
        update = make_update(text="/help", user_id=67890)
    """

    def _factory(
        text: str = "/start",
        chat_id: int = 12345,
        chat_type: str = "private",
        user_id: int = 67890,
        user_first_name: str = "测试用户",
        callback_query=None,
        message_id: int = 1,
    ) -> FakeUpdate:
        return FakeUpdate(
            text=text,
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            user_first_name=user_first_name,
            callback_query=callback_query,
            message_id=message_id,
        )

    return _factory


@pytest.fixture
def make_context():
    """
    工厂 fixture：创建 FakeContext，可自定义参数和 bot 用户名。

    用法:
        ctx = make_context(args=["AAPL"])
    """

    def _factory(
        args: Optional[list] = None,
        bot_username: str = "test_bot",
    ) -> FakeContext:
        return FakeContext(args=args, bot_username=bot_username)

    return _factory


@pytest.fixture
def allowed_user_id() -> int:
    """返回测试用的授权用户 ID。"""
    return 67890


@pytest.fixture
def mock_env(monkeypatch):
    """
    注入假的环境变量，覆盖所有需要 API Token 的配置项。

    包含:
      - ALLOWED_USER_IDS=67890   (与 allowed_user_id 一致)
      - 各种 API token 使用 fake- 前缀
    """
    env_vars = {
        "ALLOWED_USER_IDS": "67890",
        "TELEGRAM_BOT_TOKEN": "fake-telegram-token",
        "OPENAI_API_KEY": "fake-openai-key",
        "ANTHROPIC_API_KEY": "fake-anthropic-key",
        "GEMINI_API_KEY": "fake-gemini-key",
        "DEEPSEEK_API_KEY": "fake-deepseek-key",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


@pytest.fixture
def mock_llm():
    """
    Mock 掉 LLM 调用，防止测试发真实请求。

    Patch 路径: src.litellm_router.free_pool.acompletion
    返回格式与 LiteLLM 一致的假响应。
    """
    # 构造与 LiteLLM ModelResponse 结构一致的假响应
    fake_choice = _Obj(
        message=_Obj(content="这是一个假的 LLM 回复。", role="assistant"),
        finish_reason="stop",
    )
    fake_response = _Obj(
        choices=[fake_choice],
        usage=_Obj(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        model="fake-model",
    )

    with patch("src.litellm_router.free_pool.acompletion", new_callable=AsyncMock) as mock:
        mock.return_value = fake_response
        yield mock


@pytest.fixture
def mock_yfinance():
    """
    Mock 掉 yfinance.Ticker，防止测试中发起真实网络请求。

    返回一个带基本属性的 MagicMock。
    """
    with patch("yfinance.Ticker") as mock_ticker_cls:
        # 构造一个假的 Ticker 实例
        ticker_instance = MagicMock()
        ticker_instance.info = {
            "shortName": "Test Corp",
            "regularMarketPrice": 150.0,
            "currency": "USD",
            "marketCap": 1_000_000_000,
        }
        ticker_instance.history.return_value = MagicMock()  # DataFrame mock
        mock_ticker_cls.return_value = ticker_instance
        yield mock_ticker_cls
