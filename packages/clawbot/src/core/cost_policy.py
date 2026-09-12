"""Explicit deployment prices; model marketing names never imply a free API."""

from dataclasses import asdict, dataclass
from decimal import Decimal

from src.core.cost_ledger import BudgetDenied, LedgerError, _identity, money_units


def tokens(value):
    if type(value) is not int or value < 0:
        raise LedgerError("invalid token count")
    return value


@dataclass(frozen=True)
class DeploymentPrice:
    provider: str
    deployment_id: str
    model: str
    snapshot: str
    input_per_million: Decimal
    output_per_million: Decimal
    max_input_tokens: int
    max_output_tokens: int
    source: str

    @classmethod
    def from_deployment(cls, deployment):
        info = deployment.get("model_info", {})
        price = info.get("accounting")
        if not isinstance(price, dict):
            raise BudgetDenied("deployment price unknown")
        try:
            if price["currency"] != "USD" or not price["source"]:
                raise ValueError
            values = [Decimal(str(price[key])) for key in ("input_per_million", "output_per_million")]
            for value in values:
                money_units(value)
            input_limit = tokens(price["max_input_tokens"])
            output_limit = tokens(price["max_output_tokens"])
            if not input_limit or not output_limit:
                raise ValueError
            return cls(
                _identity(price["provider"]),
                _identity(info["id"]),
                _identity(deployment["litellm_params"]["model"]),
                _identity(price["snapshot"]),
                *values,
                input_limit,
                output_limit,
                _identity(price["source"]),
            )
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            raise BudgetDenied("invalid deployment price configuration") from exc

    @property
    def is_zero(self):
        return self.input_per_million == self.output_per_million == 0

    def snapshot_data(self):
        data = asdict(self)
        for key in ("input_per_million", "output_per_million"):
            data[key] = str(data[key])
        return {**data, "currency": "USD"}

    def bound(self, max_output):
        maximum = tokens(max_output)
        if not maximum or maximum > self.max_output_tokens:
            raise BudgetDenied("output token bound unavailable")
        # Reserve the configured provider input limit, not a heuristic tokenizer
        # estimate; this includes schema/system/tool overhead added by the SDK.
        return self.cost(self.max_input_tokens, maximum)

    def cost(self, input_tokens, output_tokens):
        return (
            tokens(input_tokens) * self.input_per_million + tokens(output_tokens) * self.output_per_million
        ) / 1_000_000

    def usage_cost(self, usage):
        if usage is None:
            return (Decimal(0), {}) if self.is_zero else (None, {})
        data = usage if isinstance(usage, dict) else usage.model_dump()
        prompt = data.get("prompt_tokens", data.get("input_tokens"))
        output = data.get("completion_tokens", data.get("output_tokens"))
        counted = {
            key: tokens(value)
            for key, value in (("input_tokens", prompt), ("output_tokens", output))
            if value is not None
        }
        # Store only numeric, explicitly recognized billing dimensions. Arbitrary
        # response fields never enter the cost database.
        details = data.get("prompt_tokens_details") or {}
        completion = data.get("completion_tokens_details") or {}
        server = data.get("server_tool_use") or {}
        cache = details.get("cache_creation_token_details") or {}
        extra = {
            "cache_read_tokens": data.get("cache_read_input_tokens") or details.get("cached_tokens"),
            "cache_write_tokens": data.get("cache_creation_input_tokens")
            or details.get("cache_creation_tokens")
            or (
                sum(tokens(cache.get(key) if cache.get(key) is not None else 0) for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"))
                if cache
                else 0
            ),
            "audio_input_tokens": details.get("audio_tokens"),
            "audio_output_tokens": completion.get("audio_tokens"),
            "web_search_requests": data.get("web_search_requests")
            or server.get("web_search_requests")
            or details.get("web_search_requests"),
            "code_execution_requests": server.get("code_execution_requests"),
        }
        for key, value in extra.items():
            if value:
                counted[key] = tokens(value)

        def has_quantity(value):
            if isinstance(value, dict):
                return any(has_quantity(child) for child in value.values())
            if isinstance(value, (list, tuple)):
                return any(has_quantity(child) for child in value)
            return bool(value)

        # Only plain-text subdivisions known to be included in the two priced
        # token totals are supported. Other nested dimensions (including future
        # SDK fields) are unknown even when input/output token rates are zero.
        supported_details = {
            "prompt_tokens_details": {"text_tokens"},
            "completion_tokens_details": {"text_tokens", "reasoning_tokens"},
        }
        supported = {"prompt_tokens", "input_tokens", "completion_tokens", "output_tokens", "total_tokens"}
        unsupported = False
        for key, value in data.items():
            if key in supported_details:
                if value is None:
                    continue
                if not isinstance(value, dict):
                    unsupported = True
                    continue
                unsupported |= any(
                    has_quantity(child) for name, child in value.items() if name not in supported_details[key]
                )
            elif key not in supported:
                unsupported |= has_quantity(value)
        if any(extra.values()) or unsupported:
            return None, counted
        if prompt is None or output is None:
            return (Decimal(0), counted) if self.is_zero else (None, counted)
        return self.cost(prompt, output), counted
