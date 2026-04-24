"""
ClawBot 监控 — 告警规则引擎

对标 LiteLLM: 可编程告警规则 + 回调通知。
"""
import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class AlertRule:
    """告警规则"""
    def __init__(self, name: str, condition_fn: Callable[[], bool],
                 message_fn: Callable[[], str], cooldown: float = 300):
        self.name = name
        self.condition_fn = condition_fn
        self.message_fn = message_fn
        self.cooldown = cooldown
        self.last_fired = 0.0

    def check(self) -> str | None:
        now = time.time()
        if now - self.last_fired < self.cooldown:
            return None
        try:
            if self.condition_fn():
                self.last_fired = now
                return self.message_fn()
        except Exception:
            logger.debug("Silenced exception", exc_info=True)
        return None


class AlertManager:
    """告警管理器"""
    def __init__(self):
        self.rules: list[AlertRule] = []
        self._callbacks: list[Callable[[str, str], None]] = []

    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)

    def on_alert(self, callback: Callable[[str, str], None]):
        """注册告警回调 (rule_name, message)"""
        self._callbacks.append(callback)

    def check_all(self) -> list[str]:
        fired = []
        for rule in self.rules:
            msg = rule.check()
            if msg:
                fired.append(msg)
                for cb in self._callbacks:
                    try:
                        cb(rule.name, msg)
                    except Exception as e:
                        logger.debug(f"[Alert] 回调失败: {e}")
        return fired
