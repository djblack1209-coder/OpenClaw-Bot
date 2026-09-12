"""Per-attempt accounting, including streams which are closed before consumption."""

import copy
import datetime
import json
from uuid import uuid4

from src.core.cost_ledger import BudgetDenied, LedgerError
from src.core.cost_policy import DeploymentPrice


class _ProviderUsageCapture:
    """Observe LiteLLM 1.90.2's per-call raw response before Usage defaults.

    Use the same setup the SDK wrapper would use. Keep its callbacks intact;
    only this attempt's logging instance is adapted. Never store response text.
    Providers without this raw-response seam conservatively retain their hold.
    """

    def __init__(self, params):
        from litellm.utils import Rules, function_setup

        params = dict(params)
        params.setdefault("litellm_call_id", str(uuid4()))
        existing = params.get("litellm_logging_obj")
        if existing is None:
            logger, params = function_setup("acompletion", Rules(), datetime.datetime.now(), **params)
        else:
            logger = copy.copy(existing)
            logger.model_call_details = dict(existing.model_call_details)
        self.usage = None
        self.seen = False
        self.logger = logger
        self.original = logger.post_call

        def observe(original_response, *args, **kwargs):
            # More than one response observation is ambiguous (e.g. an SDK
            # service call). Never silently settle only its last response.
            if self.seen:
                self.usage = None
            else:
                self.seen = True
                try:
                    data = json.loads(original_response) if isinstance(original_response, str) else original_response
                    raw = data.get("usage") if isinstance(data, dict) else None
                    self.usage = copy.deepcopy(raw) if isinstance(raw, dict) else None
                except (ValueError, TypeError):
                    self.usage = None
            return self.original(original_response, *args, **kwargs)

        logger.post_call = observe
        self.params = {**params, "litellm_logging_obj": logger}

    def restore(self):
        self.logger.post_call = self.original


class AccountedStream:
    def __init__(self, stream, ledger, attempt, price):
        self.stream = stream
        self.iterator = stream.__aiter__()
        self.ledger, self.attempt, self.price = ledger, attempt, price
        self.usage = None
        self.closed = False
        self.on_finish = None
        from litellm import CustomStreamWrapper

        self.sdk_stream = isinstance(stream, CustomStreamWrapper)
        self.provider_usage = None
        if self.sdk_stream:
            creator = stream.chunk_creator

            def observe(*args, **kwargs):
                raw = kwargs.get("chunk", args[0] if args else None)
                usage = raw.get("usage") if isinstance(raw, dict) else getattr(raw, "usage", None)
                if usage is not None:
                    # Preserve fields actually supplied by the provider. SDK
                    # Usage defaults can otherwise turn a missing count into 0.
                    self.provider_usage = usage if isinstance(usage, dict) else usage.model_dump(exclude_unset=True)
                return creator(*args, **kwargs)

            stream.chunk_creator = observe

    def __aiter__(self):
        return self

    def __getattr__(self, name):
        return getattr(self.stream, name)

    async def __anext__(self):
        if self.closed:
            raise StopAsyncIteration
        try:
            chunk = await self.iterator.__anext__()
        except StopAsyncIteration:
            await self._finish(complete=True)
            raise
        except BaseException:
            await self._finish(complete=False)
            raise
        if getattr(chunk, "usage", None) is not None:
            self.usage = chunk.usage
        return chunk

    async def _finish(self, *, complete):
        if self.closed:
            return
        self.closed = True
        try:
            if complete:
                # LiteLLM 1.90.2 fabricates the final usage chunk. Only usage
                # observed before its transformation can release a paid hold.
                if self.sdk_stream:
                    self.usage = self.provider_usage
                settle_usage(self.ledger, self.attempt, self.price, self.usage)
            else:
                self.ledger.mark_unknown(self.attempt, "stream_interrupted")
        finally:
            try:
                close = getattr(self.stream, "aclose", None)
                if close is not None:
                    await close()
            finally:
                if self.on_finish is not None:
                    self.on_finish(self.usage, complete)

    async def aclose(self):
        await self._finish(complete=False)


def settle_usage(ledger, attempt, price, usage):
    try:
        amount, counted = price.usage_cost(usage)
    except (LedgerError, AttributeError, TypeError, ValueError):
        ledger.mark_unknown(attempt, "invalid_usage")
        return
    if amount is None:
        ledger.mark_unknown(
            attempt,
            "usage_or_billing_unknown",
            usage=counted,
            usage_source="provider_reported" if usage is not None else "unknown",
        )
    else:
        ledger.settle(
            attempt,
            amount,
            usage=counted,
            kind="configured_zero" if price.is_zero else "estimated",
            usage_source="provider_reported" if usage is not None else "configured_zero",
        )


async def accounted_completion(
    *, deployment, controller, transport, params, request_id=None, task_type="chat", usage_from=None, sdk_usage=False
):
    price = DeploymentPrice.from_deployment(deployment)
    configured = deployment["litellm_params"]
    for identity in ("model", "api_base", "api_key", "custom_llm_provider"):
        if identity in params and params[identity] != configured.get(identity):
            raise BudgetDenied("request overrides priced deployment identity")
    if params.get("n", 1) != 1 or params.get("best_of", 1) != 1:
        raise BudgetDenied("multiple completions need a separate cost bound")
    if any(params.get(key) for key in ("audio", "modalities", "web_search_options", "service_tier", "extra_body")):
        raise BudgetDenied("unsupported billing dimension")

    def reject_billing_options(value):
        if isinstance(value, dict):
            if any(value.get(key) for key in ("cache_control", "cache_creation", "web_search_options")):
                raise BudgetDenied("unsupported cache or server billing option")
            for child in value.values():
                reject_billing_options(child)
        elif isinstance(value, list):
            for child in value:
                reject_billing_options(child)

    for key in ("messages", "system", "tools", "functions"):
        reject_billing_options(params.get(key))
    for tool in params.get("tools", []) or []:
        if not isinstance(tool, dict) or tool.get("type", "function") not in {"function", "custom"}:
            raise BudgetDenied("unsupported server tool billing")

    def text_content(content):
        if content is None or isinstance(content, str):
            return True
        if not isinstance(content, list):
            return False
        return all(
            isinstance(block, dict)
            and block.get("type") in {"text", "tool_use", "tool_result"}
            and (block.get("type") != "tool_result" or text_content(block.get("content")))
            for block in content
        )

    if any(not text_content(message.get("content")) for message in params.get("messages", [])):
        raise BudgetDenied("multimodal billing bound unavailable")
    maximum = params.get("max_completion_tokens", params.get("max_tokens"))
    if (
        params.get("max_completion_tokens") is not None
        and params.get("max_tokens") is not None
        and params["max_completion_tokens"] != params["max_tokens"]
    ):
        raise BudgetDenied("conflicting output token limits")
    amount = price.bound(maximum)
    attempt = uuid4().hex
    ledger = controller.ledger
    ledger.reserve(
        attempt_id=attempt,
        request_id=request_id or uuid4().hex,
        provider=price.provider,
        deployment_id=price.deployment_id,
        model=price.model,
        price_snapshot=price.snapshot,
        price_details=price.snapshot_data(),
        budget_usd=controller._daily_budget,
        max_cost_usd=amount,
        task_type=task_type,
    )
    # Once dispatched, any ambiguous transport failure retains its reservation.
    ledger.dispatch(attempt)
    capture = None
    try:
        call = {**params, "max_retries": 0, "num_retries": 0}
        if sdk_usage and not params.get("stream"):
            capture = _ProviderUsageCapture(call)
            call = capture.params
        response = await transport(**call)
    except BaseException:
        ledger.mark_unknown(attempt, "transport_failed")
        raise
    finally:
        if capture is not None:
            capture.restore()
    if params.get("stream"):
        return AccountedStream(response, ledger, attempt, price)
    try:
        usage = (
            capture.usage
            if capture is not None
            else (usage_from(response) if usage_from else getattr(response, "usage", None))
        )
    except (ValueError, TypeError, KeyError):
        ledger.mark_unknown(attempt, "invalid_usage")
        return response
    settle_usage(ledger, attempt, price, usage)
    return response
