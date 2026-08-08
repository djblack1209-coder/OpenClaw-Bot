"""仅绑定 localhost 的 JIYU 补号助手 FastAPI 页面。"""

from __future__ import annotations

import hmac
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from .core import InputFormatError, ReplenishJob, parse_seller_payload
from .runner import ReplenishRunner

HOST = "127.0.0.1"
PORT = 18796
ORIGIN = f"http://{HOST}:{PORT}"
SESSION_COOKIE = "jiyu_replenish_session"
MAX_REQUEST_BYTES = 520 * 1024
_STATIC_DIR = Path(__file__).with_name("static")


def create_app(*, dry_run: bool = False) -> FastAPI:
    """创建不启用 CORS、敏感输入只驻留进程内存的本地应用。"""
    runner = ReplenishRunner(dry_run=dry_run)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await runner.stop()

    app = FastAPI(
        title="JIYU Sub2 补号助手",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.runner = runner
    app.state.session_token = session_token
    app.state.csrf_token = csrf_token

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        host = request.headers.get("host", "").lower()
        if host not in {HOST, f"{HOST}:{PORT}"}:
            return JSONResponse({"detail": "仅允许本机访问"}, status_code=403)
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin", "")
            cookie = request.cookies.get(SESSION_COOKIE, "")
            csrf = request.headers.get("x-jiyu-csrf", "")
            if (
                origin != ORIGIN
                or not hmac.compare_digest(cookie, session_token)
                or not hmac.compare_digest(csrf, csrf_token)
            ):
                return JSONResponse({"detail": "本地会话校验失败"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    def require_session(request: Request) -> None:
        cookie = request.cookies.get(SESSION_COOKIE, "")
        if not hmac.compare_digest(cookie, session_token):
            raise HTTPException(status_code=403, detail="本地会话已失效，请刷新页面")

    async def read_json(request: Request) -> dict:
        content_length = request.headers.get("content-length", "0")
        if content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="请求内容过大")
        body = await request.body()
        if len(body) > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="请求内容过大")
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="请求格式不正确") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="请求格式不正确")
        return payload

    @app.get("/", response_class=HTMLResponse)
    async def index() -> Response:
        html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace("__CSRF_TOKEN__", csrf_token).replace(
            "__DRY_RUN__", "true" if dry_run else "false"
        )
        response = HTMLResponse(html)
        response.set_cookie(
            SESSION_COOKIE,
            session_token,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
        )
        return response

    @app.get("/app.js")
    async def javascript() -> Response:
        return Response((_STATIC_DIR / "app.js").read_text(encoding="utf-8"), media_type="text/javascript")

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/state")
    async def state(request: Request) -> dict:
        require_session(request)
        return runner.public_state()

    @app.post("/api/parse")
    async def parse(request: Request) -> dict:
        require_session(request)
        payload = await read_json(request)
        raw = payload.get("raw")
        target_channel = payload.get("target_channel", "A")
        if not isinstance(raw, str):
            raise HTTPException(status_code=400, detail="请粘贴卖家发货原文")
        if target_channel not in {"A", "B"}:
            raise HTTPException(status_code=400, detail="请选择渠道A或渠道B")
        try:
            credentials = parse_seller_payload(raw)
            runner.replace_jobs(
                [ReplenishJob(credential=item) for item in credentials],
                target_channel=target_channel,
            )
        except InputFormatError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return runner.public_state()

    @app.post("/api/start")
    async def start(request: Request) -> dict:
        require_session(request)
        try:
            runner.start()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return runner.public_state()

    @app.post("/api/stop")
    async def stop(request: Request) -> dict:
        require_session(request)
        await runner.stop()
        return runner.public_state()

    @app.post("/api/jobs/{job_id}/skip")
    async def skip(job_id: str, request: Request) -> dict:
        require_session(request)
        try:
            runner.skip(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return runner.public_state()

    @app.post("/api/jobs/{job_id}/retry")
    async def retry(job_id: str, request: Request) -> dict:
        require_session(request)
        try:
            runner.retry(job_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return runner.public_state()

    @app.post("/api/jobs/{job_id}/group")
    async def group(job_id: str, request: Request) -> dict:
        require_session(request)
        payload = await read_json(request)
        group_id = payload.get("group_id")
        if not isinstance(group_id, int):
            raise HTTPException(status_code=400, detail="请选择有效分组")
        try:
            runner.choose_group(job_id, group_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return runner.public_state()

    @app.post("/api/jobs/{job_id}/rate")
    async def rate(job_id: str, request: Request) -> dict:
        require_session(request)
        payload = await read_json(request)
        rate_multiplier = payload.get("rate_multiplier")
        if (
            not isinstance(rate_multiplier, (int, float))
            or isinstance(rate_multiplier, bool)
        ):
            raise HTTPException(status_code=400, detail="请输入有效账号倍率")
        try:
            runner.choose_rate(job_id, float(rate_multiplier))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return runner.public_state()

    @app.exception_handler(Exception)
    async def safe_error(_: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return JSONResponse(
            {"detail": "本地助手发生错误，敏感详情未写入响应或日志"},
            status_code=500,
        )

    return app


def run(*, dry_run: bool = False) -> None:
    """以无访问日志模式启动固定 localhost 服务并打开本地页面。"""
    import threading
    import webbrowser

    import uvicorn

    threading.Timer(1.0, lambda: webbrowser.open(ORIGIN)).start()
    uvicorn.run(
        create_app(dry_run=dry_run),
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False,
        server_header=False,
    )
