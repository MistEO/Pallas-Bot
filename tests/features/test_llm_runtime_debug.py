from __future__ import annotations

import asyncio

import pytest

from pallas.product.llm.runtime_debug import (
    append_request_snapshot,
    append_runtime_trace,
    build_replay_payload,
    load_runtime_debug_bundle,
)


def _raise_oserror(_message: str = "runtime debug unavailable") -> None:
    raise OSError(_message)


class _OpenFails:
    def open(self, *_args, **_kwargs):
        raise OSError("open failed")


class _WriteFailsHandle:
    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def write(self, _data: str) -> None:
        raise OSError("write failed")


class _WriteFailsPath:
    def open(self, *_args, **_kwargs) -> _WriteFailsHandle:
        return _WriteFailsHandle()


def _snapshot_kwargs() -> dict:
    return {
        "request_id": "req-fail",
        "task": "llm_chat",
        "system_prompt": "你是牛牛",
        "messages": [{"role": "user", "content": "你好"}],
        "metadata": {"task": "llm_chat", "bot_id": 1, "group_id": 2},
    }


def test_runtime_debug_snapshot_and_trace_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "pallas.product.llm.runtime_debug.runtime_debug_dir",
        lambda: tmp_path,
    )
    snapshot_id = append_request_snapshot(
        request_id="req-1",
        task="llm_chat",
        system_prompt="你是牛牛",
        messages=[{"role": "user", "content": "你好"}],
        metadata={
            "task": "llm_chat",
            "persona_shaping_active": True,
            "persona_affect_block": "【本轮牛格塑形】\n- 像顺口接话",
            "variation_hint": "【本轮表达去重】\n- 最近解释偏满",
            "agent_stage_plan": ["plan", "tool_loop", "generate"],
            "tool_catalog": {"version": "tool_catalog/v1"},
            "hybrid_retrieval_trace": {
                "sources": ["memory", "knowledge"],
                "memory": {"hit_count": 1},
                "knowledge": {"hit_count": 2},
                "relationship": {"hit_count": 0},
            },
        },
    )
    append_runtime_trace(
        request_id="req-1",
        trace={"request_snapshot_id": snapshot_id, "version": "agent_trace/v1", "tool_call_count": 1},
    )
    bundle = load_runtime_debug_bundle(request_id="req-1")
    assert bundle["snapshot"]["request_snapshot_id"] == snapshot_id
    assert bundle["snapshot"]["stage_inputs"]["plan"]["agent_stage_plan"] == ["plan", "tool_loop", "generate"]
    assert bundle["snapshot"]["stage_inputs"]["retrieve"]["sources"] == ["memory", "knowledge"]
    assert bundle["persona_shaping"]["persona_shaping_active"] is True
    assert bundle["persona_shaping"]["lines"] == ["像顺口接话"]
    assert bundle["trace"]["tool_call_count"] == 1
    assert bundle["tool_trace"]["tool_call_count"] == 1
    assert bundle["tool_trace"]["tool_schema_count"] >= 0
    replay = build_replay_payload(request_id="req-1")
    assert replay["request_snapshot_id"] == snapshot_id
    assert replay["mode"] == "mock_tools"
    assert replay["stage_inputs"]["retrieve"]["memory"]["hit_count"] == 1


def test_append_request_snapshot_returns_id_when_dir_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("pallas.product.llm.runtime_debug.runtime_debug_dir", lambda: _raise_oserror())
    snapshot_id = append_request_snapshot(**_snapshot_kwargs())
    assert snapshot_id.startswith("reqsnap_")


def test_append_request_snapshot_returns_id_when_open_fails(monkeypatch) -> None:
    monkeypatch.setattr("pallas.product.llm.runtime_debug.request_snapshot_path", lambda: _OpenFails())
    snapshot_id = append_request_snapshot(**_snapshot_kwargs())
    assert snapshot_id.startswith("reqsnap_")


def test_append_request_snapshot_returns_id_when_write_fails(monkeypatch) -> None:
    monkeypatch.setattr("pallas.product.llm.runtime_debug.request_snapshot_path", lambda: _WriteFailsPath())
    snapshot_id = append_request_snapshot(**_snapshot_kwargs())
    assert snapshot_id.startswith("reqsnap_")


def test_append_request_snapshot_returns_id_when_serialization_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("pallas.product.llm.runtime_debug.runtime_debug_dir", lambda: tmp_path)
    kwargs = _snapshot_kwargs()
    kwargs["metadata"]["tool_catalog"] = {"tools": [], "unserializable": {1, 2}}
    snapshot_id = append_request_snapshot(**kwargs)
    assert snapshot_id.startswith("reqsnap_")


def test_append_request_snapshot_returns_id_when_stage_inputs_fail(monkeypatch) -> None:
    def broken_stage_inputs(**_kwargs):
        raise ValueError("stage inputs failed")

    monkeypatch.setattr("pallas.product.llm.runtime_debug.build_stage_inputs", broken_stage_inputs)
    snapshot_id = append_request_snapshot(**_snapshot_kwargs())
    assert snapshot_id.startswith("reqsnap_")


def test_append_runtime_trace_swallows_write_failure(monkeypatch) -> None:
    monkeypatch.setattr("pallas.product.llm.runtime_debug.runtime_debug_dir", lambda: _raise_oserror())
    append_runtime_trace(request_id="req-trace", trace={"status": "success"})


def test_snapshot_failure_logs_rate_limited(monkeypatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(
        "pallas.product.llm.runtime_debug.log_rate_limited",
        lambda *args, **_kwargs: calls.append(args),
    )
    monkeypatch.setattr("pallas.product.llm.runtime_debug.runtime_debug_dir", lambda: _raise_oserror())
    append_request_snapshot(**_snapshot_kwargs())
    assert calls
    assert "req-fail" in calls[0]
    assert "OSError" in calls[0]


def test_append_request_snapshot_does_not_swallow_base_exception(monkeypatch) -> None:
    def broken_stage_inputs(**_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("pallas.product.llm.runtime_debug.build_stage_inputs", broken_stage_inputs)
    with pytest.raises(KeyboardInterrupt):
        append_request_snapshot(**_snapshot_kwargs())


def test_append_runtime_trace_does_not_swallow_cancelled(monkeypatch) -> None:
    def cancelled_path():
        raise asyncio.CancelledError

    monkeypatch.setattr("pallas.product.llm.runtime_debug.runtime_trace_path", cancelled_path)
    with pytest.raises(asyncio.CancelledError):
        append_runtime_trace(request_id="req-cancel", trace={})
