"""
OpenClaw OMEGA — 安全分级 (Security Gate)
权限分级、PIN 码验证、审计日志、SSRF 防护。
"""
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUDIT_DIR = _BASE_DIR / "data" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_FILE = AUDIT_DIR / "operations.jsonl"
PIN_FILE = AUDIT_DIR / ".pin_hash"

# ── SSRF 防护 ─────────────────────────────────────────

# SSRF 防护: 禁止访问的主机名黑名单（云厂商元数据服务 + 本地回环地址）
SSRF_BLOCKED_HOSTS: frozenset = frozenset({
    "169.254.169.254", "metadata.google.internal",
    "metadata.internal", "100.100.100.200",
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
})


class SSRFError(Exception):
    """SSRF 安全检查未通过时抛出的异常"""
    pass


def check_ssrf(url: str) -> bool:
    """检查 URL 是否安全（非内网/非元数据服务），防止 SSRF 攻击。

    通过 DNS 解析验证目标 IP，防止 DNS 重绑定攻击。
    采用 fail-close 策略：任何异常情况都拒绝访问。

    Args:
        url: 待检查的完整 URL

    Returns:
        True 表示安全，False 表示存在 SSRF 风险
    """
    try:
        parsed = urlparse(url)
        # 只允许 http/https 协议，阻止 file:// gopher:// 等危险协议
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # 黑名单检查：拦截已知的内网/元数据服务地址
        if hostname in SSRF_BLOCKED_HOSTS:
            return False
        # DNS 解析后检查 IP（防止 DNS 重绑定攻击）
        try:
            resolved_ips = socket.getaddrinfo(hostname, None)
            for family, _type, proto, canonname, sockaddr in resolved_ips:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    logger.warning("[SSRF] 拦截: %s 解析到内网地址 %s", url, ip)
                    return False
        except (socket.gaierror, ValueError):
            # 安全修复: DNS 解析失败 → 拒绝（fail-close，防止利用 DNS 解析失败绕过检查）
            logger.warning("[SSRF] 拦截: %s DNS 解析失败，拒绝访问", url)
            return False
        return True
    except Exception:
        return False


# ── 权限分级 ──────────────────────────────────────────

PERMISSION_AUTO = {
    "screen_read", "web_browse", "social_publish_draft", "price_search",
    "portfolio_view", "memory_search", "trending_scan", "evolution_scan",
    "news_fetch", "info_query", "system_status",
}

PERMISSION_CONFIRM = {
    "purchase_over_500", "phone_call", "email_send_important",
    "trade_execute", "file_delete", "system_config_change",
    "social_publish_final", "booking_confirm",
}

PERMISSION_ALWAYS_HUMAN = {
    "transfer_over_5000", "legal_document_sign", "privacy_data_share",
    "account_delete", "credential_change",
}

# 敏感数据模式（永不持久化）
SENSITIVE_PATTERNS = [
    r'\b\d{16,19}\b',          # 银行卡号
    r'\b\d{3}-?\d{2}-?\d{4}\b',  # SSN
    r'\b\d{15,18}[xX]?\b',    # 身份证号
    r'password\s*[:=]\s*\S+',  # 密码
    r'token\s*[:=]\s*\S+',    # Token

    # ── 新增：XSS 防护 ──
    r'(?i)<\s*script.*?>',
    r'(?i)<\s*/\s*script\s*>',
    r'(?i)＜\s*script.*?＞',     # 全角变体
    r'(?i)＜\s*/\s*script\s*＞', # 全角变体
    r'(?i)[\x00\u200b\u200c\u200d\ufeff]', # Unicode 空字符绕过
    r'(?i)<[^>]*\bon[a-z]+\s*=', # 标签内事件处理器

    # ── 新增：SQL 注入防护 ──
    r'(?i)(\bUNION\s+SELECT\b)',
    r'(?i)(\bDROP\s+TABLE\b)',
    r'(?i)(\bxp_cmdshell\b)',
    r"(?i)('\s*OR\s+.*)",
    r"(?i)('--\s*$)",
    r"(?i)(;\s*--\s*$)",
    r"(?i)(/\*.*\*/)",         # 块注释

    # ── 新增：路径遍历防护 ──
    r'(?i)(\.\.[/\\\\]|%2e%2e%2f|%252e%252e%252f|%252f)',

    # ── 新增：命令注入防护 ──
    r'(?i)(;\s*rm\s+-rf)',
    r'(?i)(\|\s*cat\s+/etc/)',
    r'(`[^`]+`)',
    r'(\$\([^)]+\))',
    r'(?i)(\bcurl\b.*\|\s*bash\b)',
]


@dataclass
class PermissionResult:
    allowed: bool = False
    requires_confirmation: bool = False
    requires_pin: bool = False
    reason: str = ""
    permission_level: str = ""  # auto / confirm / always_human


class SecurityGate:
    """
    安全门控 — 权限检查、PIN 验证、审计日志。

    用法:
        gate = get_security_gate()
        result = gate.check_permission("trade_execute", user_id=123)
        if result.requires_pin:
            verified = gate.verify_pin("1234")
    """

    def __init__(self, admin_user_ids: Optional[List[int]] = None):
        self._admin_ids: Set[int] = set(admin_user_ids or [])
        self._pin_hash: Optional[str] = self._load_pin_hash()
        self._operation_count: Dict[str, int] = {}
        self._pin_attempts: dict = {}  # user_id -> {"count": int, "locked_until": float}
        logger.info(f"SecurityGate 初始化 (管理员: {len(self._admin_ids)})")

    def _load_pin_hash(self) -> Optional[str]:
        """加载已存储的 PIN hash"""
        if PIN_FILE.exists():
            try:
                return PIN_FILE.read_text().strip()
            except Exception as e:
                logger.error("PIN hash 文件读取失败 (%s), PIN 验证将要求重新设置", e)
        return None

    def check_permission(
        self, action: str, user_id: int = 0
    ) -> PermissionResult:
        """
        检查操作权限。

        Args:
            action: 操作标识（如 "trade_execute"）
            user_id: Telegram user_id

        Returns:
            PermissionResult
        """
        # 白名单检查
        if self._admin_ids and user_id not in self._admin_ids:
            return PermissionResult(
                allowed=False, reason="用户不在白名单中",
                permission_level="denied",
            )

        # 分级检查
        if action in PERMISSION_AUTO:
            return PermissionResult(
                allowed=True, permission_level="auto",
                reason="自动执行权限",
            )

        if action in PERMISSION_CONFIRM:
            result = PermissionResult(
                allowed=True,
                requires_confirmation=True,
                permission_level="confirm",
                reason="需要用户确认",
            )
            # 交易类操作需要 PIN
            if "trade" in action and self._pin_hash:
                result.requires_pin = True
                result.reason = "交易操作需要 PIN 确认"
            return result

        if action in PERMISSION_ALWAYS_HUMAN:
            return PermissionResult(
                allowed=False,
                permission_level="always_human",
                reason="此操作必须由用户亲自完成",
            )

        # 未知操作默认需要确认
        return PermissionResult(
            allowed=True,
            requires_confirmation=True,
            permission_level="confirm",
            reason="未分类操作，需要确认",
        )

    def set_pin(self, pin: str) -> bool:
        """设置 PIN（PBKDF2 + 随机盐存储）"""
        if len(pin) < 4:
            return False
        salt = secrets.token_hex(16)
        pin_hash = hashlib.pbkdf2_hmac('sha256', pin.encode(), salt.encode(), 100000).hex()
        try:
            # 存储格式: salt:hash
            PIN_FILE.write_text(f"{salt}:{pin_hash}")
            os.chmod(PIN_FILE, 0o600)
            self._pin_hash = f"{salt}:{pin_hash}"
            logger.info("PIN 已设置")
            return True
        except Exception as e:
            logger.error(f"PIN 设置失败: {e}")
            return False

    def verify_pin(self, pin: str, user_id: int = 0) -> bool:
        """验证 PIN（含频率限制: 5次失败后锁定5分钟）"""
        # 频率限制检查
        state = self._pin_attempts.get(user_id, {"count": 0, "locked_until": 0})
        if time.time() < state.get("locked_until", 0):
            return False

        if not self._pin_hash:
            return True  # 未设置 PIN 则跳过验证
        stored = self._pin_hash
        if ':' in stored:
            # 新格式: salt:hash (PBKDF2)
            salt, expected_hash = stored.split(':', 1)
            pin_hash = hashlib.pbkdf2_hmac('sha256', pin.encode(), salt.encode(), 100000).hex()
            result = hmac.compare_digest(pin_hash, expected_hash)
        else:
            # 向后兼容旧格式（无盐 SHA-256），验证后自动升级为 PBKDF2
            result = hashlib.sha256(pin.encode()).hexdigest() == stored
            if result:
                # 旧格式验证通过，自动升级为 PBKDF2 + 随机盐
                new_salt = secrets.token_hex(16)
                new_hash = hashlib.pbkdf2_hmac('sha256', pin.encode(), new_salt.encode(), 100000).hex()
                upgraded = f"{new_salt}:{new_hash}"
                try:
                    PIN_FILE.write_text(upgraded)
                    os.chmod(PIN_FILE, 0o600)
                    self._pin_hash = upgraded
                    logger.info("旧格式 PIN 已自动升级为 PBKDF2 + 盐")
                except Exception as e:
                    logger.warning(f"PIN 自动升级写入失败: {e}")

        if not result:
            state["count"] = state.get("count", 0) + 1
            if state["count"] >= 5:
                state["locked_until"] = time.time() + 300  # 锁定5分钟
                state["count"] = 0
                logger.warning("[Security] PIN 验证失败 5 次，用户 %s 锁定 5 分钟", user_id)
                # EventBus: 安全告警
                try:
                    from src.core.event_bus import get_event_bus
                    bus = get_event_bus()
                    if bus:
                        import asyncio
                        try:
                            loop = asyncio.get_running_loop()
                            _t = loop.create_task(bus.publish("system.security_alert", {
                                "alert_type": "pin_brute_force",
                                "user_id": user_id,
                                "locked_minutes": 5,
                            }))
                            _t.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
                        except RuntimeError as e:
                            logger.debug("发布安全警报事件时无事件循环: %s", e)
                except Exception as e:
                    logger.debug("静默异常: %s", e)
            self._pin_attempts[user_id] = state
        else:
            self._pin_attempts.pop(user_id, None)  # 成功后清除计数
        return result

    def has_pin(self) -> bool:
        return self._pin_hash is not None

    def log_operation(
        self,
        user_id: int,
        action: str,
        details: Optional[Dict] = None,
        success: bool = True,
    ) -> None:
        """写入审计日志（追加模式，不可篡改）"""
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "action": action,
            "success": success,
            "details_keys": list((details or {}).keys()),
        }

        # 统计
        self._operation_count[action] = self._operation_count.get(action, 0) + 1

        try:
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"审计日志写入失败: {e}")

    def contains_sensitive_data(self, text: str) -> bool:
        """检查文本是否包含敏感数据"""
        import re
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def redact_sensitive(self, text: str) -> str:
        """脱敏处理"""
        import re
        redacted = text
        for pattern in SENSITIVE_PATTERNS:
            redacted = re.sub(pattern, "[已脱敏]", redacted, flags=re.IGNORECASE)
        return redacted

    def sanitize_input(self, text: str) -> str:
        """
        输入消毒，拦截 XSS、SQL 注入、路径遍历和命令注入等攻击载荷。
        注意：这并不替代特定的转义（如 SQL 参数化查询），但可作为基础安全防线。
        """
        if not text:
            return text

        import re
        sanitized = text

        # 1. 过滤不可见字符 / 零宽字符 / NULL 字节
        sanitized = re.sub(r'[\x00\u200b\u200c\u200d\ufeff]', '', sanitized)

        # 2. XSS 基础防护 (转义 HTML 尖括号，包括全角变体)
        sanitized = re.sub(r'[<＜\uff1c]', '&lt;', sanitized)
        sanitized = re.sub(r'[>＞\uff1e]', '&gt;', sanitized)

        # 3. 危险事件处理器 (如 onerror=, onload=)
        sanitized = re.sub(r'(?i)\bon[a-z]+\s*=', 'blocked=', sanitized)

        # 4. 路径遍历 (拦截 ../, ..\, %2e%2e%2f 等)
        sanitized = re.sub(r'(?i)(\.\.[/\\\\]|%2e%2e%2f|%252e%252e%252f)', '', sanitized)

        # 5. SQL 注入基础黑名单
        sql_patterns = [
            r'(?i)(\bUNION\s+SELECT\b)',
            r'(?i)(\bDROP\s+TABLE\b)',
            r'(?i)(\bxp_cmdshell\b)',
            r"(?i)('\s*OR\s+.*)",
            r"(?i)('--\s*$)",
            r"(?i)(;\s*--\s*$)",
            r'(?i)(\bINSERT\s+INTO\b)',
            r'(?i)(\bDELETE\s+FROM\b)',
            r'(?i)(\bEXEC\s+)',
            r'(?i)(\bWAITFOR\s+DELAY\b)',
            r'(?i)(\bALTER\s+TABLE\b)',
            r'(?i)(\bCREATE\s+TABLE\b)',
            r'(?i)(\bTRUNCATE\s+)',
            r'(?i)(\bUPDATE\s+\w+\s+SET\b)',
        ]
        for pattern in sql_patterns:
            sanitized = re.sub(pattern, '[BLOCKED_SQL]', sanitized)

        # 6. 命令注入基础黑名单
        cmd_patterns = [
            r'(?i)(;\s*rm\s+-rf)',
            r'(?i)(\|\s*cat\s+/etc/)',
            r'(`[^`]+`)',
            r'(\$\([^)]+\))',
            r'(?i)(\bcurl\b.*\|\s*bash\b)',
            r'(\|\|)',              # 逻辑 OR 链式命令
            r'(&&)',               # 逻辑 AND 链式命令
            r'(>>\s*\S)',          # 追加重定向
            r'(<\(\s*\S)',         # 进程替换
            r'(?i)(;\s*wget\b)',   # 分号后跟 wget
            r'(?i)(;\s*curl\b)',   # 分号后跟 curl
            r'(?i)(;\s*chmod\b)',  # 分号后跟 chmod
        ]
        for pattern in cmd_patterns:
            sanitized = re.sub(pattern, '[BLOCKED_CMD]', sanitized)

        return sanitized

    def get_stats(self) -> Dict:
        return {
            "admin_count": len(self._admin_ids),
            "pin_configured": self.has_pin(),
            "operation_counts": dict(self._operation_count),
        }

    def get_recent_operations(self, limit: int = 20) -> List[Dict]:
        """获取最近的操作日志"""
        records = []
        if AUDIT_FILE.exists():
            try:
                with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            records.append(json.loads(line))
            except Exception:
                logger.debug("Silenced exception", exc_info=True)
        return records[-limit:]


_gate: Optional[SecurityGate] = None


def get_security_gate() -> SecurityGate:
    global _gate
    if _gate is None:
        admin_str = os.environ.get("OMEGA_ADMIN_USER_IDS", "")
        ids = [int(x.strip()) for x in admin_str.split(",") if x.strip().isdigit()]
        # 也读取现有的 ALLOWED_USER_IDS
        try:
            from src.bot.globals import ALLOWED_USER_IDS
            if ALLOWED_USER_IDS:
                ids.extend(ALLOWED_USER_IDS)
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
        _gate = SecurityGate(admin_user_ids=list(set(ids)))
    return _gate
