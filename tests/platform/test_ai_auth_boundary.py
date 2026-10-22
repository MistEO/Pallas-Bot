"""Bot 内部鉴权/边界安全回归：internal header、AI Bearer、ASGI 边界、任务绑定与终态。"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient

from pallas.core.platform.ai_callback import ai_bearer, internal_auth
from pallas.core.platform.ai_callback.boundary_guard import AiBoundaryGuard
from pallas.core.platform.ai_callback.internal_auth import (
    INTERNAL_TOKEN_HEADER,
    PURPOSE_AI_TASK_REGISTRATION,
)


@pytest.fixture(autouse=True)
def isolate_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr("pallas.core.foundation.paths.DATA_ROOT", tmp_path)
    return tmp_path


def _now() -> float:
    import time

    return time.time()


def _write_ai_extension(tmp_path, token: str) -> None:
    path = tmp_path / "pb_webui"
    path.mkdir(parents=True, exist_ok=True)
    (path / "ai_extension.json").write_text(json.dumps({"token": token}), encoding="utf-8")


# ---------- internal_auth ----------


def test_internal_token_roundtrip_and_purpose_separation(tmp_path) -> None:
    token = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    assert token
    assert internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, token)
    assert not internal_auth.verify_internal_token("other-purpose", token)
    assert not internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, "")
    assert not internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, "deadbeef")


def test_internal_token_rotation_rejects_old(tmp_path) -> None:
    old = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    internal_auth.session_secret_path().write_bytes(b"x" * 32)
    new = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    assert old != new
    assert not internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, old)
    assert internal_auth.verify_internal_token(PURPOSE_AI_TASK_REGISTRATION, new)


# ---------- ai_bearer ----------


def test_ai_bearer_verify_and_empty_config(tmp_path) -> None:
    assert ai_bearer.resolve_ai_bearer_token() == ""
    assert not ai_bearer.verify_ai_bearer("Bearer anything")
    _write_ai_extension(tmp_path, "s3cret")
    assert ai_bearer.verify_ai_bearer("Bearer s3cret")
    assert not ai_bearer.verify_ai_bearer("s3cret")
    assert not ai_bearer.verify_ai_bearer("Bearer other")
    assert ai_bearer.ai_bearer_headers() == {"Authorization": "Bearer s3cret"}


# ---------- boundary guard ----------


def _guard_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AiBoundaryGuard)

    @app.post("/callback/{task_id}")
    async def _cb(task_id: str) -> dict:
        return {"ok": True}

    @app.post("/pallas/api/internal/ai/tasks/{task_id}")
    async def _reg(task_id: str) -> dict:
        return {"ok": True}

    @app.post("/pallas/api/internal/llm/tools/execute")
    async def _tools() -> dict:
        return {"ok": True}

    return app


def test_guard_installer_wires_middleware(tmp_path) -> None:
    from pallas.core.platform.ai_callback.boundary_guard import install_ai_boundary_guard

    app = FastAPI()

    @app.post("/callback/{task_id}")
    async def _cb(task_id: str) -> dict:
        return {"ok": True}

    install_ai_boundary_guard(app)
    install_ai_boundary_guard(app)  # idempotent
    _write_ai_extension(tmp_path, "tok")
    client = TestClient(app)
    assert client.post("/callback/t1", data={"status": "success"}).status_code == 401
    assert (
        client.post("/callback/t1", data={"status": "success"}, headers={"Authorization": "Bearer tok"}).status_code
        == 200
    )


def test_guard_rejects_unauthenticated_callback(tmp_path) -> None:
    client = TestClient(_guard_app())
    resp = client.post("/callback/t1", data={"status": "success"})
    assert resp.status_code == 503  # 未配置 AI Bearer

    _write_ai_extension(tmp_path, "tok")
    assert client.post("/callback/t1", data={"status": "success"}).status_code == 401
    assert (
        client.post("/callback/t1", data={"status": "success"}, headers={"Authorization": "Bearer tok"}).status_code
        == 200
    )


def test_guard_internal_tasks_requires_internal_token(tmp_path) -> None:
    client = TestClient(_guard_app())
    assert client.post("/pallas/api/internal/ai/tasks/t1", json={"task_id": "t1"}).status_code == 403
    token = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    resp = client.post(
        "/pallas/api/internal/ai/tasks/t1",
        json={"task_id": "t1"},
        headers={INTERNAL_TOKEN_HEADER: token},
    )
    assert resp.status_code == 200


def test_guard_rejects_oversized_content_length(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PALLAS_AI_INTERNAL_MAX_BYTES", "1024")
    client = TestClient(_guard_app())
    token = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    resp = client.post(
        "/pallas/api/internal/ai/tasks/t1",
        content=b"x" * 4096,
        headers={INTERNAL_TOKEN_HEADER: token, "Content-Type": "application/json"},
    )
    assert resp.status_code == 413


def test_guard_rejects_oversized_chunked_body(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PALLAS_AI_INTERNAL_MAX_BYTES", "1024")
    client = TestClient(_guard_app())
    token = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)

    def _chunks():
        for _ in range(8):
            yield b"x" * 512

    resp = client.post(
        "/pallas/api/internal/ai/tasks/t1",
        content=_chunks(),
        headers={INTERNAL_TOKEN_HEADER: token, "Content-Type": "application/json"},
    )
    assert resp.status_code == 413


# ---------- TaskManager binding / terminal ----------


@pytest.fixture
def task_manager(monkeypatch):
    import asyncio

    from pallas.core.foundation.config import TaskManager

    monkeypatch.setattr("pallas.core.platform.coord.redis_settings.coord_redis_enabled", lambda: False)
    monkeypatch.setattr(TaskManager, "_tasks", {})
    monkeypatch.setattr(TaskManager, "_terminal", {})
    monkeypatch.setattr(TaskManager, "_lock", asyncio.Lock())
    return TaskManager


async def test_task_manager_same_binding_is_idempotent(task_manager, monkeypatch) -> None:
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    payload = {"bot_id": "123", "group_id": 9, "user_id": 7, "task_type": "sing", "start_time": _now()}
    assert await task_manager.add_task("t1", dict(payload)) == "ok"
    assert await task_manager.add_task("t1", dict(payload)) == "ok"


async def test_task_manager_different_binding_conflicts(task_manager, monkeypatch) -> None:
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    base = {"bot_id": "123", "group_id": 9, "user_id": 7, "task_type": "sing", "start_time": _now()}
    assert await task_manager.add_task("t1", dict(base)) == "ok"
    changed = dict(base, group_id=10)
    assert await task_manager.add_task("t1", changed) == "conflict"


async def test_task_manager_terminal_prevents_revival(task_manager, monkeypatch) -> None:
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.remove_ai_task",
        lambda _tid: None,
    )
    payload = {"bot_id": "123", "group_id": 9, "user_id": 7, "task_type": "sing", "start_time": _now()}
    assert await task_manager.add_task("t1", dict(payload)) == "ok"
    assert await task_manager.claim_task("t1") is not None
    assert await task_manager.claim_task("t1") is None
    assert await task_manager.add_task("t1", dict(payload)) == "conflict"


# ---------- tools context binding ----------


def _tool_body(**overrides):
    from pallas.core.platform.ai_callback.llm_tools_http import LlmToolExecuteRequest

    data = {
        "name": "memory.recall",
        "arguments": {},
        "bot_id": 123,
        "group_id": 9,
        "user_id": 7,
        "request_id": "task-1",
    }
    data.update(overrides)
    return LlmToolExecuteRequest(**data)


def _llm_task(**overrides):
    task = {"bot_id": "123", "group_id": 9, "user_id": 7, "task_type": "llm_chat", "start_time": _now()}
    task.update(overrides)
    return task


def test_tools_context_rejects_identity_mismatch() -> None:
    from pallas.core.platform.ai_callback.llm_tools_http import build_tool_context

    with pytest.raises(HTTPException) as exc:
        build_tool_context(_tool_body(group_id=10), _llm_task())
    assert exc.value.status_code == 403


def test_tools_context_blocks_social_and_alias() -> None:
    from pallas.core.platform.ai_callback.llm_tools_http import build_tool_context

    for name in ("social.master.info", "social__master__info"):
        with pytest.raises(HTTPException) as exc:
            build_tool_context(_tool_body(name=name), _llm_task())
        assert exc.value.status_code == 403


def test_tools_context_rejects_non_llm_task() -> None:
    from pallas.core.platform.ai_callback.llm_tools_http import build_tool_context

    with pytest.raises(HTTPException) as exc:
        build_tool_context(_tool_body(), _llm_task(task_type="sing"))
    assert exc.value.status_code == 403


def test_tools_request_forbids_self_granted_approval() -> None:
    from pydantic import ValidationError

    from pallas.core.platform.ai_callback.llm_tools_http import LlmToolExecuteRequest

    with pytest.raises(ValidationError):
        LlmToolExecuteRequest(
            name="x",
            arguments={},
            bot_id=1,
            group_id=2,
            user_id=3,
            request_id="t",
            approved_tools=["danger"],
        )


def test_tools_context_builds_from_task_record() -> None:
    from pallas.core.platform.ai_callback.llm_tools_http import build_tool_context

    task = _llm_task(command_source_segments=[{"type": "command", "name": "x"}, {"bad": 1}])
    ctx = build_tool_context(_tool_body(), task)
    assert ctx.bot_id == 123
    assert ctx.group_id == 9
    assert ctx.user_id == 7
    assert ctx.request_id == "task-1"
    assert ctx.approved_tools == frozenset()
    assert ctx.source_segments == ({"type": "command", "name": "x"},)


# ---------- callback field validation ----------


def test_validate_callback_payload_bounds_text(monkeypatch) -> None:
    from pallas.core.platform.ai_callback.runner import validate_callback_payload

    monkeypatch.setenv("PALLAS_AI_CALLBACK_TEXT_MAX_BYTES", "256")
    validate_callback_payload(status="success", text="short")
    with pytest.raises(HTTPException) as exc:
        validate_callback_payload(status="success", text="x" * 1024)
    assert exc.value.status_code == 413


def test_validate_callback_payload_rejects_invalid_status() -> None:
    from pallas.core.platform.ai_callback.runner import validate_callback_payload

    with pytest.raises(HTTPException) as exc:
        validate_callback_payload(status="weird")
    assert exc.value.status_code == 400


def test_validate_callback_payload_bounds_file(monkeypatch) -> None:
    from types import SimpleNamespace

    from pallas.core.platform.ai_callback.runner import validate_callback_payload

    monkeypatch.setenv("PALLAS_AI_CALLBACK_MAX_FILE_BYTES", "1024")
    with pytest.raises(HTTPException) as exc:
        validate_callback_payload(status="success", file=SimpleNamespace(size=4096))
    assert exc.value.status_code == 413


# ---------- file manager bounded read ----------


def test_file_manager_read_is_bounded(tmp_path, monkeypatch) -> None:
    from packages.pb_webui import file_manager_api

    monkeypatch.setattr(file_manager_api, "PROJECT_ROOT", tmp_path)
    big = tmp_path / "big.txt"
    big.write_text("a" * (file_manager_api._MAX_TEXT_BYTES + 10), encoding="utf-8")

    app = FastAPI()
    from fastapi import APIRouter

    router = APIRouter()
    file_manager_api.register_file_manager_router(router, x="/pallas/api", plugin_config=object())
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/pallas/api/files/read", params={"path": "big.txt"})
    assert resp.status_code == 413


# ---------- BFF same-origin redirect ----------


def test_bff_opener_blocks_cross_origin_redirect() -> None:
    from packages.pb_webui.ai_extension_api import _same_origin, build_same_origin_opener

    assert _same_origin("http://127.0.0.1:9099/a", "http://127.0.0.1:9099/b")
    assert not _same_origin("http://127.0.0.1:9099/a", "http://evil.example/b")
    assert build_same_origin_opener("http://127.0.0.1:9099") is not None


# ---------- hub → worker forward ----------


async def test_forward_bounded_file_raises_413(monkeypatch) -> None:
    from io import BytesIO

    from fastapi import UploadFile

    from pallas.core.platform.ai_callback import boundary_limits
    from pallas.core.platform.shard.coord.ai_callback_forward import _read_bounded

    monkeypatch.setattr(boundary_limits, "callback_max_file_bytes", lambda: 1024)
    upload = UploadFile(filename="a.bin", file=BytesIO(b"x" * 4096))
    with pytest.raises(HTTPException) as exc:
        await _read_bounded(upload, boundary_limits.callback_max_file_bytes())
    assert exc.value.status_code == 413


async def test_forward_uses_bearer_and_no_redirect(monkeypatch) -> None:
    from unittest.mock import AsyncMock, Mock

    from pallas.core.platform.shard.coord import ai_callback_forward as fwd

    monkeypatch.setattr(fwd, "resolve_worker_port_for_task", lambda _tid: 7971)
    monkeypatch.setattr(fwd, "ai_bearer_headers", lambda: {"Authorization": "Bearer x"})
    response = Mock(status_code=200)
    response.json.return_value = {"message": "ok"}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = response
    captured: dict = {}
    monkeypatch.setattr(fwd.httpx, "AsyncClient", lambda **kw: (captured.update(kw), client)[1])

    result = await fwd.forward_ai_callback_to_worker("t1", status="success", text="hi")

    assert result == {"message": "ok"}
    assert captured["trust_env"] is False
    assert captured["follow_redirects"] is False
    assert client.post.await_args.kwargs["headers"] == {"Authorization": "Bearer x"}


async def test_forward_preserves_worker_413(monkeypatch) -> None:
    from unittest.mock import AsyncMock, Mock

    from pallas.core.platform.shard.coord import ai_callback_forward as fwd

    monkeypatch.setattr(fwd, "resolve_worker_port_for_task", lambda _tid: 7971)
    response = Mock(status_code=413, text="too large")
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = response
    monkeypatch.setattr(fwd.httpx, "AsyncClient", lambda **_kw: client)

    with pytest.raises(HTTPException) as exc:
        await fwd.forward_ai_callback_to_worker("t1", status="success")
    assert exc.value.status_code == 413


# ---------- Redis 登记/领取原子性（claim 与 register 交错） ----------


class _HookRedis:
    """最小 fake：支持 set(nx,ex)/get/getdel/delete 与原子 eval（复刻 ai_task 脚本）。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.on_getdel = None

    def set(self, key, val, ex=None, nx=False):  # noqa: ANN001
        if nx and key in self.store:
            return False
        self.store[key] = val
        return True

    def get(self, key):  # noqa: ANN001
        return self.store.get(key)

    def getdel(self, key):  # noqa: ANN001
        val = self.store.pop(key, None)
        if self.on_getdel is not None:
            self.on_getdel()
        return val

    def delete(self, key):  # noqa: ANN001
        self.store.pop(key, None)
        return 1

    def eval(self, script, numkeys, *args):  # noqa: ANN001
        keys = list(args[:numkeys])
        argv = list(args[numkeys:])
        if "pallas:ai_task:register" in script:
            terminal_key, task_key = keys
            body, _ttl, binding_sig, content_sig = argv
            if terminal_key in self.store:
                return "conflict"
            existing = self.store.get(task_key)
            if existing is not None:
                dec = json.loads(existing)

                def _s(value):  # noqa: ANN001
                    return "" if value is None else str(value).strip()

                if _s(dec.get("_binding_sig")) != binding_sig or _s(dec.get("_content_sig")) != content_sig:
                    return "conflict"
                return "ok"
            self.store[task_key] = body
            return "ok"
        if "pallas:ai_task:claim" in script:
            task_key, terminal_key = keys
            raw = self.store.get(task_key)
            if raw is None:
                return None
            self.store.pop(task_key, None)
            self.store[terminal_key] = "1"
            return raw
        if "pallas:ai_task:terminal_remove" in script:
            terminal_key, task_key = keys
            self.store[terminal_key] = "1"
            self.store.pop(task_key, None)
            return 1
        raise AssertionError(f"unexpected script: {script[:40]}")


def _bind_redis(monkeypatch, client) -> None:
    monkeypatch.setattr("pallas.core.platform.coord.redis_settings.coord_redis_enabled", lambda: True)
    monkeypatch.setattr("pallas.core.platform.coord.redis_claim.get_coord_redis_client", lambda: client)


def _task_rec(task_id: str = "T") -> dict:
    import time

    return {
        "task_id": task_id,
        "bot_id": "1",
        "group_id": 2,
        "user_id": 3,
        "task_type": "sing",
        "start_time": time.time(),
    }


def test_claim_register_gap_does_not_double_claim(monkeypatch) -> None:
    from pallas.core.platform.shard.coord import ai_task_registry as reg

    client = _HookRedis()
    _bind_redis(monkeypatch, client)
    rec = _task_rec()
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "ok"

    first = reg.claim_ai_task_record("T")
    second = reg.claim_ai_task_record("T")
    assert first is not None
    assert second is None
    # 领取后同 ID 登记不得复活终态，pending 也不再可见
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "conflict"
    assert reg.get_ai_task_record("T") is None


def test_register_does_not_overwrite_existing_binding(monkeypatch) -> None:
    import json as _json

    from pallas.core.platform.shard.coord import ai_task_registry as reg

    client = _HookRedis()
    _bind_redis(monkeypatch, client)
    rec = _task_rec()
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "ok"
    changed = dict(rec, group_id=99)
    assert reg.write_ai_task_redis_sync(changed, ttl_sec=3600) == "conflict"
    stored = _json.loads(client.store[reg.ai_task_redis_key("T")])
    assert stored["group_id"] == 2


# ---------- boundary guard 头部歧义 / Content-Length 有界 ----------


async def _run_guard(path: str, headers: list[tuple[str, str]], body: bytes = b"") -> list[dict]:
    app = FastAPI()
    guard = AiBoundaryGuard(app)
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {"type": "http", "path": path, "headers": [(k.encode(), v.encode()) for k, v in headers]}
    await guard(scope, receive, send)
    return sent


async def test_guard_rejects_duplicate_authorization(tmp_path) -> None:
    _write_ai_extension(tmp_path, "tok")
    sent = await _run_guard(
        "/callback/t1",
        [("authorization", "Bearer tok"), ("authorization", "Bearer tok")],
        body=b"status=success",
    )
    assert sent[0]["status"] == 400


async def test_guard_rejects_duplicate_internal_token() -> None:
    token = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    sent = await _run_guard(
        "/pallas/api/internal/ai/tasks/t1",
        [(INTERNAL_TOKEN_HEADER, token), (INTERNAL_TOKEN_HEADER, token)],
        body=b"{}",
    )
    assert sent[0]["status"] == 400


async def test_guard_huge_content_length_is_not_500() -> None:
    token = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    sent = await _run_guard(
        "/pallas/api/internal/ai/tasks/t1",
        [(INTERNAL_TOKEN_HEADER, token), ("content-length", "9" * 5000)],
    )
    assert sent[0]["status"] == 413


async def test_guard_non_digit_content_length_is_400() -> None:
    token = internal_auth.derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    sent = await _run_guard(
        "/pallas/api/internal/ai/tasks/t1",
        [(INTERNAL_TOKEN_HEADER, token), ("content-length", "abc")],
    )
    assert sent[0]["status"] == 400


async def test_guard_replay_handles_empty_body(tmp_path) -> None:
    _write_ai_extension(tmp_path, "tok")
    sent = await _run_guard("/callback/t1", [("authorization", "Bearer tok")], body=b"")
    # 通过守卫后进入 app（无路由 → 404），不得因空 body/断连出错
    assert sent
    assert sent[0]["status"] in {404, 405}


def test_guard_install_skips_loudly_when_app_started(caplog) -> None:
    import logging
    from types import SimpleNamespace

    from pallas.core.platform.ai_callback.boundary_guard import install_ai_boundary_guard

    class _StartedApp:
        def __init__(self) -> None:
            self.state = SimpleNamespace()
            self.middleware_stack = object()
            self.added = 0

        def add_middleware(self, _mw) -> None:
            self.added += 1

    app = _StartedApp()
    with caplog.at_level(logging.WARNING):
        install_ai_boundary_guard(app)
    assert app.added == 0
    assert not getattr(app.state, "_pallas_ai_boundary_guard", False)
    assert any("boundary guard not installed" in r.message for r in caplog.records)
