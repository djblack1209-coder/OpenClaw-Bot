"""补号输入解析、脱敏和内存状态模型。"""

from __future__ import annotations

import base64
import binascii
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

import pyotp

MAX_INPUT_BYTES = 512 * 1024
MAX_ACCOUNTS = 100
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_TERMINAL_STATUSES = {"success", "duplicate", "skipped", "stopped", "dry_run"}


class InputFormatError(ValueError):
    """卖家原文格式不符合安全合同。"""


@dataclass(slots=True, repr=False)
class SellerCredential:
    """只存在于当前 Python 进程内存的卖家交付凭据。"""

    email: str
    password: str
    totp_secret: str

    def wipe(self) -> None:
        """尽早解除敏感字符串引用，避免后续响应或日志误用。"""
        self.email = ""
        self.password = ""
        self.totp_secret = ""


@dataclass(slots=True, repr=False)
class ReplenishJob:
    """单个账号的内存任务；公开状态永不包含原始凭据或 OAuth Token。"""

    credential: SellerCredential
    id: str = field(default_factory=lambda: secrets.token_urlsafe(12))
    email_label: str = field(init=False)
    status: str = "pending"
    message: str = "等待开始"
    group_options: list[dict[str, Any]] = field(default_factory=list)
    selected_group_id: int | None = None
    rate_options: list[float] = field(default_factory=list)
    selected_rate_multiplier: float | None = None
    account_id: int | None = None
    plan_type: str = ""
    token_info: dict[str, Any] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.email_label = mask_email(self.credential.email)

    def public(self) -> dict[str, Any]:
        """返回可以安全显示在本地页面的最小状态。"""
        result: dict[str, Any] = {
            "id": self.id,
            "email": self.email_label,
            "status": self.status,
            "message": self.message,
            "group_options": self.group_options,
            "selected_group_id": self.selected_group_id,
            "rate_options": self.rate_options,
        }
        if self.account_id is not None:
            result["account_id"] = self.account_id
        if self.selected_rate_multiplier is not None:
            result["rate_multiplier"] = self.selected_rate_multiplier
        if self.plan_type:
            result["plan_type"] = normalize_public_plan(self.plan_type)
        return result

    def wipe_secrets(self) -> None:
        """清除凭据与 OAuth Token 的内存引用。"""
        self.credential.wipe()
        if self.token_info is not None:
            self.token_info.clear()
        self.token_info = None

    def wipe_oauth_tokens(self) -> None:
        """失败或跳过时丢弃已换取的 OAuth Token，重试必须重新授权。"""
        if self.token_info is not None:
            self.token_info.clear()
        self.token_info = None

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES


def mask_email(email: str) -> str:
    """邮箱只保留首字符和域名，避免本地截图泄露完整账号。"""
    local, separator, domain = email.partition("@")
    if not separator or not local or not domain:
        return "***"
    return f"{local[0]}***@{domain}"


def normalize_public_plan(plan_type: str) -> str:
    """仅向页面暴露 Plus/Pro 分类，不回显上游原始元数据。"""
    normalized = plan_type.strip().lower()
    if "plus" in normalized:
        return "Plus"
    if "pro" in normalized:
        return "Pro"
    return "待人工确认"


def redact_text(value: object) -> str:
    """异常边界统一使用固定文案，不拼接第三方响应或敏感值。"""
    del value
    return "操作失败，详细凭据未写入日志；请按页面提示重试。"


def _normalize_totp_secret(value: str) -> str:
    normalized = re.sub(r"[\s-]+", "", value).upper()
    if not 16 <= len(normalized) <= 256:
        raise InputFormatError("TOTP 密钥长度不正确")
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    try:
        decoded = base64.b32decode(normalized + padding, casefold=True)
    except (binascii.Error, ValueError) as exc:
        raise InputFormatError("TOTP 密钥不是有效的 Base32") from exc
    if len(decoded) < 10:
        raise InputFormatError("TOTP 密钥强度不足")
    return normalized


def parse_seller_payload(raw: str) -> list[SellerCredential]:
    """解析固定的 email----password----totp_secret 批量格式。"""
    if not isinstance(raw, str) or not raw.strip():
        raise InputFormatError("请粘贴卖家发货原文")
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise InputFormatError("原文过大，单批最多 512 KiB")

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) > MAX_ACCOUNTS:
        raise InputFormatError("单批最多 100 个账号")

    records: list[SellerCredential] = []
    seen_emails: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        parts = line.split("----")
        if len(parts) != 3:
            raise InputFormatError(f"第 {line_number} 行必须恰好包含两个 ---- 分隔符")
        email, password, totp_secret = (part.strip() for part in parts)
        if not _EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
            raise InputFormatError(f"第 {line_number} 行邮箱格式不正确")
        if not password or len(password) > 1024:
            raise InputFormatError(f"第 {line_number} 行密码为空或过长")
        email_key = email.casefold()
        if email_key in seen_emails:
            raise InputFormatError(f"第 {line_number} 行邮箱在本批次重复")
        seen_emails.add(email_key)
        records.append(
            SellerCredential(
                email=email,
                password=password,
                totp_secret=_normalize_totp_secret(totp_secret),
            )
        )
    return records


def current_totp(secret: str) -> str:
    """在本机内存生成 RFC 6238 验证码，不调用外部 2FA 网站。"""
    try:
        return pyotp.TOTP(secret).now()
    except Exception as exc:
        raise InputFormatError("无法生成本地 TOTP 验证码") from exc
