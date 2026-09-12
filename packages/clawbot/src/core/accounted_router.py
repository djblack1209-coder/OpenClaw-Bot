"""Narrow LiteLLM 1.90.2 adapter: retain Router selection/retries, meter each send.

The SDK's _acompletion dispatch seam is adapted locally because global callbacks
cannot guarantee a durable pre-send reservation. Contract tests exercise the real
Router retry/fallback machinery. Provider-internal retries and stream replay are
disabled; each Router retry enters this seam and gets its own attempt.
"""

import asyncio
from contextvars import ContextVar
from uuid import uuid4

import litellm
from litellm import Router

from src.core.accounted_completion import accounted_completion
from src.core.cost_control import get_cost_controller
from src.core.cost_ledger import LedgerError

_request = ContextVar("accounting_request", default=None)


class _AccountingStop(BaseException):
    """Internal sentinel bypasses SDK generic Exception retry/fallback handlers."""

    def __init__(self, error):
        self.error = error


class AccountedRouter(Router):
    async def acompletion(self, *args, **kwargs):
        token = _request.set(uuid4().hex)
        try:
            return await super().acompletion(*args, **kwargs)
        except _AccountingStop as stop:
            raise stop.error from None
        finally:
            _request.reset(token)

    async def _acompletion(self, model, messages, **kwargs):
        deployment = await self.async_get_available_deployment(
            model=model,
            messages=messages,
            specific_deployment=kwargs.pop("specific_deployment", None),
            request_kwargs=kwargs,
        )
        params = deployment["litellm_params"].copy()
        if params.get("silent_model"):
            from src.core.cost_ledger import BudgetDenied

            raise _AccountingStop(BudgetDenied("unmetered mirrored deployment disabled"))
        self._update_kwargs_with_deployment(deployment=deployment, kwargs=kwargs)
        # SDK clients can have independent retries; constructing the call with
        # zero retries also makes client selection use the same explicit limit.
        kwargs["max_retries"] = 0
        client = self._get_async_openai_model_client(deployment=deployment, kwargs=kwargs)
        call = {**params, "messages": messages, "caching": False, "client": client, **kwargs}
        semaphore = self._get_client(deployment=deployment, kwargs=kwargs, client_type="max_parallel_requests")

        async def send():
            await self.async_routing_strategy_pre_call_checks(
                deployment=deployment, logging_obj=kwargs.get("litellm_logging_obj"), parent_otel_span=None
            )
            self.total_calls[params["model"]] += 1
            try:
                response = await accounted_completion(
                    deployment=deployment,
                    controller=get_cost_controller(),
                    transport=litellm.acompletion,
                    sdk_usage=True,
                    params=call,
                    request_id=_request.get(),
                )
            except LedgerError as exc:
                raise _AccountingStop(exc) from exc
            except Exception as exc:
                self.fail_calls[params["model"]] += 1
                self._set_deployment_num_retries_on_exception(exc, deployment)
                self._set_failed_deployment_id_on_exception(exc, deployment)
                raise
            self.success_calls[params["model"]] += 1
            if isinstance(response, litellm.ModelResponse) and self._should_raise_content_policy_error(
                model=model, response=response, kwargs=kwargs
            ):
                raise litellm.ContentPolicyViolationError(
                    message="Response output was blocked.", model=model, llm_provider=""
                )
            return response

        if isinstance(semaphore, asyncio.Semaphore):
            async with semaphore:
                return await send()
        return await send()
