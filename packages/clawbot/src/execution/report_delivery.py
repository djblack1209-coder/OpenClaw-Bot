"""Receipt-based ordinary reports. Telegram acceptance never implies user reading."""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
from dataclasses import dataclass
from datetime import timedelta

from telegram.error import BadRequest, ChatMigrated, Forbidden, InvalidToken, NetworkError, RetryAfter, TelegramError

from src.constants import TG_SAFE_LENGTH


@dataclass(frozen=True)
class Target:
    identity: str
    address: int | str


@dataclass(frozen=True)
class Receipt:
    status: str
    message_id: str | None = None
    reason: str = ''
    retry_after: float = 60


@dataclass(frozen=True)
class ReportDocument:
    text: str
    quality: str = 'unverified'


@dataclass(frozen=True)
class PreferenceDecision:
    state: str | None = None
    reason: str = ''

    def __bool__(self):
        return self.state is None


class ReportPreferences:
    """Read report controls before generation and each external send; fail closed."""
    def __init__(self, controls_path, user_prefs, public_target, private_target):
        self.controls_path, self.user_prefs = controls_path, user_prefs
        self.public_target, self.private_target = public_target, private_target

    def __call__(self, kind, _target, channel):
        # Retain historic receipts, but never revive the retired general-Bot brief
        # through old environment flags or persisted scheduler controls.
        if kind == 'morning_news':
            return PreferenceDecision('disabled', 'retired_to_global_intelligence')
        state = json.loads(self.controls_path.read_text()) if self.controls_path.exists() else {}
        scheduler, settings = state.get('scheduler', {}), state.get('global_settings', {})
        def flag(mapping, key, default):
            value = mapping.get(key, default)
            if type(value) is not bool:
                raise ValueError('invalid report control value')
            return value
        if flag(scheduler, 'maintenance_mode', False) or flag(settings, 'maintenance_mode', False):
            return PreferenceDecision('blocked', 'maintenance_paused')
        if not flag(scheduler, 'enabled', True) or not flag(settings, 'scheduler_enabled', True):
            return PreferenceDecision('blocked', 'scheduler_paused')
        if not flag(scheduler.get('tasks', {}).get(kind, {}), 'enabled', True):
            return PreferenceDecision('disabled', 'task_disabled')
        env_flag, default = {'daily_brief': ('OPS_BRIEF_ENABLED', ''),
                         'weekly_report': ('WEEKLY_REPORT_ENABLED', '1')}[kind]
        if os.getenv(env_flag, default).lower() not in {'1', 'true', 'yes', 'on'}:
            return PreferenceDecision('disabled', 'report_channel_disabled')
        if channel == 'wechat' and os.getenv('WECHAT_NOTIFY_ENABLED', '').lower() not in {'1', 'true', 'yes', 'on'}:
            return PreferenceDecision('disabled', 'mirror_disabled')
        address = (self.public_target if kind == 'daily_brief' else self.private_target)()
        if not address:
            return PreferenceDecision('blocked', 'target_unavailable')
        if not self.user_prefs.report_enabled(address):
            return PreferenceDecision('disabled', 'preference_disabled')
        return PreferenceDecision()


def split_report(text, limit=TG_SAFE_LENGTH):
    """Keep every character and bound UTF-16 units (including astral emoji)."""
    if not isinstance(text, str) or not text or len(text) > 256_000 or limit < 2:
        raise ValueError('invalid report text or chunk limit')
    result, start, units = [], 0, 0
    for index, character in enumerate(text):
        size = 2 if ord(character) > 0xffff else 1
        if units + size > limit:
            result.append(text[start:index])
            start, units = index, 0
        units += size
    result.append(text[start:])
    return result


class TelegramTransport:
    channel = 'telegram'

    def __init__(self, bot_provider, public_target, private_target):
        self.bot_provider = bot_provider
        self.public_target = public_target
        self.private_target = private_target

    def target(self, kind):
        address = (self.public_target if kind == 'daily_brief' else self.private_target)()
        bot = self.bot_provider()
        if not address or bot is None:
            return None
        try:
            bot_id = bot.id  # requires the already initialized production Bot
        except RuntimeError:
            return None
        return Target(f'{bot_id}:{address}', address)

    async def send(self, target, text):
        try:
            message = await self.bot_provider().send_message(
                chat_id=target.address, text=text, parse_mode=None,
                read_timeout=20, write_timeout=20, connect_timeout=10, pool_timeout=5,
            )
        except RetryAfter as error:
            delay = error.retry_after.total_seconds() if isinstance(error.retry_after, timedelta) else error.retry_after
            return Receipt('retryable_failure', reason='telegram_rate_limit', retry_after=float(delay))
        except (BadRequest, Forbidden, InvalidToken, ChatMigrated) as error:
            return Receipt('permanent_failure', reason=type(error).__name__)
        except (NetworkError, TelegramError) as error:
            return Receipt('unknown', reason=type(error).__name__)
        if not isinstance(message.message_id, int) or message.message_id <= 0:
            return Receipt('unknown', reason='missing_message_id')
        if isinstance(target.address, int) and message.chat.id != target.address:
            return Receipt('unknown', reason='receipt_target_mismatch')
        return Receipt('sent', message_id=str(message.message_id))


class LegacyWechatTransport:
    """The legacy bool bridge has no verifiable receipt; one attempt stays unknown."""
    channel = 'wechat'

    def target(self, _kind):
        from src import wechat_bridge
        if not wechat_bridge._WECHAT_ENABLED:
            return None
        user_id = wechat_bridge._creds.user_id
        if not user_id:
            return None
        return Target(hashlib.sha256(str(user_id).encode()).hexdigest(), str(user_id))

    async def send(self, target, text):
        from src.wechat_bridge import send_to_wechat
        await send_to_wechat(text, user_id=target.address, single_attempt=True)
        return Receipt('unknown', reason='legacy_mirror_receipt_unverified')


class ReportDeliveryService:
    def __init__(self, store, telegram, *, allowed=None, mirror=None, catchup_seconds=7200):
        self.store, self.telegram, self.mirror = store, telegram, mirror
        self.allowed = allowed or (lambda *_: True)
        self.catchup_seconds = max(60, min(int(catchup_seconds), 21600))

    def _preflight(self, kind, transport, target):
        try:
            enabled = self.allowed(kind, target, transport.channel)
        except Exception:
            return 'blocked', 'preference_unavailable'
        if isinstance(enabled, PreferenceDecision) and enabled.state is not None:
            return enabled.state, enabled.reason
        if not enabled:
            return 'disabled', 'preference_disabled'
        if target is None:
            return 'blocked', 'target_unavailable'
        if transport.target(kind) != target:
            return 'blocked', 'target_changed'
        return None

    async def run(self, kind, planned, generator):
        self.store.recover()
        ident = await self._deliver(kind, planned, generator, self.telegram)
        # Mirror failures never change, retry, or invalidate a Telegram receipt.
        if self.mirror is not None and self.mirror.target(kind) is not None:
            row = self.store.get(ident)
            if row['text'] is not None:
                async def cached(_):
                    return ReportDocument(row['text'], row['generation_quality'])
                await self._deliver(kind, planned, cached, self.mirror)
        return ident

    async def _deliver(self, kind, planned, generator, transport):
        if planned.tzinfo is None:
            raise ValueError('scheduled time must be timezone aware')
        target = transport.target(kind)
        ident = self.store.ensure(kind, planned.timestamp(), planned.timestamp() + self.catchup_seconds,
                                  transport.channel, target.identity if target else 'unconfigured')
        claimed = self.store.claim(ident)
        if claimed is None:
            return ident
        token = claimed['token']
        try:
            blocked = self._preflight(kind, transport, target)
            if blocked:
                self.store.defer(ident, token, *blocked)
                return ident
            if claimed['job']['text'] is None:
                self.store.begin_generation(ident, token)
                try:
                    timeout = min(120, self.store.lease_seconds * .75,
                                  claimed['job']['deadline'] - self.store.clock())
                    async with asyncio.timeout(max(.01, timeout)):
                        document = generator(planned)
                        if inspect.isawaitable(document):
                            document = await document
                    if isinstance(document, str):
                        document = ReportDocument(document)
                    if not isinstance(document, ReportDocument):
                        raise ValueError('generator must return report content')
                    self.store.generated(ident, token, document.text, split_report(document.text), quality=document.quality)
                except Exception as error:
                    self.store.generation_failed(ident, token, type(error).__name__)
                    return ident
            for part in self.store.get(ident)['parts']:
                if part['state'] == 'sent':
                    continue
                blocked = self._preflight(kind, transport, target)
                if blocked:
                    self.store.defer(ident, token, *blocked)
                    break
                if self.store.clock() >= claimed['job']['deadline']:
                    self.store.defer(ident, token, 'expired', 'window_expired')
                    break
                attempt = self.store.begin_part(ident, token, part['seq'])
                # Persist sending BEFORE the external effect. Cancellation, a bad
                # adapter, or a failed ack write leaves unknown in finally/recovery.
                async with asyncio.timeout(min(60, self.store.lease_seconds * .75)):
                    receipt = await transport.send(target, part['text'])
                self.store.finish_part(ident, token, part['seq'], attempt, receipt.status,
                    message_id=receipt.message_id, reason=receipt.reason, retry_after=receipt.retry_after)
                if receipt.status != 'sent':
                    break
        finally:
            self.store.release(ident, token)
        return ident
