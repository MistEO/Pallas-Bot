"""provider_client 单轮预算：真实 HTTP 计数、deadline 协作截止与取消语义。"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from pallas.product.llm.provider_client import LlmProviderError, complete_chat_message
from pallas.product.llm.turn_budget import LlmTurnBudget, LlmTurnBudgetExceeded


class _OkResponse:
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b""
    text = ""

    def json(self) -> dict:
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}


class _UnauthorizedResponse:
    status_code = 401
    headers = {}
    content = b""
    text = "unauthorized"

    def json(self) -> dict:
        return {}


def _allow_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pallas.product.llm.availability.llm_calls_enabled", lambda cfg=None: True)
    monkeypatch.setattr("pallas.product.llm.providers_store.find_provider", lambda _pid: None)


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(llm_chat_enabled=True, llm_api_key="sk", llm_model="m", chat_timeout_sec=10.0)


def _stub_client(monkeypatch: pytest.MonkeyPatch, client: object) -> None:
    async def fake_client():
        return client

    monkeypatch.setattr("pallas.product.llm.provider_client.get_llm_shared_httpx_client", fake_client)


@pytest.mark.asyncio
async def test_http_cap_counts_real_posts_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    posts: list[float] = []

    class FakeClient:
        async def post(self, *_args, **_kwargs):
            posts.append(float(_kwargs["timeout"].read))
            return _OkResponse()

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 60, max_http_attempts=1)

    first = await complete_chat_message(
        [{"role": "user", "content": "hi"}],
        model="m",
        base_url="https://x/v1",
        api_key="sk",
        cfg=_cfg(),
        turn_budget=budget,
    )
    assert first["content"] == "ok"
    assert budget.used_http_attempts == 1

    with pytest.raises(LlmTurnBudgetExceeded) as exc:
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            base_url="https://x/v1",
            api_key="sk",
            cfg=_cfg(),
            turn_budget=budget,
        )
    assert exc.value.reason == "http_attempts_exhausted"
    assert len(posts) == 1


@pytest.mark.asyncio
async def test_httpx_timeout_clamped_to_remaining(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[float] = []

    class FakeClient:
        async def post(self, *_args, **_kwargs):
            seen.append(float(_kwargs["timeout"].read))
            return _OkResponse()

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 3, max_http_attempts=6)

    await complete_chat_message(
        [{"role": "user", "content": "hi"}],
        model="m",
        base_url="https://x/v1",
        api_key="sk",
        cfg=_cfg(),
        turn_budget=budget,
    )
    assert seen
    assert seen[0] <= 3.0


@pytest.mark.asyncio
async def test_deadline_cancels_slow_provider_body(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        async def post(self, *_args, **_kwargs):
            await asyncio.sleep(30)
            return _OkResponse()

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 0.05, max_http_attempts=6)

    with pytest.raises(LlmTurnBudgetExceeded) as exc:
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            base_url="https://x/v1",
            api_key="sk",
            cfg=_cfg(),
            turn_budget=budget,
        )
    assert exc.value.reason == "deadline_exceeded"


@pytest.mark.asyncio
async def test_internal_timeout_error_not_misjudged(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        async def post(self, *_args, **_kwargs):
            raise TimeoutError("inner provider timeout")

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 60, max_http_attempts=6)

    with pytest.raises(TimeoutError):
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            base_url="https://x/v1",
            api_key="sk",
            cfg=_cfg(),
            turn_budget=budget,
        )


@pytest.mark.asyncio
async def test_external_cancellation_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()

    class FakeClient:
        async def post(self, *_args, **_kwargs):
            started.set()
            await asyncio.sleep(30)
            return _OkResponse()

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 60, max_http_attempts=6)

    task = asyncio.create_task(
        complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            base_url="https://x/v1",
            api_key="sk",
            cfg=_cfg(),
            turn_budget=budget,
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_preparation_consumes_deadline_without_http_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.product.llm.providers_store import ResolvedLlmEndpoint

    monkeypatch.setattr(
        "pallas.product.llm.providers_store.resolve_endpoint_candidates_for_task",
        lambda _task: [
            ResolvedLlmEndpoint(
                provider_id="p1",
                base_url="https://x/v1",
                api_key="sk",
                model="m",
                api_keys=("sk",),
            )
        ],
    )
    _allow_llm(monkeypatch)
    monkeypatch.setattr("pallas.product.llm.provider_client.provider_daily_budget_ok", lambda _pid: True)

    async def slow_prepare(_messages, _endpoint, _model):
        await asyncio.sleep(30)
        return _messages

    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 0.05, max_http_attempts=6)
    with pytest.raises(LlmTurnBudgetExceeded):
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            task="llm_chat",
            cfg=_cfg(),
            prepare_candidate_messages=slow_prepare,
            turn_budget=budget,
        )
    assert budget.used_http_attempts == 0


class _BadRequestResponse:
    status_code = 400
    headers = {}
    content = b""
    text = "tool_choice does not support required"

    def json(self) -> dict:
        return {}


@pytest.mark.asyncio
async def test_deadline_anchored_to_started_at_and_not_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    import pallas.product.llm.turn_budget as tb

    clock = {"now": 1000.0}
    monkeypatch.setattr(tb, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    posts: list[str] = []

    class FakeClient:
        async def post(self, *_args, **_kwargs):
            posts.append("post")
            return _OkResponse()

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    cfg = SimpleNamespace(
        llm_chat_enabled=True,
        llm_api_key="sk",
        llm_model="m",
        chat_timeout_sec=10.0,
        llm_chat_turn_timeout_sec=60.0,
        llm_chat_turn_max_http_attempts=6,
    )
    budget = tb.new_llm_chat_turn_budget(cfg, started_at=clock["now"])
    assert budget.deadline_monotonic == 1060.0

    await complete_chat_message(
        [{"role": "user", "content": "hi"}],
        model="m",
        base_url="https://x/v1",
        api_key="sk",
        cfg=cfg,
        turn_budget=budget,
    )
    clock["now"] = 1100.0
    assert budget.deadline_monotonic == 1060.0
    with pytest.raises(LlmTurnBudgetExceeded) as exc:
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            base_url="https://x/v1",
            api_key="sk",
            cfg=cfg,
            turn_budget=budget,
        )
    assert exc.value.reason == "deadline_exceeded"
    assert posts == ["post"]


@pytest.mark.asyncio
async def test_required_to_auto_retry_consumes_shared_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.product.llm.provider_client import clear_tool_choice_compatibility_cache

    posts: list[str] = []

    class FakeClient:
        async def post(self, *_args, **_kwargs):
            posts.append("post")
            return _BadRequestResponse()

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    clear_tool_choice_compatibility_cache()
    tools = [{"type": "function", "function": {"name": "lookup"}}]

    two = LlmTurnBudget(deadline_monotonic=time.monotonic() + 60, max_http_attempts=2)
    with pytest.raises(LlmProviderError):
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            base_url="https://x/v1",
            api_key="sk",
            cfg=_cfg(),
            options={"tool_choice": "required"},
            tools=tools,
            turn_budget=two,
        )
    assert posts == ["post", "post"]
    clear_tool_choice_compatibility_cache()

    posts.clear()
    one = LlmTurnBudget(deadline_monotonic=time.monotonic() + 60, max_http_attempts=1)
    with pytest.raises(LlmTurnBudgetExceeded):
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            base_url="https://x/v1",
            api_key="sk",
            cfg=_cfg(),
            options={"tool_choice": "required"},
            tools=tools,
            turn_budget=one,
        )
    assert posts == ["post"]
    clear_tool_choice_compatibility_cache()


@pytest.mark.asyncio
async def test_cross_provider_failover_consumes_shared_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.product.llm.providers_store import ResolvedLlmEndpoint

    posts: list[str] = []

    class FakeClient:
        async def post(self, *_args, **_kwargs):
            posts.append("post")
            return _UnauthorizedResponse()

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    monkeypatch.setattr("pallas.product.llm.provider_client.provider_daily_budget_ok", lambda _pid: True)
    monkeypatch.setattr(
        "pallas.product.llm.providers_store.resolve_endpoint_candidates_for_task",
        lambda _task: [
            ResolvedLlmEndpoint(provider_id="p1", base_url="https://a/v1", api_key="k1", model="m", api_keys=("k1",)),
            ResolvedLlmEndpoint(provider_id="p2", base_url="https://b/v1", api_key="k2", model="m", api_keys=("k2",)),
        ],
    )
    one = LlmTurnBudget(deadline_monotonic=time.monotonic() + 60, max_http_attempts=1)
    with pytest.raises(LlmTurnBudgetExceeded):
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            task="llm_chat",
            cfg=_cfg(),
            turn_budget=one,
        )
    assert posts == ["post"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_method",
    ["chat_completions", "responses", "anthropic_messages", "ollama_chat"],
)
async def test_all_protocols_claim_shared_cap(
    monkeypatch: pytest.MonkeyPatch,
    request_method: str,
) -> None:
    class FakeClient:
        async def post(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 60, max_http_attempts=1)

    with pytest.raises(RuntimeError):
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            base_url="https://x/v1",
            api_key="sk",
            request_method=request_method,
            cfg=_cfg(),
            turn_budget=budget,
        )
    assert budget.used_http_attempts == 1


@pytest.mark.asyncio
async def test_budget_not_swallowed_by_key_failover(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.product.llm.providers_store import ResolvedLlmEndpoint

    posts: list[str] = []

    class FakeClient:
        async def post(self, *_args, **_kwargs):
            posts.append("post")
            return _UnauthorizedResponse()

    _stub_client(monkeypatch, FakeClient())
    _allow_llm(monkeypatch)
    monkeypatch.setattr("pallas.product.llm.provider_client.provider_daily_budget_ok", lambda _pid: True)
    monkeypatch.setattr(
        "pallas.product.llm.providers_store.resolve_endpoint_candidates_for_task",
        lambda _task: [
            ResolvedLlmEndpoint(
                provider_id="p1",
                base_url="https://x/v1",
                api_key="sk-1",
                model="m",
                api_keys=("sk-1", "sk-2"),
            )
        ],
    )
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 60, max_http_attempts=1)

    with pytest.raises(LlmTurnBudgetExceeded):
        await complete_chat_message(
            [{"role": "user", "content": "hi"}],
            model="m",
            task="llm_chat",
            cfg=_cfg(),
            turn_budget=budget,
        )
    assert posts == ["post"]
