"""补号输入解析、脱敏和内存状态模型。"""

from __future__ import annotations

import base64
import binascii
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

import pyotp

MAX_INPUT_BYTES = 512 * 1024
MAX_ACCOUNTS = 100
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_LABEL_PATTERN = re.compile(
    r"^(邮箱|email|e-mail|密码|password|pass|2fa(?:\s*密钥)?|totp(?:_secret|\s*密钥)?|密钥|secret)\s*[:：=]\s*(.+)$",
    re.IGNORECASE,
)
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


def _credential_from_values(
    email: object,
    password: object,
    totp_secret: object,
    *,
    location: str,
) -> SellerCredential:
    """统一校验三种输入格式，错误只描述位置而不回显原值。"""
    if not isinstance(email, str) or not _EMAIL_PATTERN.fullmatch(email.strip()) or len(email.strip()) > 254:
        raise InputFormatError(f"{location}邮箱格式不正确")
    if not isinstance(password, str) or not password or len(password) > 1024:
        raise InputFormatError(f"{location}密码为空或过长")
    if not isinstance(totp_secret, str):
        raise InputFormatError(f"{location}缺少有效的 2FA/TOTP 密钥")
    return SellerCredential(
        email=email.strip(),
        password=password,
        totp_secret=_normalize_totp_secret(totp_secret),
    )


def _parse_delimited_payload(raw: str) -> list[SellerCredential]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    records: list[SellerCredential] = []
    for line_number, line in enumerate(lines, start=1):
        parts = line.split("----")
        if len(parts) != 3:
            raise InputFormatError(f"第 {line_number} 行必须恰好包含两个 ---- 分隔符")
        records.append(
            _credential_from_values(
                *(part.strip() for part in parts),
                location=f"第 {line_number} 行",
            )
        )
    return records


def _parse_json_payload(raw: str) -> list[SellerCredential]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InputFormatError("JSON 发货内容格式不正确") from exc
    items = payload if isinstance(payload, list) else [payload]
    if not items or not all(isinstance(item, dict) for item in items):
        raise InputFormatError("JSON 必须是账号对象或账号对象数组")

    records: list[SellerCredential] = []
    for index, item in enumerate(items, start=1):
        normalized = {str(key).strip().casefold(): value for key, value in item.items()}
        secret_values = [
            normalized[key]
            for key in ("totp_secret", "totp", "secret")
            if key in normalized and normalized[key] not in (None, "")
        ]
        if len({str(value) for value in secret_values}) > 1:
            raise InputFormatError(f"第 {index} 个 JSON 账号包含冲突的 2FA/TOTP 密钥字段")
        records.append(
            _credential_from_values(
                normalized.get("email"),
                normalized.get("password"),
                secret_values[0] if secret_values else None,
                location=f"第 {index} 个 JSON 账号",
            )
        )
    return records


def _parse_labeled_payload(raw: str) -> list[SellerCredential]:
    field_names = {
        "邮箱": "email",
        "email": "email",
        "e-mail": "email",
        "密码": "password",
        "password": "password",
        "pass": "password",
        "2fa": "totp_secret",
        "2fa密钥": "totp_secret",
        "totp": "totp_secret",
        "totp_secret": "totp_secret",
        "totp密钥": "totp_secret",
        "密钥": "totp_secret",
        "secret": "totp_secret",
    }
    records: list[SellerCredential] = []
    current: dict[str, str] = {}
    account_index = 1
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        match = _LABEL_PATTERN.fullmatch(line)
        if match is None:
            raise InputFormatError(f"第 {line_number} 行不是可识别的邮箱、密码或 2FA/TOTP 标签")
        label = re.sub(r"\s+", "", match.group(1).casefold())
        field_name = field_names[label]
        if field_name in current:
            if set(current) != {"email", "password", "totp_secret"}:
                raise InputFormatError(f"第 {line_number} 行在当前账号完成前重复了字段")
            records.append(
                _credential_from_values(
                    current["email"],
                    current["password"],
                    current["totp_secret"],
                    location=f"第 {account_index} 个标签账号",
                )
            )
            account_index += 1
            current = {}
        current[field_name] = match.group(2).strip()
    if current:
        if set(current) != {"email", "password", "totp_secret"}:
            raise InputFormatError(f"第 {account_index} 个标签账号字段不完整")
        records.append(
            _credential_from_values(
                current["email"],
                current["password"],
                current["totp_secret"],
                location=f"第 {account_index} 个标签账号",
            )
        )
    return records


def parse_seller_payload(raw: str) -> list[SellerCredential]:
    """严格解析分隔行、带标签多行块或 JSON 账号对象/数组。"""
    if not isinstance(raw, str) or not raw.strip():
        raise InputFormatError("请粘贴卖家发货原文")
    if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
        raise InputFormatError("原文过大，单批最多 512 KiB")

    stripped = raw.strip()
    if stripped.startswith(("{", "[")):
        records = _parse_json_payload(stripped)
    elif "----" in stripped:
        records = _parse_delimited_payload(stripped)
    else:
        records = _parse_labeled_payload(stripped)
    if not records:
        raise InputFormatError("没有找到完整账号")
    if len(records) > MAX_ACCOUNTS:
        raise InputFormatError("单批最多 100 个账号")

    seen_emails: set[str] = set()
    for index, record in enumerate(records, start=1):
        email_key = record.email.casefold()
        if email_key in seen_emails:
            raise InputFormatError(f"第 {index} 个账号邮箱在本批次重复")
        seen_emails.add(email_key)
    return records


def current_totp(secret: str) -> str:
    """在本机内存生成 RFC 6238 验证码，不调用外部 2FA 网站。"""
    try:
        return pyotp.TOTP(secret).now()
    except Exception as exc:
        raise InputFormatError("无法生成本地 TOTP 验证码") from exc
