"""Sub2API 原生管理员接口的最小安全客户端。"""

from __future__ import annotations

import math
import subprocess
from typing import Any

import httpx

SUB2_BASE_URL = "https://jiyu.245334.xyz"
KEYCHAIN_SERVICE = "JIYU AI Sub2API 管理员 API Key"


class Sub2ClientError(RuntimeError):
    """不携带第三方响应正文的安全错误。"""


def read_admin_api_key() -> str:
    """只从 macOS 钥匙串读取管理员 API Key，禁止回显 stderr。"""
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise Sub2ClientError("无法从 macOS 钥匙串读取管理员 API Key") from exc
    key = result.stdout.strip()
    if not key:
        raise Sub2ClientError("macOS 钥匙串中的管理员 API Key 为空")
    return key


class Sub2AdminClient:
    """请求只发往固定生产域名，响应错误不带正文。"""

    def __init__(self) -> None:
        self._api_key: str | None = None

    def _key(self) -> str:
        if self._api_key is None:
            self._api_key = read_admin_api_key()
        return self._api_key

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"x-api-key": self._key(), "accept": "application/json"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            async with httpx.AsyncClient(
                base_url=SUB2_BASE_URL,
                headers=headers,
                timeout=httpx.Timeout(30.0),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.request(method, path, json=json_body, params=params)
        except httpx.HTTPError as exc:
            raise Sub2ClientError("无法连接 JIYU Sub2API") from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise Sub2ClientError(f"JIYU Sub2API 请求失败（HTTP {response.status_code}）")
        try:
            payload = response.json()
        except ValueError as exc:
            raise Sub2ClientError("JIYU Sub2API 返回了无效响应") from exc
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise Sub2ClientError("JIYU Sub2API 拒绝了本次操作")
        return payload.get("data")

    async def generate_openai_auth_url(self) -> dict[str, str]:
        data = await self._request("POST", "/api/v1/admin/openai/generate-auth-url", json_body={})
        if not isinstance(data, dict) or not data.get("auth_url") or not data.get("session_id"):
            raise Sub2ClientError("Sub2 未返回有效的 OpenAI OAuth 会话")
        return {"auth_url": str(data["auth_url"]), "session_id": str(data["session_id"])}

    async def exchange_openai_code(self, session_id: str, code: str, state: str) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/api/v1/admin/openai/exchange-code",
            json_body={"session_id": session_id, "code": code, "state": state},
        )
        if not isinstance(data, dict) or not data.get("access_token"):
            raise Sub2ClientError("Sub2 未返回有效的 OpenAI OAuth 结果")
        return data

    async def list_openai_accounts(self) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/api/v1/admin/accounts",
            params={"platform": "openai", "page": 1, "page_size": 1000, "sort_by": "name"},
        )
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise Sub2ClientError("Sub2 账号列表响应格式不正确")
        return [item for item in data["items"] if isinstance(item, dict)]

    async def list_group_accounts(self, group_id: int) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/api/v1/admin/accounts",
            params={
                "platform": "openai",
                "group": group_id,
                "page": 1,
                "page_size": 1000,
                "sort_by": "name",
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise Sub2ClientError("Sub2 分组账号列表响应格式不正确")
        return [item for item in data["items"] if isinstance(item, dict)]

    async def list_openai_groups(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v1/admin/groups/all", params={"platform": "openai"})
        if not isinstance(data, list):
            raise Sub2ClientError("Sub2 分组列表响应格式不正确")
        return [item for item in data if isinstance(item, dict)]

    async def create_openai_oauth_account(
        self,
        token_info: dict[str, Any],
        group_id: int,
        rate_multiplier: float,
        idempotency_key: str,
    ) -> dict[str, Any]:
        credentials: dict[str, Any] = {"access_token": token_info["access_token"]}
        for key in (
            "refresh_token",
            "id_token",
            "email",
            "chatgpt_account_id",
            "chatgpt_user_id",
            "organization_id",
            "plan_type",
            "subscription_expires_at",
            "client_id",
        ):
            value = token_info.get(key)
            if value not in (None, ""):
                credentials[key] = value
        expires_at = token_info.get("expires_at")
        if isinstance(expires_at, (int, float)) and expires_at > 0:
            from datetime import UTC, datetime

            credentials["expires_at"] = datetime.fromtimestamp(expires_at, tz=UTC).isoformat()

        name = str(token_info.get("email") or token_info.get("chatgpt_account_id") or "JIYU OpenAI OAuth")
        data = await self._request(
            "POST",
            "/api/v1/admin/accounts",
            json_body={
                "name": name,
                "platform": "openai",
                "type": "oauth",
                "credentials": credentials,
                "extra": {"import_source": "jiyu_local_replenish_helper"},
                "concurrency": 3,
                "priority": 50,
                "rate_multiplier": rate_multiplier,
                "group_ids": [group_id],
                "upstream_billing_probe_enabled": False,
            },
            idempotency_key=f"jiyu-replenish-{idempotency_key}",
        )
        if not isinstance(data, dict) or not isinstance(data.get("id"), int):
            raise Sub2ClientError("Sub2 创建账号后未返回账号编号")
        return data

    async def get_account(self, account_id: int) -> dict[str, Any]:
        data = await self._request("GET", f"/api/v1/admin/accounts/{account_id}")
        if not isinstance(data, dict):
            raise Sub2ClientError("Sub2 账号回读响应格式不正确")
        return data


def find_duplicate_account(accounts: list[dict[str, Any]], token_info: dict[str, Any]) -> dict[str, Any] | None:
    """按邮箱与 OpenAI 账号标识去重，不比较或输出 Token。"""
    email = str(token_info.get("email") or "").strip().casefold()
    account_id = str(token_info.get("chatgpt_account_id") or "").strip()
    for account in accounts:
        credentials = account.get("credentials")
        if not isinstance(credentials, dict):
            credentials = {}
        existing_email = str(credentials.get("email") or account.get("name") or "").strip().casefold()
        existing_account_id = str(credentials.get("chatgpt_account_id") or "").strip()
        if email and existing_email == email:
            return account
        if account_id and existing_account_id == account_id:
            return account
    return None


def matching_plan_groups(groups: list[dict[str, Any]], plan_type: str) -> list[dict[str, Any]]:
    """按 OAuth 计划匹配唯一启用的 JIYU OpenAI 自营号池。"""
    normalized_plan = plan_type.strip().lower()
    plan = "plus" if "plus" in normalized_plan else "pro" if "pro" in normalized_plan else ""
    if not plan:
        return []
    matches: list[dict[str, Any]] = []
    for group in groups:
        name = str(group.get("name") or "")
        if (
            group.get("platform") == "openai"
            and group.get("status") == "active"
            and name.startswith("JIYU")
            and "openai" in name.casefold()
            and plan in name.casefold()
            and "自营号池" in name
            and isinstance(group.get("id"), int)
        ):
            match = {"id": group["id"], "name": name}
            template_rate = group_rate_template(group)
            if template_rate is not None:
                match["rate_multiplier"] = template_rate
            matches.append(match)
    return matches


def manual_openai_group_options(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """计划未知时只提供 Plus/Pro 自营号池分组。"""
    options: list[dict[str, Any]] = []
    for group in groups:
        name = str(group.get("name") or "")
        normalized = name.casefold()
        if (
            group.get("platform") == "openai"
            and group.get("status") == "active"
            and name.startswith("JIYU")
            and "openai" in normalized
            and "自营号池" in name
            and ("plus" in normalized or "pro" in normalized)
            and isinstance(group.get("id"), int)
        ):
            option = {"id": group["id"], "name": name}
            template_rate = group_rate_template(group)
            if template_rate is not None:
                option["rate_multiplier"] = template_rate
            options.append(option)
    return options


def group_rate_template(group: dict[str, Any] | None) -> float | None:
    """读取自营号池分组倍率，作为空池首个账号的明确模板。"""
    if not isinstance(group, dict):
        return None
    raw = group.get("rate_multiplier")
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(rate) or not 0 <= rate <= 100:
        return None
    return round(rate, 8)


def group_rate_candidates(accounts: list[dict[str, Any]]) -> list[float]:
    """提取目标分组现有账号倍率；不使用默认值或分组倍率反推。"""
    rates: set[float] = set()
    for account in accounts:
        raw = account.get("rate_multiplier")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw >= 0:
            rates.add(round(float(raw), 8))
    return sorted(rates)
