from __future__ import annotations

from typing import Any

import pytest

from pallas.product.llm.config import LlmConfig
from pallas.product.llm.tool_loop import complete_with_tool_loop, tool_names_from_schemas
from pallas.product.llm.tools.activation_cache import activated_tool_names, clear_activation_cache_for_tests
from pallas.product.llm.tools.bootstrap import reset_llm_tools_bootstrap_for_tests
from pallas.product.llm.tools.contracts import ToolCapability
from pallas.product.llm.tools.discovery import TOOLS_FIND_NAME, register_discovery_tools
from pallas.product.llm.tools.registry import LlmToolSource, LlmToolSpec, clear_tool_registry, register_tool


@pytest.fixture(autouse=True)
def reset_tools() -> None:
    reset_llm_tools_bootstrap_for_tests()
    clear_activation_cache_for_tests()
    yield
    reset_llm_tools_bootstrap_for_tests()
    clear_activation_cache_for_tests()


@pytest.mark.asyncio
async def test_tools_find_activates_deferred_tool_for_next_round(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_tool_registry()
    register_discovery_tools()

    async def deferred_handler(args: dict, ctx=None):
        del args, ctx
        return {"ok": True, "result": {"echo": "pong"}}

    register_tool(
        LlmToolSpec(
            name="demo.deferred_ping",
            description="冷门演示工具",
            parameters={"type": "object", "properties": {}},
            domains=frozenset({"demo"}),
            handler=deferred_handler,
            source=LlmToolSource.BUILTIN,
            capabilities=frozenset({ToolCapability.READ_ONLY.value}),
            hints=frozenset({"冷门演示"}),
            visibility="deferred",
        )
    )

    calls = {"n": 0}
    second_tools: list[Any] = []

    async def fake_complete(messages, *, model, options=None, tools=None, cfg=None, **_kwargs):
        del messages, model, options, cfg
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": TOOLS_FIND_NAME, "arguments": '{"query":"冷门演示"}'},
                    }
                ],
            }
        if calls["n"] == 2:
            second_tools.append(tools)
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {"name": "demo.deferred_ping", "arguments": "{}"},
                    }
                ],
            }
        return {"role": "assistant", "content": "好了"}

    monkeypatch.setattr("pallas.product.llm.tool_loop.complete_chat_message", fake_complete)

    content, assistant = await complete_with_tool_loop(
        system_prompt="sys",
        messages=[{"role": "user", "content": "找冷门演示"}],
        metadata={
            "task": "llm_chat",
            "tools_enabled": True,
            "tool_schemas": [{"type": "function", "function": {"name": TOOLS_FIND_NAME}}],
            "bot_id": 1,
            "group_id": 2,
            "user_id": 3,
        },
        cfg=LlmConfig(
            llm_base_url="http://example.test/v1",
            llm_model="demo",
            llm_tools_enabled=True,
            llm_tools_max_rounds=4,
        ),
    )

    assert content == "好了"
    names = set(tool_names_from_schemas(second_tools[0] or [])) if second_tools else set()
    assert "demo__deferred_ping" in names or "demo.deferred_ping" in names
    assert "demo.deferred_ping" in ((assistant.get("_agent_trace") or {}).get("activated_tools") or [])
    assert "demo.deferred_ping" in activated_tool_names(1, 2, 3)


@pytest.mark.asyncio
async def test_social_required_tool_fails_closed_without_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_complete(messages, *, model, options=None, tools=None, cfg=None, **_kwargs):
        del messages, model, options, tools, cfg
        return {"role": "assistant", "content": "我没有主人"}

    monkeypatch.setattr("pallas.product.llm.tool_loop.complete_chat_message", fake_complete)

    content, assistant = await complete_with_tool_loop(
        system_prompt="sys",
        messages=[{"role": "user", "content": "你的主人是谁"}],
        metadata={
            "task": "llm_chat",
            "tools_enabled": True,
            "tool_choice_prefer": "required",
            "tool_schemas": [{"type": "function", "function": {"name": "social__master__info"}}],
            "bot_id": 1,
            "group_id": 2,
            "user_id": 3,
        },
        cfg=LlmConfig(
            llm_base_url="http://example.test/v1",
            llm_model="demo",
            llm_tools_enabled=True,
            llm_tools_max_rounds=2,
        ),
    )

    assert content == "群内信息暂时查不了，稍后再试。"
    assert assistant["_agent_trace"]["status"] == "required_tool_missing"


@pytest.mark.asyncio
async def test_social_required_tool_fails_closed_after_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_complete(messages, *, model, options=None, tools=None, cfg=None, **_kwargs):
        del messages, model, options, tools, cfg
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "social-1",
                    "type": "function",
                    "function": {"name": "social__master__info", "arguments": "{}"},
                }
            ],
        }

    async def fake_execute(*_args, **_kwargs):
        return {"ok": False, "error": "bot_unavailable"}

    monkeypatch.setattr("pallas.product.llm.tool_loop.complete_chat_message", fake_complete)
    monkeypatch.setattr("pallas.product.llm.tool_loop.execute_tool_async", fake_execute)

    content, assistant = await complete_with_tool_loop(
        system_prompt="sys",
        messages=[{"role": "user", "content": "你的主人是谁"}],
        metadata={
            "task": "llm_chat",
            "tools_enabled": True,
            "tool_choice_prefer": "required",
            "tool_schemas": [{"type": "function", "function": {"name": "social__master__info"}}],
            "bot_id": 1,
            "group_id": 2,
            "user_id": 3,
        },
        cfg=LlmConfig(
            llm_base_url="http://example.test/v1",
            llm_model="demo",
            llm_tools_enabled=True,
            llm_tools_max_rounds=2,
        ),
    )

    assert content == "群内信息暂时查不了，稍后再试。"
    assert assistant["_agent_trace"]["status"] == "required_tool_failed"


@pytest.mark.asyncio
async def test_social_required_tool_rejects_unrelated_successful_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    async def fake_complete(messages, *, model, options=None, tools=None, cfg=None, **_kwargs):
        del messages, model, options, tools, cfg
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "other-1",
                        "type": "function",
                        "function": {"name": "web__search", "arguments": "{}"},
                    }
                ],
            }
        return {"role": "assistant", "content": "我没有主人"}

    async def fake_execute(*_args, **_kwargs):
        return {"ok": True, "result": {"summary": "web search completed"}}

    monkeypatch.setattr("pallas.product.llm.tool_loop.complete_chat_message", fake_complete)
    monkeypatch.setattr("pallas.product.llm.tool_loop.execute_tool_async", fake_execute)

    content, assistant = await complete_with_tool_loop(
        system_prompt="sys",
        messages=[{"role": "user", "content": "你的主人是谁"}],
        metadata={
            "task": "llm_chat",
            "tools_enabled": True,
            "tool_choice_prefer": "required",
            "tool_schemas": [{"type": "function", "function": {"name": "social__master__info"}}],
            "bot_id": 1,
            "group_id": 2,
            "user_id": 3,
        },
        cfg=LlmConfig(
            llm_base_url="http://example.test/v1",
            llm_model="demo",
            llm_tools_enabled=True,
            llm_tools_max_rounds=2,
        ),
    )

    assert content == "群内信息暂时查不了，稍后再试。"
    assert assistant["_agent_trace"]["status"] == "required_tool_missing"


@pytest.mark.asyncio
async def test_tool_loop_rejects_tool_not_in_current_schemas(monkeypatch: pytest.MonkeyPatch) -> None:
    """模型杜撰未在本轮开放集合内的工具：不执行 handler，合法工具仍执行。"""
    clear_tool_registry()
    executed: list[str] = []

    async def handler(args: dict, ctx=None):
        del args, ctx
        executed.append("ran")
        return {"ok": True, "result": {"echo": "pong"}}

    for name in ("demo.legit", "demo.hallucinated"):
        register_tool(
            LlmToolSpec(
                name=name,
                description=name,
                parameters={"type": "object", "properties": {}},
                domains=frozenset({"demo"}),
                handler=handler,
                source=LlmToolSource.BUILTIN,
                capabilities=frozenset({ToolCapability.READ_ONLY.value}),
            )
        )

    calls = {"n": 0}

    async def fake_complete(messages, *, model, options=None, tools=None, cfg=None, **_kwargs):
        del messages, model, options, tools, cfg
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "h1",
                        "type": "function",
                        "function": {"name": "demo__hallucinated", "arguments": "{}"},
                    }
                ],
            }
        if calls["n"] == 2:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "l1", "type": "function", "function": {"name": "demo__legit", "arguments": "{}"}},
                ],
            }
        return {"role": "assistant", "content": "好了"}

    monkeypatch.setattr("pallas.product.llm.tool_loop.complete_chat_message", fake_complete)

    content, _assistant = await complete_with_tool_loop(
        system_prompt="sys",
        messages=[{"role": "user", "content": "试试"}],
        metadata={
            "task": "llm_chat",
            "tools_enabled": True,
            "tool_schemas": [{"type": "function", "function": {"name": "demo__legit"}}],
            "bot_id": 1,
            "group_id": 2,
            "user_id": 3,
        },
        cfg=LlmConfig(
            llm_base_url="http://example.test/v1",
            llm_model="demo",
            llm_tools_enabled=True,
            llm_tools_max_rounds=4,
        ),
    )

    assert content == "好了"
    assert executed == ["ran"]


@pytest.mark.asyncio
async def test_same_batch_discovery_rejects_activated_tool_until_next_round(monkeypatch: pytest.MonkeyPatch) -> None:
    """同批 tools.find 激活的 deferred：本批冻结集合内拒绝，下一轮 schema 扩展后才可执行。"""
    clear_tool_registry()
    register_discovery_tools()

    executed: list[str] = []

    async def deferred_handler(args: dict, ctx=None):
        del args, ctx
        executed.append("deferred")
        return {"ok": True, "result": {"echo": "pong"}}

    register_tool(
        LlmToolSpec(
            name="demo.deferred_ping",
            description="冷门演示工具",
            parameters={"type": "object", "properties": {}},
            domains=frozenset({"demo"}),
            handler=deferred_handler,
            source=LlmToolSource.BUILTIN,
            capabilities=frozenset({ToolCapability.READ_ONLY.value}),
            hints=frozenset({"冷门演示"}),
            visibility="deferred",
        )
    )

    calls = {"n": 0}

    async def fake_complete(messages, *, model, options=None, tools=None, cfg=None, **_kwargs):
        del messages, model, options, cfg
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "f1",
                        "type": "function",
                        "function": {"name": TOOLS_FIND_NAME, "arguments": '{"query":"冷门演示"}'},
                    },
                    {
                        "id": "d1",
                        "type": "function",
                        "function": {"name": "demo.deferred_ping", "arguments": "{}"},
                    },
                ],
            }
        if calls["n"] == 2:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "d2",
                        "type": "function",
                        "function": {"name": "demo.deferred_ping", "arguments": '{"round":2}'},
                    },
                ],
            }
        return {"role": "assistant", "content": "好了"}

    monkeypatch.setattr("pallas.product.llm.tool_loop.complete_chat_message", fake_complete)

    content, _assistant = await complete_with_tool_loop(
        system_prompt="sys",
        messages=[{"role": "user", "content": "找冷门演示"}],
        metadata={
            "task": "llm_chat",
            "tools_enabled": True,
            "tool_schemas": [{"type": "function", "function": {"name": TOOLS_FIND_NAME}}],
            "bot_id": 1,
            "group_id": 2,
            "user_id": 3,
        },
        cfg=LlmConfig(
            llm_base_url="http://example.test/v1",
            llm_model="demo",
            llm_tools_enabled=True,
            llm_tools_max_rounds=4,
        ),
    )

    assert content == "好了"
    assert executed == ["deferred"]


@pytest.mark.asyncio
async def test_auto_injected_chat_reply_rejected_same_round_allowed_next(monkeypatch: pytest.MonkeyPatch) -> None:
    """副作用成功后同轮自动注入的 chat.reply 本批拒绝，下一轮才可执行。"""
    clear_tool_registry()

    async def side_effect_handler(args: dict, ctx=None):
        del args, ctx
        return {"ok": True, "result": {"summary": "done"}}

    register_tool(
        LlmToolSpec(
            name="demo.side_effect",
            description="side effect demo",
            parameters={"type": "object", "properties": {}},
            domains=frozenset({"demo"}),
            handler=side_effect_handler,
            source=LlmToolSource.BUILTIN,
            capabilities=frozenset({ToolCapability.SIDE_EFFECTING.value}),
        )
    )

    from pallas.product.llm.tools import reply as reply_mod

    reply_calls: list[dict[str, Any]] = []

    async def fake_reply(args: dict, ctx=None):
        del ctx
        reply_calls.append(dict(args))
        return {"ok": True, "result": {"text": str(args.get("text") or ""), "visible_reply": True}}

    monkeypatch.setattr(reply_mod, "handle_chat_reply", fake_reply)
    reply_mod.register_reply_tools()

    calls = {"n": 0}

    async def fake_complete(messages, *, model, options=None, tools=None, cfg=None, **_kwargs):
        del messages, model, options, cfg
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "s1", "type": "function", "function": {"name": "demo.side_effect", "arguments": "{}"}},
                    {
                        "id": "r1",
                        "type": "function",
                        "function": {"name": "chat.reply", "arguments": '{"text":"不该这轮发"}'},
                    },
                ],
            }
        if calls["n"] == 2:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "r2",
                        "type": "function",
                        "function": {"name": "chat.reply", "arguments": '{"text":"真实回复"}'},
                    },
                ],
            }
        return {"role": "assistant", "content": ""}

    monkeypatch.setattr("pallas.product.llm.tool_loop.complete_chat_message", fake_complete)

    content, _assistant = await complete_with_tool_loop(
        system_prompt="sys",
        messages=[{"role": "user", "content": "做点事"}],
        metadata={
            "task": "llm_chat",
            "tools_enabled": True,
            "tool_schemas": [{"type": "function", "function": {"name": "demo.side_effect"}}],
            "bot_id": 1,
            "group_id": 2,
            "user_id": 3,
        },
        cfg=LlmConfig(
            llm_base_url="http://example.test/v1",
            llm_model="demo",
            llm_tools_enabled=True,
            llm_tools_max_rounds=4,
        ),
    )

    assert reply_calls == [{"text": "真实回复"}]
    assert content == "真实回复"


@pytest.mark.asyncio
async def test_provider_schema_snapshot_isolated_from_metadata_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    """等待 provider 期间外部追加/改写 metadata schema，不影响本次请求参数与开放集合。"""
    clear_tool_registry()
    executed: list[str] = []

    async def allowed_handler(args: dict, ctx=None):
        del args, ctx
        executed.append("allowed")
        return {"ok": True, "result": {"echo": "allowed"}}

    async def hidden_handler(args: dict, ctx=None):
        del args, ctx
        executed.append("hidden")
        return {"ok": True, "result": {"echo": "hidden"}}

    for name, handler in (("demo.allowed", allowed_handler), ("demo.hidden", hidden_handler)):
        register_tool(
            LlmToolSpec(
                name=name,
                description=name,
                parameters={"type": "object", "properties": {}},
                domains=frozenset({"demo"}),
                handler=handler,
                source=LlmToolSource.BUILTIN,
                capabilities=frozenset({ToolCapability.READ_ONLY.value}),
            )
        )

    original_schema = {
        "type": "function",
        "function": {"name": "demo.allowed", "parameters": {"type": "object", "properties": {}}},
    }
    metadata = {
        "task": "llm_chat",
        "tools_enabled": True,
        "tool_schemas": [
            {
                "type": "function",
                "function": {"name": "demo.allowed", "parameters": {"type": "object", "properties": {}}},
            }
        ],
        "bot_id": 1,
        "group_id": 2,
        "user_id": 3,
    }

    captured_tools: list[Any] = []

    async def fake_complete(messages, *, model, options=None, tools=None, cfg=None, **_kwargs):
        del messages, model, options, cfg
        captured_tools.append(tools)
        if len(captured_tools) == 1:
            # 模拟等待 provider 期间外部追加/改写 metadata schema（含嵌套字段）
            metadata["tool_schemas"].append({
                "type": "function",
                "function": {"name": "demo.hidden", "parameters": {"type": "object", "properties": {}}},
            })
            metadata["tool_schemas"][0]["function"]["name"] = "demo.hidden"
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "h1", "type": "function", "function": {"name": "demo.hidden", "arguments": "{}"}},
                ],
            }
        return {"role": "assistant", "content": "好了"}

    monkeypatch.setattr("pallas.product.llm.tool_loop.complete_chat_message", fake_complete)

    content, assistant = await complete_with_tool_loop(
        system_prompt="sys",
        messages=[{"role": "user", "content": "试试"}],
        metadata=metadata,
        cfg=LlmConfig(
            llm_base_url="http://example.test/v1",
            llm_model="demo",
            llm_tools_enabled=True,
            llm_tools_max_rounds=4,
        ),
    )

    assert captured_tools[0] == [original_schema]
    assert executed == []
    assert assistant["_agent_trace"]["rounds"][0]["calls"][0]["error"] == "tool_not_offered"
    assert content == "好了"
