#!/usr/bin/env python3
"""只读检查资源续费台账，并生成不含凭据的到期提醒摘要。

脚本不会登录供应商、不会付款、不会修改自动续费状态。实际台账默认放在
``packages/clawbot/config/renewals.json``，该文件被 Git 忽略；仓库只跟踪无凭据模板。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit


DEFAULT_LEDGER = Path("packages/clawbot/config/renewals.json")
DEFAULT_REMINDER_DAYS = (30, 14, 7, 3, 1)
UNKNOWN = "unknown"
LEDGER_VERSION = 1
_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:api[_-]?key|token|secret|password|passwd|cookie|session|credential|private[_-]?key|验证码)"
)
_AUTO_RENEW_VALUES = {"enabled", "disabled", UNKNOWN}
_COST_PERIODS = {"monthly", "annual", "one_time", UNKNOWN}


class LedgerError(ValueError):
    """表示台账结构不安全或无法解析。"""


@dataclass(frozen=True)
class RenewalItem:
    """保存一个已验证、不会包含凭据的资源条目。"""

    resource_id: str
    name: str
    purpose: str
    provider: str
    expires_on: date | None
    auto_renew: str
    estimated_amount: float | None
    currency: str
    cost_period: str
    action_url: str | None
    notes: str


_STATUS_PRIORITY = {
    "expired": 0,
    "expires_today": 1,
    "due_soon": 2,
    "unknown": 3,
    "ok": 4,
}


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(f"{field} 必须是非空字符串")
    return value.strip()


def _reject_sensitive_keys(value: Any, path: str = "root") -> None:
    """拒绝把凭据字段混进续费台账；只看字段名，不读取其他本地文件。"""
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if _SENSITIVE_KEY_RE.search(key_text):
                raise LedgerError(f"{path}.{key_text} 是禁止写入续费台账的敏感字段")
            _reject_sensitive_keys(child, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{path}[{index}]")


def _parse_expiry(value: Any, field: str) -> date | None:
    text = _require_nonempty_string(value, field)
    if text == UNKNOWN:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise LedgerError(f"{field} 必须是 YYYY-MM-DD 或 unknown") from exc


def _parse_action_url(value: Any, field: str) -> str | None:
    text = _require_nonempty_string(value, field)
    if text == UNKNOWN:
        return None
    parsed = urlsplit(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise LedgerError(f"{field} 必须是无凭据的 https 地址或 unknown")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LedgerError(f"{field} 不得包含账号、密码、查询参数或片段")
    return text


def _parse_cost(value: Any, field: str) -> tuple[float | None, str, str]:
    if not isinstance(value, dict):
        raise LedgerError(f"{field} 必须是对象")
    amount_value = value.get("amount", UNKNOWN)
    if amount_value == UNKNOWN:
        amount = None
    elif isinstance(amount_value, bool) or not isinstance(amount_value, (int, float)) or amount_value < 0:
        raise LedgerError(f"{field}.amount 必须是非负数字或 unknown")
    else:
        amount = float(amount_value)
    currency = _require_nonempty_string(value.get("currency", UNKNOWN), f"{field}.currency")
    if currency != UNKNOWN and not _CURRENCY_RE.fullmatch(currency):
        raise LedgerError(f"{field}.currency 必须是三位大写货币代码或 unknown")
    period = _require_nonempty_string(value.get("period", UNKNOWN), f"{field}.period")
    if period not in _COST_PERIODS:
        raise LedgerError(f"{field}.period 必须是 monthly、annual、one_time 或 unknown")
    return amount, currency, period


def validate_ledger(payload: Any) -> tuple[tuple[int, ...], list[RenewalItem]]:
    """校验台账结构和安全边界，返回提醒规则与规范化条目。"""
    if not isinstance(payload, dict):
        raise LedgerError("台账根节点必须是对象")
    _reject_sensitive_keys(payload)
    if payload.get("version") != LEDGER_VERSION:
        raise LedgerError(f"version 必须是 {LEDGER_VERSION}")

    reminder_value = payload.get("reminder_days")
    if not isinstance(reminder_value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in reminder_value
    ):
        raise LedgerError("reminder_days 必须是正整数数组")
    reminder_days = tuple(reminder_value)
    if reminder_days != DEFAULT_REMINDER_DAYS:
        expected = "/".join(str(item) for item in DEFAULT_REMINDER_DAYS)
        raise LedgerError(f"reminder_days 必须固定为 {expected} 天")

    resources = payload.get("resources")
    if not isinstance(resources, list) or not resources:
        raise LedgerError("resources 必须是非空数组")

    items: list[RenewalItem] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(resources):
        field = f"resources[{index}]"
        if not isinstance(raw, dict):
            raise LedgerError(f"{field} 必须是对象")
        resource_id = _require_nonempty_string(raw.get("id"), f"{field}.id")
        if not _ID_RE.fullmatch(resource_id):
            raise LedgerError(f"{field}.id 必须使用小写 kebab-case")
        if resource_id in seen_ids:
            raise LedgerError(f"资源 id 重复：{resource_id}")
        seen_ids.add(resource_id)
        auto_renew = _require_nonempty_string(raw.get("auto_renew", UNKNOWN), f"{field}.auto_renew")
        if auto_renew not in _AUTO_RENEW_VALUES:
            raise LedgerError(f"{field}.auto_renew 必须是 enabled、disabled 或 unknown")
        amount, currency, period = _parse_cost(raw.get("estimated_cost", {}), f"{field}.estimated_cost")
        items.append(
            RenewalItem(
                resource_id=resource_id,
                name=_require_nonempty_string(raw.get("name"), f"{field}.name"),
                purpose=_require_nonempty_string(raw.get("purpose"), f"{field}.purpose"),
                provider=_require_nonempty_string(raw.get("provider", UNKNOWN), f"{field}.provider"),
                expires_on=_parse_expiry(raw.get("expires_on", UNKNOWN), f"{field}.expires_on"),
                auto_renew=auto_renew,
                estimated_amount=amount,
                currency=currency,
                cost_period=period,
                action_url=_parse_action_url(raw.get("action_url", UNKNOWN), f"{field}.action_url"),
                notes=str(raw.get("notes", "")).strip(),
            )
        )
    return reminder_days, items


def _reminder_threshold(days_remaining: int, reminder_days: Iterable[int]) -> int | None:
    candidates = [threshold for threshold in reminder_days if days_remaining <= threshold]
    return min(candidates) if candidates else None


def evaluate_ledger(payload: Any, *, today: date | None = None) -> dict[str, Any]:
    """计算到期状态；输出不含费用链接、备注或其他可能的私人运营细节。"""
    reminder_days, items = validate_ledger(payload)
    current_day = today or date.today()
    rows: list[dict[str, Any]] = []
    for item in items:
        if item.expires_on is None:
            row = {
                "id": item.resource_id,
                "name": item.name,
                "status": "unknown",
                "days_remaining": None,
                "reminder_threshold": None,
            }
        else:
            days_remaining = (item.expires_on - current_day).days
            if days_remaining < 0:
                status = "expired"
                threshold = 0
            elif days_remaining == 0:
                status = "expires_today"
                threshold = 0
            else:
                threshold = _reminder_threshold(days_remaining, reminder_days)
                status = "due_soon" if threshold is not None else "ok"
            row = {
                "id": item.resource_id,
                "name": item.name,
                "status": status,
                "days_remaining": days_remaining,
                "reminder_threshold": threshold,
            }
        rows.append(row)

    counts = {status: sum(row["status"] == status for row in rows) for status in _STATUS_PRIORITY}
    if counts["expired"] or counts["expires_today"] or counts["due_soon"]:
        status = "action_required"
    elif counts["unknown"]:
        status = "warning"
    else:
        status = "ok"
    rows.sort(key=lambda row: (_STATUS_PRIORITY[row["status"]], row["name"], row["id"]))
    return {
        "version": LEDGER_VERSION,
        "status": status,
        "as_of": current_day.isoformat(),
        "reminder_days": list(reminder_days),
        "summary": {"total": len(rows), **counts},
        "resources": rows,
        "safety": {
            "read_only": True,
            "payments_performed": False,
            "auto_renew_changed": False,
            "credentials_allowed": False,
        },
    }


def _missing_report(path: Path, *, today: date) -> dict[str, Any]:
    return {
        "version": LEDGER_VERSION,
        "status": "missing",
        "as_of": today.isoformat(),
        "reminder_days": list(DEFAULT_REMINDER_DAYS),
        "summary": {
            "total": 0,
            "expired": 0,
            "expires_today": 0,
            "due_soon": 0,
            "unknown": 0,
            "ok": 0,
        },
        "resources": [],
        "safety": {
            "read_only": True,
            "payments_performed": False,
            "auto_renew_changed": False,
            "credentials_allowed": False,
        },
        "ledger": str(path),
    }


def _parse_today(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--today 必须是 YYYY-MM-DD") from exc


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读检查 OpenClaw 资源续费台账")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get("OPENCLAW_RENEWALS_FILE", DEFAULT_LEDGER)),
        help="续费台账路径；默认使用被 Git 忽略的本机 renewals.json",
    )
    parser.add_argument("--today", type=_parse_today, default=date.today())
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument(
        "--validate-template",
        action="store_true",
        help="把缺失文件或非 unknown 到期日视为错误，用于 CI 校验仓库模板",
    )
    return parser.parse_args(argv)


def _print_human(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"续费台账状态：{report['status']}（截至 {report['as_of']}）")
    print(
        "总数={total} 已过期={expired} 今日到期={expires_today} "
        "30天内={due_soon} 日期未知={unknown} 正常={ok}".format(**summary)
    )
    for item in report["resources"]:
        remaining = "unknown" if item["days_remaining"] is None else str(item["days_remaining"])
        print(f"- {item['name']}: {item['status']}（剩余天数 {remaining}）")
    print("本检查只提醒，不会付款、续费、登录供应商或修改自动续费。")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.expanduser()
    if not config_path.is_absolute():
        repo_root = Path(__file__).resolve().parents[1]
        config_path = repo_root / config_path
    if not config_path.is_file():
        report = _missing_report(config_path, today=args.today)
        print(json.dumps(report, ensure_ascii=False) if args.json else "续费台账不存在，请从模板复制后填写。")
        return 2 if args.validate_template else 0

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        report = evaluate_ledger(payload, today=args.today)
        if args.validate_template and any(item["status"] != "unknown" for item in report["resources"]):
            raise LedgerError("仓库模板的 expires_on 必须全部保持 unknown，避免把示例日期误当真实到期日")
    except (OSError, json.JSONDecodeError, LedgerError) as exc:
        error_report = {
            "version": LEDGER_VERSION,
            "status": "invalid",
            "as_of": args.today.isoformat(),
            "error": str(exc),
            "safety": {
                "read_only": True,
                "payments_performed": False,
                "auto_renew_changed": False,
                "credentials_allowed": False,
            },
        }
        print(json.dumps(error_report, ensure_ascii=False) if args.json else f"续费台账无效：{exc}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
