"""Ollama 原生 /api/chat：思考内容解析与 think 参数行为。"""

from __future__ import annotations

import pytest

from pallas.product.llm.provider_client import _post_ollama_chat
from pallas.product.llm.provider_client.client import _ollama_think_value


def test_ollama_think_value_disable_omits_think_flag() -> None:
    # ollama.com 的 think: false 会把思考内联进 content，宁可不传
    assert _ollama_think_value({"model_effort": "disable"}) is None
    assert _ollama_think_value({"model_effort": "enable"}) is True
    assert _ollama_think_value({"model_effort": "high"}) == "high"
    assert _ollama_think_value({}) is None


@pytest.mark.asyncio
async def test_post_ollama_chat_parses_thinking_into_reasoning_content(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {
                "message": {
                    "role": "assistant",
                    "content": "2",
                    "thinking": "The user asks 1+1. Answer with a number.",
                },
                "done": True,
            }

    class FakeClient:
        def __init__(self) -> None:
            self.payloads: list[dict] = []

        async def post(self, *_args, json=None, **_kwargs):
            self.payloads.append(json)
            return FakeResponse()

    fake_client_instance = FakeClient()

    async def fake_client():
        return fake_client_instance

    monkeypatch.setattr("pallas.product.llm.provider_client.get_llm_shared_httpx_client", fake_client)
    result = await _post_ollama_chat(
        [{"role": "user", "content": "1+1等于几？只回答数字"}],
        base_url="https://ollama.com",
        api_key="sk-test",
        model="glm-5.3-flash",
        options={"model_effort": "disable"},
        tools=None,
        timeout_sec=60,
    )
    assert result["content"] == "2"
    assert result["reasoning_content"] == "The user asks 1+1. Answer with a number."
    assert "thinking" not in result
    assert "reasoning_effort" not in fake_client_instance.payloads[0]
