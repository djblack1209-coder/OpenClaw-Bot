"""Tests for ContextManager — tiered context window management.

Covers: _count_text_tokens, compress_local, TieredContextManager core/recall/archival,
        per-chat persistence, and status reporting.
"""
import json

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from src.context_manager import ContextManager, TieredContextManager, _atomic_json_write


# ============ Fixtures ============

@pytest.fixture
def cm(tmp_path):
    """ContextManager with tmp storage directory."""
    return ContextManager(storage_dir=str(tmp_path / "ctx_storage"))


@pytest.fixture
def tiered(cm, tmp_path):
    """TieredContextManager wrapping the cm fixture (no SharedMemory)."""
    return TieredContextManager(cm, shared_memory=None, total_budget=60000)


def _msg(role: str, content: str) -> dict:
    """Helper to build a message dict."""
    return {"role": role, "content": content}


def _bulk_msgs(n: int, text: str = "Hello world, this is test message number ") -> list:
    """Generate n alternating user/assistant messages."""
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append(_msg(role, f"{text}{i}"))
    return msgs


# ============ _count_text_tokens ============

class TestCountTextTokens:

    def test_english_text_returns_positive(self, cm):
        """_count_text_tokens returns a positive estimate for English text."""
        tokens = cm._count_text_tokens("Hello world, this is a test.")
        assert tokens > 0

    def test_cjk_text_gives_higher_count_than_pure_ascii(self, cm):
        """CJK characters should produce more tokens per character than ASCII."""
        ascii_tokens = cm._count_text_tokens("abcd")
        cjk_tokens = cm._count_text_tokens("你好世界")  # 4 CJK chars
        # CJK text of same char-count should tokenize to >= ASCII count
        assert cjk_tokens >= ascii_tokens

    def test_empty_string_returns_zero(self, cm):
        """Empty string should return 0 tokens."""
        assert cm._count_text_tokens("") == 0


# ============ estimate_tokens / should_compress ============

class TestEstimateTokens:

    def test_add_message_increases_token_count(self, cm):
        """Adding a message increases the estimated token count."""
        msgs = [_msg("user", "hi")]
        base = cm.estimate_tokens(msgs)
        msgs.append(_msg("assistant", "hello there, how can I help you today?"))
        assert cm.estimate_tokens(msgs) > base

    def test_should_compress_triggers_above_threshold(self, cm):
        """should_compress returns True when tokens exceed COMPRESS_THRESHOLD."""
        # tiktoken encodes 'x'*1000 more efficiently than naive estimate.
        # Use real English sentences to generate reliable token counts.
        big_text = "The quick brown fox jumps over the lazy dog. " * 200  # ~2000 tokens
        msgs = [_msg("user", big_text) for _ in range(40)]  # ~80K+ tokens
        assert cm.should_compress(msgs) is True

    def test_compress_not_needed_for_small_history(self, cm):
        """should_compress returns False for a small conversation."""
        msgs = _bulk_msgs(4)
        assert cm.should_compress(msgs) is False


# ============ compress_local ============

class TestCompressLocal:

    def test_compress_preserves_recent_messages(self, cm):
        """After compression, the most recent messages survive intact."""
        msgs = _bulk_msgs(4)
        big = "This is a very long message. " * 500
        old_msgs = [_msg("user", big) for _ in range(60)]
        all_msgs = old_msgs + msgs

        compressed, summary = cm.compress_local(all_msgs)
        # The last 4 messages (our short ones) should be present
        last_contents = [m["content"] for m in compressed[-4:]]
        for m in msgs:
            assert m["content"] in last_contents

    def test_compress_preserves_key_marker_messages(self, cm):
        """Messages containing KEY_MARKERS survive compression."""
        big = "filler text " * 500
        msgs = [_msg("user", big) for _ in range(50)]
        # Insert a key message in the middle
        key_msg = _msg("user", "请记住我的名字叫 Alice")
        msgs.insert(10, key_msg)
        msgs += _bulk_msgs(4)

        compressed, summary = cm.compress_local(msgs)
        all_text = " ".join(m.get("content", "") for m in compressed)
        assert "Alice" in all_text

    def test_compress_returns_summary(self, cm):
        """Compression generates a non-empty summary string."""
        big = "The quick brown fox jumps over the lazy dog. " * 200
        msgs = [_msg("user", big) for _ in range(40)]
        msgs += _bulk_msgs(4)

        compressed, summary = cm.compress_local(msgs)
        assert len(summary) > 0
        assert "摘要" in summary or "压缩" in summary


# ============ build_context (TieredContextManager) ============

class TestBuildContext:

    def test_build_context_returns_messages_and_metadata(self, tiered):
        """build_context returns a (messages, metadata) tuple."""
        msgs = _bulk_msgs(6)
        result, meta = tiered.build_context(msgs, system_prompt="You are helpful.")
        assert isinstance(result, list)
        assert isinstance(meta, dict)
        assert "total_tokens" in meta

    def test_build_context_includes_system_prompt(self, tiered):
        """System prompt text appears in the assembled context."""
        msgs = _bulk_msgs(4)
        result, meta = tiered.build_context(msgs, system_prompt="Be concise.")
        all_text = " ".join(m.get("content", "") for m in result)
        assert "Be concise" in all_text


# ============ TieredContextManager._save_core / _get_core ============

class TestTieredCorePersistence:

    def test_save_core_writes_json_atomically(self, tiered, tmp_path):
        """_save_core writes a JSON file to the core_memory directory."""
        chat_id = 12345
        tiered.core_set("user_profile", "Test User", chat_id=chat_id)
        tiered._save_core(chat_id)

        path = tiered._memory_dir / f"chat_{chat_id}.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["user_profile"] == "Test User"

    def test_get_core_returns_defaults_for_new_chat(self, tiered):
        """_get_core returns default fields for a chat_id with no persisted data."""
        core = tiered._get_core(chat_id=99999)
        assert "user_profile" in core
        assert "key_facts" in core
        assert core["user_profile"] == ""

    def test_core_append_adds_text(self, tiered):
        """core_append concatenates text to an existing core memory field."""
        chat_id = 100
        tiered.core_set("key_facts", "Fact A", chat_id=chat_id)
        tiered.core_append("key_facts", "Fact B", chat_id=chat_id)
        value = tiered.core_get("key_facts", chat_id=chat_id)
        assert "Fact A" in value
        assert "Fact B" in value

    def test_core_update_replaces_field(self, tiered):
        """core_set replaces the full value of a core memory field."""
        chat_id = 200
        tiered.core_set("current_task", "old task", chat_id=chat_id)
        tiered.core_set("current_task", "new task", chat_id=chat_id)
        assert tiered.core_get("current_task", chat_id=chat_id) == "new task"


# ============ get_status ============

class TestGetStatus:

    def test_get_status_returns_correct_structure(self, tiered):
        """get_status returns a dict with expected keys."""
        status = tiered.get_status(chat_id=0)
        assert "core_memory_keys" in status
        assert "core_memory_chars" in status
        assert "has_shared_memory" in status
        assert "total_budget" in status
        assert "persisted_chats" in status
        assert "budget_allocation" in status
        assert status["has_shared_memory"] is False
        assert status["total_budget"] == 60000
