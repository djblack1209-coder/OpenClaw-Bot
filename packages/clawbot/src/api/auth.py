"""Per-application API authentication, shared by HTTP and WebSocket."""
import hmac
import logging
import os
from dataclasses import dataclass, field
from ipaddress import ip_address

from fastapi import HTTPException, WebSocket
from starlette.requests import HTTPConnection

logger = logging.getLogger(__name__)
_DEVELOPMENT_MODES = frozenset({'development', 'dev', 'test'})


@dataclass(frozen=True)
class APIAuthContext:
    """A startup snapshot; never infer bind policy from request/proxy headers."""

    host: str
    env_mode: str
    token: str = field(repr=False)

    @classmethod
    def resolve(cls, *, host: str | None = None, env_mode: str | None = None,
                api_token: str | None = None) -> 'APIAuthContext':
        bind = (host if host is not None else os.getenv('API_HOST', '127.0.0.1')).strip().lower()
        if bind == 'localhost':
            bind = '127.0.0.1'
        if bind.startswith('[') and bind.endswith(']'):
            bind = bind[1:-1]
        # Require a concrete IP: DNS changes cannot widen a previously local bind.
        try:
            bind = str(ip_address(bind))
        except ValueError as error:
            raise ValueError('API_HOST must be an IP address or localhost') from error
        mode = (env_mode if env_mode is not None else os.getenv('ENV', 'development')).strip().lower()
        token = api_token if api_token is not None else os.getenv('OPENCLAW_API_TOKEN', '')
        if token and (not token.strip() or any(char in token for char in '\r\n\x00')):
            raise ValueError('Invalid API token configuration')
        return cls(host=bind, env_mode=mode, token=token)

    @property
    def allows_local_development(self) -> bool:
        return self.env_mode in _DEVELOPMENT_MODES and ip_address(self.host).is_loopback

    def matches(self, candidate: str) -> bool:
        return bool(candidate) and hmac.compare_digest(candidate.encode(), self.token.encode())


def _connection_context(conn: HTTPConnection) -> APIAuthContext | None:
    app = conn.scope.get('app')
    context = getattr(getattr(app, 'state', None), 'api_auth_context', None)
    return context if isinstance(context, APIAuthContext) else None


def log_token_status(context: APIAuthContext) -> None:
    if context.token:
        logger.info('[API Auth] API Token authentication enabled')
    elif context.allows_local_development:
        logger.warning('[API Auth] Explicit loopback development without API Token')
    else:
        logger.critical('[API Auth] API Token missing; requests will be rejected')


async def verify_api_token(conn: HTTPConnection) -> None:
    # The WebSocket endpoint rejects with close code 1008 through the same context.
    if conn.scope.get('type') == 'websocket':
        return
    context = _connection_context(conn)
    if context is None:
        raise HTTPException(status_code=503, detail='API authentication context unavailable')
    if not context.token:
        if not context.allows_local_development:
            raise HTTPException(status_code=503, detail='API authentication is not configured')
        return
    if not context.matches(conn.headers.get('x-api-token', '')):
        raise HTTPException(status_code=401, detail='Invalid or missing API token')


def verify_ws_token(websocket: WebSocket) -> bool:
    context = _connection_context(websocket)
    if context is None:
        return False
    if not context.token:
        return context.allows_local_development
    return context.matches(websocket.query_params.get('token', ''))
