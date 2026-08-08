"""串行 OAuth 浏览器执行器；验证码和风控只暂停，不绕过。"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from .core import ReplenishJob, current_totp
from .sub2_client import (
    Sub2AdminClient,
    find_duplicate_account,
    group_rate_candidates,
    manual_openai_group_options,
    matching_plan_groups,
)

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 1455
CALLBACK_PATH = "/auth/callback"
_AUTH_HOSTS = {"auth.openai.com", "login.openai.com", "chatgpt.com", "openai.com"}
_OTP_SELECTORS = (
    'input[autocomplete="one-time-code"]',
    'input[name*="otp" i]',
    'input[id*="otp" i]',
    'input[name*="mfa" i]',
    'input[id*="mfa" i]',
    'input[aria-label*="verification code" i]',
    'input[placeholder*="verification code" i]',
    'input[aria-label*="2fa" i]',
    'input[placeholder*="2fa" i]',
)


class JobSkipped(RuntimeError):
    """当前账号被操作者跳过。"""


class BatchStopped(RuntimeError):
    """批次被操作者停止。"""


class ReplenishRunner:
    """持有单进程任务队列和临时浏览器状态。"""

    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.jobs: list[ReplenishJob] = []
        self.target_pool = "self_hosted"
        self.running = False
        self._batch_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._actions: dict[str, asyncio.Queue[tuple[str, int | None]]] = {}
        self._client = Sub2AdminClient()

    def replace_jobs(self, jobs: list[ReplenishJob], *, target_pool: str = "self_hosted") -> None:
        """新批次覆盖旧批次前清除旧凭据引用。"""
        if self.running:
            raise RuntimeError("当前批次仍在运行")
        if target_pool != "self_hosted":
            raise ValueError("补号只能导入 JIYU 自营号池")
        self.wipe_all()
        self.jobs = jobs
        self.target_pool = target_pool
        self._actions = {job.id: asyncio.Queue() for job in jobs}
        self._stop_event = asyncio.Event()

    def public_state(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "dry_run": self.dry_run,
            "target_pool": self.target_pool,
            "jobs": [job.public() for job in self.jobs],
            "notice": "短信、实体手机号、CAPTCHA 或风控必须由本人在打开的浏览器中完成。",
        }

    def start(self) -> None:
        if self.running:
            return
        if not self.jobs:
            raise RuntimeError("请先粘贴并解析账号")
        self.running = True
        self._batch_task = asyncio.create_task(self._run_batch())

    async def stop(self) -> None:
        self._stop_event.set()
        for queue in self._actions.values():
            queue.put_nowait(("stop", None))
        if self._batch_task is not None:
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(self._batch_task), timeout=8)
        for job in self.jobs:
            if not job.terminal:
                job.status = "stopped"
                job.message = "已停止"
        self.wipe_all()

    def skip(self, job_id: str) -> None:
        job = self._find_job(job_id)
        if job.terminal:
            return
        self._actions[job.id].put_nowait(("skip", None))

    def choose_group(self, job_id: str, group_id: int) -> None:
        job = self._find_job(job_id)
        allowed = {int(option["id"]) for option in job.group_options}
        if job.status != "group_required" or group_id not in allowed:
            raise ValueError("所选分组不在本次候选列表中")
        job.status = "group_selected"
        job.message = "分组已确认，正在核对模板账号倍率"
        self._actions[job.id].put_nowait(("group", group_id))

    def choose_rate(self, job_id: str, rate_multiplier: float) -> None:
        job = self._find_job(job_id)
        if job.status != "rate_required" or not 0 <= rate_multiplier <= 100:
            raise ValueError("账号倍率必须是 0 到 100 之间的数字")
        job.status = "rate_selected"
        job.message = "账号倍率已确认，正在创建账号"
        self._actions[job.id].put_nowait(("rate", rate_multiplier))

    def retry(self, job_id: str) -> None:
        job = self._find_job(job_id)
        if job.status not in {"failed", "skipped"}:
            raise ValueError("只有失败或已跳过任务可以重试")
        if not job.credential.email or not job.credential.password or not job.credential.totp_secret:
            raise ValueError("敏感凭据已清除，请重新粘贴该账号")
        job.status = "pending"
        job.message = "等待重试"
        job.group_options = []
        job.selected_group_id = None
        job.rate_options = []
        job.selected_rate_multiplier = None
        if not self.running:
            self.start()

    def wipe_all(self) -> None:
        for job in self.jobs:
            job.wipe_secrets()

    def _find_job(self, job_id: str) -> ReplenishJob:
        for job in self.jobs:
            if secrets.compare_digest(job.id, job_id):
                return job
        raise KeyError("任务不存在")

    async def _run_batch(self) -> None:
        try:
            for job in self.jobs:
                if self._stop_event.is_set():
                    break
                if job.status != "pending":
                    continue
                if self.dry_run:
                    job.status = "dry_run"
                    job.message = "格式与本地页面合同通过；演练模式未登录或创建账号"
                    job.wipe_secrets()
                    continue
                try:
                    await self._run_job(job)
                except JobSkipped:
                    job.status = "skipped"
                    job.message = "已跳过，可在本进程退出前重试"
                except BatchStopped:
                    job.status = "stopped"
                    job.message = "已停止"
                    break
                except Exception:
                    job.status = "failed"
                    job.message = "操作失败，未记录敏感详情；可重试或检查网络与钥匙串"
                finally:
                    if job.status in {"success", "duplicate", "stopped"}:
                        job.wipe_secrets()
                    elif job.status in {"failed", "skipped"}:
                        job.wipe_oauth_tokens()
        finally:
            self.running = False

    async def _run_job(self, job: ReplenishJob) -> None:
        self._raise_if_action(job)
        job.status = "oauth"
        job.message = "正在创建 Sub2 OAuth 会话"
        auth = await self._client.generate_openai_auth_url()
        code, state = await self._run_browser_oauth(job, auth["auth_url"])

        self._raise_if_action(job)
        job.status = "oauth"
        job.message = "授权完成，正在安全换取账号计划"
        token_info = await self._client.exchange_openai_code(auth["session_id"], code, state)
        job.token_info = token_info
        job.plan_type = str(token_info.get("plan_type") or "")

        accounts = await self._client.list_openai_accounts()
        duplicate = find_duplicate_account(accounts, token_info)
        if duplicate is not None:
            job.account_id = duplicate.get("id") if isinstance(duplicate.get("id"), int) else None
            job.status = "duplicate"
            job.message = "Sub2 已存在相同邮箱或 OpenAI 账号标识，未重复创建"
            return

        all_groups = await self._client.list_openai_groups()
        groups = matching_plan_groups(all_groups, job.plan_type)
        if len(groups) == 1:
            job.selected_group_id = int(groups[0]["id"])
        else:
            job.status = "group_required"
            job.group_options = groups or manual_openai_group_options(all_groups)
            if groups:
                job.message = "计划已识别，但对应自营号池存在多个目标分组，请人工核对"
            else:
                job.message = "计划无法识别或对应自营号池不存在，请核对 Plus/Pro 自营号池"
            if not job.group_options:
                raise RuntimeError("没有可选的 JIYU OpenAI Plus/Pro 自营号池")
            action, group_id = await self._actions[job.id].get()
            if action == "skip":
                raise JobSkipped
            if action == "stop":
                raise BatchStopped
            if action != "group" or group_id is None:
                raise RuntimeError("未收到有效分组选择")
            self.choose_group_value(job, group_id)

        if job.token_info is None or job.selected_group_id is None:
            raise RuntimeError("账号创建前状态不完整")
        rate_candidates = group_rate_candidates(
            await self._client.list_group_accounts(job.selected_group_id)
        )
        if len(rate_candidates) == 1:
            job.selected_rate_multiplier = rate_candidates[0]
        else:
            job.status = "rate_required"
            job.rate_options = rate_candidates
            job.message = (
                "目标分组没有模板账号倍率，请人工输入并确认"
                if not rate_candidates
                else "目标分组模板账号倍率不一致，请人工核对后确认"
            )
            action, rate = await self._actions[job.id].get()
            if action == "skip":
                raise JobSkipped
            if action == "stop":
                raise BatchStopped
            if action != "rate" or rate is None or not 0 <= float(rate) <= 100:
                raise RuntimeError("未收到有效账号倍率")
            job.selected_rate_multiplier = float(rate)

        if job.selected_rate_multiplier is None:
            raise RuntimeError("账号倍率未确认")
        job.status = "creating"
        job.message = "正在通过 Sub2 原生账号接口创建并绑定分组"
        created = await self._client.create_openai_oauth_account(
            job.token_info,
            job.selected_group_id,
            job.selected_rate_multiplier,
            job.id,
        )
        job.account_id = int(created["id"])
        verified = await self._client.get_account(job.account_id)
        group_ids = verified.get("group_ids") if isinstance(verified.get("group_ids"), list) else []
        if (
            verified.get("platform") != "openai"
            or verified.get("type") != "oauth"
            or verified.get("status") != "active"
            or job.selected_group_id not in group_ids
            or abs(float(verified.get("rate_multiplier", -1)) - job.selected_rate_multiplier) > 1e-8
        ):
            raise RuntimeError("账号创建后回读合同不一致")
        job.status = "success"
        job.message = "补号成功：账号、计划、分组和启用状态已回读确认"

    def choose_group_value(self, job: ReplenishJob, group_id: int) -> None:
        allowed = {int(option["id"]) for option in job.group_options}
        if group_id not in allowed:
            raise ValueError("分组不在候选列表中")
        job.selected_group_id = group_id

    def _raise_if_action(self, job: ReplenishJob) -> None:
        if self._stop_event.is_set():
            raise BatchStopped
        queue = self._actions[job.id]
        try:
            action, _ = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        if action == "stop":
            raise BatchStopped
        if action == "skip":
            raise JobSkipped

    async def _run_browser_oauth(self, job: ReplenishJob, auth_url: str) -> tuple[str, str]:
        parsed = urlparse(auth_url)
        if parsed.scheme != "https" or parsed.hostname not in _AUTH_HOSTS:
            raise RuntimeError("Sub2 返回的 OAuth 地址不在允许列表")

        expected_state = parse_qs(parsed.query).get("state", [""])[0]
        if not expected_state:
            raise RuntimeError("Sub2 返回的 OAuth 地址缺少 state")
        callback: asyncio.Future[tuple[str, str]] = asyncio.get_running_loop().create_future()
        server = await self._start_callback_server(callback, expected_state)
        try:
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise RuntimeError("缺少 Playwright，请先安装项目依赖") from exc

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=False)
                context = await browser.new_context(
                    accept_downloads=False,
                    service_workers="block",
                    viewport={"width": 1180, "height": 820},
                )
                page = await context.new_page()
                try:
                    job.message = "已打开隔离浏览器，正在自动填写登录信息"
                    await page.goto(auth_url, wait_until="domcontentloaded", timeout=45_000)
                    started_at = time.monotonic()
                    idle_since = started_at
                    attempted: dict[str, float] = {}
                    while time.monotonic() - started_at < 900:
                        self._raise_if_action(job)
                        if callback.done():
                            return callback.result()
                        if page.is_closed():
                            raise RuntimeError("登录窗口已关闭")
                        if await self._has_manual_challenge(page):
                            job.status = "manual"
                            job.message = "需要人工完成：请在登录窗口处理 CAPTCHA、短信、实体手机号或未知风控"
                            await asyncio.sleep(0.8)
                            continue
                        action = await self._try_fill_login(page, job, attempted)
                        if action:
                            idle_since = time.monotonic()
                            if job.status == "manual":
                                job.status = "oauth"
                                job.message = "人工步骤已通过，继续自动完成登录"
                        elif time.monotonic() - idle_since > 8:
                            job.status = "manual"
                            job.message = "需要人工完成：请在登录窗口处理 CAPTCHA、短信、实体手机号或未知风控"
                        await asyncio.sleep(0.8)
                    raise TimeoutError("OAuth 登录等待超时")
                finally:
                    await context.close()
                    await browser.close()
        finally:
            server.close()
            await server.wait_closed()

    async def _try_fill_login(self, page: Any, job: ReplenishJob, attempted: dict[str, float]) -> bool:
        now = time.monotonic()
        fields = (
            ("email", ('input[type="email"]', 'input[name="email"]', 'input[name="username"]')),
            ("password", ('input[type="password"]', 'input[name="password"]')),
            ("otp", _OTP_SELECTORS),
        )
        for kind, selectors in fields:
            if now - attempted.get(kind, 0) < (25 if kind == "otp" else 4):
                continue
            for selector in selectors:
                locator = page.locator(selector).first
                try:
                    if not await locator.is_visible(timeout=200):
                        continue
                    value = (
                        job.credential.email
                        if kind == "email"
                        else job.credential.password
                        if kind == "password"
                        else current_totp(job.credential.totp_secret)
                    )
                    await locator.fill(value, timeout=3_000)
                    attempted[kind] = now
                    submit = page.locator('button[type="submit"]').first
                    if await submit.is_visible(timeout=300) and await submit.is_enabled():
                        await submit.click(timeout=3_000)
                    else:
                        await locator.press("Enter")
                    job.message = {
                        "email": "邮箱已填写，等待密码页",
                        "password": "密码已填写，等待 2FA 或授权确认",
                        "otp": "本地 2FA 已填写，等待授权回调",
                    }[kind]
                    return True
                except Exception:
                    continue
        return False

    async def _has_manual_challenge(self, page: Any) -> bool:
        selectors = (
            'iframe[src*="captcha"]',
            '[data-sitekey]',
            'input[type="tel"]',
            'text=/captcha|verify you are human|phone number|security check|unusual activity/i',
        )
        for selector in selectors:
            try:
                if await page.locator(selector).first.is_visible(timeout=100):
                    return True
            except Exception:
                continue
        return False

    async def _start_callback_server(
        self,
        callback: asyncio.Future[tuple[str, str]],
        expected_state: str,
    ) -> asyncio.AbstractServer:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                request_line = await asyncio.wait_for(reader.readline(), timeout=5)
                parts = request_line.decode("ascii", errors="ignore").split(" ")
                target = parts[1] if len(parts) >= 2 else ""
                parsed = urlparse(target)
                query = parse_qs(parsed.query)
                code = query.get("code", [""])[0]
                state = query.get("state", [""])[0]
                valid = (
                    parsed.path == CALLBACK_PATH
                    and bool(code)
                    and bool(state)
                    and hmac.compare_digest(state, expected_state)
                )
                if valid and not callback.done():
                    callback.set_result((code, state))
                status = "200 OK" if valid else "400 Bad Request"
                body = (
                    "<h1>授权已接收</h1><p>可以回到 JIYU 补号助手查看进度。</p>"
                    if valid
                    else "<h1>授权回调无效</h1>"
                ).encode("utf-8")
                headers = (
                    f"HTTP/1.1 {status}\r\nContent-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
                ).encode("ascii")
                writer.write(headers + body)
                await writer.drain()
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()

        try:
            return await asyncio.start_server(handle, CALLBACK_HOST, CALLBACK_PORT)
        except OSError as exc:
            raise RuntimeError("本机 1455 端口被占用，请关闭占用程序后重试") from exc
