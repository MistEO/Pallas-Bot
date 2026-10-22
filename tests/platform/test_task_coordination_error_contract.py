"""协调错误合同回归 R1–R3（独立复查 bot-post-remediation-review.md）。

R1：配置要求协调但 ping 失败时，任务路径不得回退本地权威（登记/领取关闭、503）。
R2：pending 查询纯读；缺失/过期返回 None 且不取消；读取故障抛领域异常，各边界 503 且不写。
R3：取消失败（client 缺失 / eval 异常）抛领域异常，DELETE 503；恢复后重试成功才 ok。
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from pallas.core.platform.coord import redis_claim as rc
from pallas.core.platform.coord import redis_settings as rs
from pallas.core.platform.shard.coord import ai_task_registry as reg

_DEAD_SOCKET_URL = "unix:///tmp/pallas-coord-redis-does-not-exist.sock"


@pytest.fixture(autouse=True)
def reset_task_state(monkeypatch):
    from pallas.core.foundation.config import TaskManager

    monkeypatch.setattr(TaskManager, "_tasks", {})
    monkeypatch.setattr(TaskManager, "_terminal", {})
    monkeypatch.setattr(TaskManager, "_lock", asyncio.Lock())
    monkeypatch.delenv("PALLAS_COORD_REDIS_ENABLED", raising=False)
    monkeypatch.delenv("PALLAS_COORD_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("PALLAS_COORD_REDIS_URL", raising=False)
    _clear_caches()
    yield TaskManager
    _clear_caches()


def _clear_caches() -> None:
    # enabled / client getter 被用例 patch 成普通函数时其 lru 清理不可用（monkeypatch 尚未还原）
    if hasattr(rs.coord_redis_enabled, "cache_clear"):
        rs.clear_coord_redis_settings_cache()
    if hasattr(rc.get_coord_redis_client, "cache_clear"):
        rc.clear_coord_redis_client_cache()


def status(**overrides) -> dict:
    rec = {
        "bot_id": "1",
        "group_id": 2,
        "user_id": 3,
        "task_type": "sing",
        "start_time": time.time(),
    }
    rec.update(overrides)
    return rec


def task_rec(task_id: str = "T", **overrides) -> dict:
    return status(task_id=task_id, **overrides)


class RecordingRedis:
    """记录命令的 fake：可断言“零写入”，并可注入读取故障与并发交错。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.commands: list[tuple[str, tuple]] = []
        self.raise_on_get: Exception | None = None
        self.raise_on_eval: Exception | None = None
        self.on_missing_get = None

    @property
    def writes(self) -> list[tuple[str, tuple]]:
        return [c for c in self.commands if c[0] != "get"]

    def get(self, key):  # noqa: ANN001
        self.commands.append(("get", (key,)))
        if self.raise_on_get is not None:
            raise self.raise_on_get
        value = self.store.get(key)
        if value is None and self.on_missing_get is not None and not key.startswith("pallas:ai_task_done:"):
            self.on_missing_get()
        return value

    def set(self, key, value, ex=None):  # noqa: ANN001
        self.commands.append(("set", (key,)))
        self.store[key] = value
        return True

    def delete(self, *keys):  # noqa: ANN001
        self.commands.append(("delete", tuple(keys)))
        for key in keys:
            self.store.pop(key, None)
        return len(keys)

    def eval(self, script, numkeys, *args):  # noqa: ANN001
        self.commands.append(("eval", (script.splitlines()[1].strip(),)))
        if self.raise_on_eval is not None:
            raise self.raise_on_eval
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
                if dec.get("_binding_sig") != binding_sig or dec.get("_content_sig") != content_sig:
                    return "conflict"
                return "ok"
            self.store[task_key] = body
            return "ok"
        if "pallas:ai_task:claim" in script:
            task_key, terminal_key = keys
            raw = self.store.pop(task_key, None)
            if raw is None:
                return None
            self.store[terminal_key] = "1"
            return raw
        if "pallas:ai_task:terminal_remove" in script:
            terminal_key, task_key = keys
            self.store[terminal_key] = "1"
            self.store.pop(task_key, None)
            return 1
        raise AssertionError(f"unexpected script: {script[:40]}")


def bind_required(monkeypatch, client) -> None:  # noqa: ANN001
    monkeypatch.setattr(rs, "coord_redis_enabled", lambda: True)
    monkeypatch.setattr(rc, "get_coord_redis_client", lambda: client)


# ---------- R1：配置要求协调与健康分离 ----------


@pytest.mark.parametrize("mode", ["true", "auto"])
def test_configured_coord_with_failed_ping_fails_closed(monkeypatch, mode) -> None:
    if mode == "true":
        monkeypatch.setenv("PALLAS_COORD_REDIS_ENABLED", "true")
    monkeypatch.setenv("PALLAS_COORD_REDIS_URL", _DEAD_SOCKET_URL)
    _clear_caches()

    # 真实配置链：mode != false + URL 已配置 → 要求协调；ping 失败只是健康状态
    assert rs.coord_redis_configured() is True
    assert rs.coord_redis_enabled() is False
    assert rc.get_coord_redis_client() is None

    with pytest.raises(reg.AiTaskRedisError):
        reg.register_ai_task("r1", status())
    with pytest.raises(reg.AiTaskRedisError):
        reg.claim_ai_task_redis_sync("r1")


def test_coord_health_predicate_keeps_other_consumers_semantics(monkeypatch) -> None:
    monkeypatch.setenv("PALLAS_COORD_REDIS_ENABLED", "true")
    monkeypatch.setenv("PALLAS_COORD_REDIS_URL", _DEAD_SOCKET_URL)
    _clear_caches()
    # 其他消费者沿用「配置 + ping」的可用性判定，未被任务意图改写
    assert rs.coord_redis_enabled() is False
    monkeypatch.setenv("PALLAS_COORD_REDIS_ENABLED", "false")
    _clear_caches()
    assert rs.coord_redis_enabled() is False
    assert rs.coord_redis_configured() is False


async def test_configured_coord_failure_does_not_win_locally(reset_task_state, monkeypatch) -> None:
    manager = reset_task_state
    monkeypatch.setenv("PALLAS_COORD_REDIS_ENABLED", "true")
    monkeypatch.setenv("PALLAS_COORD_REDIS_URL", _DEAD_SOCKET_URL)
    _clear_caches()

    with pytest.raises(reg.AiTaskRedisError):
        await manager.add_task("r1-reg", status())
    assert "r1-reg" not in manager._tasks

    # 本地已有记录也不得因协调不可用而本地获胜
    manager._tasks["r1-claim"] = {"bot_id": "1", "start_time": time.time()}
    with pytest.raises(reg.AiTaskRedisError):
        await manager.claim_task("r1-claim")
    assert "r1-claim" in manager._tasks


async def test_register_route_maps_configured_failure_to_503(reset_task_state, monkeypatch) -> None:
    from pallas.core.platform.ai_callback.internal_auth import (
        PURPOSE_AI_TASK_REGISTRATION,
        derive_internal_token,
    )
    from pallas.core.platform.ai_callback.task_registration import register_ai_task_from_aux

    monkeypatch.setenv("PALLAS_COORD_REDIS_ENABLED", "true")
    monkeypatch.setenv("PALLAS_COORD_REDIS_URL", _DEAD_SOCKET_URL)
    _clear_caches()
    with pytest.raises(HTTPException) as exc:
        await register_ai_task_from_aux(
            "r1-route",
            status(),
            internal_token=derive_internal_token(PURPOSE_AI_TASK_REGISTRATION),
        )
    assert exc.value.status_code == 503


def test_unconfigured_coord_keeps_local_authority(monkeypatch) -> None:
    monkeypatch.setenv("PALLAS_COORD_REDIS_ENABLED", "false")
    monkeypatch.setenv("PALLAS_COORD_REDIS_URL", "redis://example.invalid:6379/0")
    _clear_caches()
    assert rs.coord_redis_configured() is False
    assert reg.register_ai_task("r1-off", status()) == "skipped"


async def test_coord_url_absent_keeps_local_authority(reset_task_state, monkeypatch) -> None:
    manager = reset_task_state
    monkeypatch.setenv("PALLAS_COORD_REDIS_ENABLED", "true")
    _clear_caches()
    assert rs.coord_redis_configured() is False
    assert await manager.add_task("r1-local", status()) == "ok"
    assert await manager.claim_task("r1-local") is not None


# ---------- R2：pending 查询纯读、故障领域化、边界 503 ----------


def test_pending_read_missing_is_pure_read(monkeypatch) -> None:
    client = RecordingRedis()
    bind_required(monkeypatch, client)
    assert reg.get_ai_task_record("gone") is None
    assert client.writes == []
    assert client.store == {}


def test_pending_read_expired_is_pure_read(monkeypatch) -> None:
    client = RecordingRedis()
    bind_required(monkeypatch, client)
    stale = dict(task_rec("stale", start_time=time.time() - 10_000_000))
    assert reg.write_ai_task_redis_sync(dict(stale), ttl_sec=3600) == "ok"
    client.commands.clear()
    assert reg.get_ai_task_record("stale") is None
    assert client.writes == []
    assert reg.ai_task_redis_key("stale") in client.store


def test_pending_read_client_missing_raises(monkeypatch) -> None:
    monkeypatch.setattr(rs, "coord_redis_enabled", lambda: True)
    monkeypatch.setattr(rc, "get_coord_redis_client", lambda: None)
    with pytest.raises(reg.AiTaskRedisError):
        reg.get_ai_task_record("t")
    with pytest.raises(reg.AiTaskRedisError):
        reg.read_ai_task_redis_sync("t")


def test_pending_read_get_failure_raises(monkeypatch) -> None:
    client = RecordingRedis()
    client.raise_on_get = OSError("socket reset")
    bind_required(monkeypatch, client)
    with pytest.raises(reg.AiTaskRedisError):
        reg.get_ai_task_record("t")
    assert client.writes == []


def test_pending_read_failure_is_retryable(monkeypatch) -> None:
    client = RecordingRedis()
    bind_required(monkeypatch, client)
    assert reg.write_ai_task_redis_sync(task_rec("retry"), ttl_sec=3600) == "ok"
    client.raise_on_get = OSError("socket reset")
    with pytest.raises(reg.AiTaskRedisError):
        reg.get_ai_task_record("retry")
    client.raise_on_get = None
    client.commands.clear()
    assert reg.get_ai_task_record("retry") is not None
    assert client.writes == []


def test_empty_read_does_not_cancel_concurrently_registered_task(monkeypatch) -> None:
    client = RecordingRedis()
    bind_required(monkeypatch, client)
    client.on_missing_get = lambda: reg.write_ai_task_redis_sync(task_rec("race"), ttl_sec=3600)
    assert reg.get_ai_task_record("race") is None
    assert reg.ai_task_terminal_key("race") not in client.store
    assert reg.ai_task_redis_key("race") in client.store
    assert reg.claim_ai_task_record("race") is not None


async def test_song_peek_lookup_failure_is_503_not_404(monkeypatch) -> None:
    from pallas.core.platform.ai_callback import runner as callback_runner

    client = RecordingRedis()
    client.raise_on_get = OSError("socket reset")
    bind_required(monkeypatch, client)

    with pytest.raises(HTTPException) as exc:
        await callback_runner.run_ai_callback("peek", status="failed", song_id="s1")
    assert exc.value.status_code == 503
    assert client.writes == []


async def test_song_peek_missing_task_is_404(monkeypatch) -> None:
    from pallas.core.platform.ai_callback import runner as callback_runner

    client = RecordingRedis()
    bind_required(monkeypatch, client)
    with pytest.raises(HTTPException) as exc:
        await callback_runner.run_ai_callback("peek-missing", status="failed", song_id="s1")
    assert exc.value.status_code == 404
    assert client.writes == []


async def test_hub_forward_lookup_failure_is_503(monkeypatch) -> None:
    from pallas.core.platform.shard.coord import ai_callback_forward

    client = RecordingRedis()
    client.raise_on_get = OSError("socket reset")
    bind_required(monkeypatch, client)

    def no_http(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("lookup failure must not attempt forwarding")

    monkeypatch.setattr(ai_callback_forward.httpx, "AsyncClient", no_http)
    with pytest.raises(HTTPException) as exc:
        await ai_callback_forward.forward_ai_callback_to_worker("hub", status="failed")
    assert exc.value.status_code == 503
    assert client.writes == []


async def test_hub_forward_missing_task_is_404(monkeypatch) -> None:
    from pallas.core.platform.shard.coord import ai_callback_forward

    client = RecordingRedis()
    bind_required(monkeypatch, client)
    with pytest.raises(HTTPException) as exc:
        await ai_callback_forward.forward_ai_callback_to_worker("hub-missing", status="failed")
    assert exc.value.status_code == 404


def test_tools_route_lookup_failure_is_503(tmp_path, monkeypatch) -> None:
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    monkeypatch.setattr("pallas.core.foundation.paths.DATA_ROOT", tmp_path)
    ext = tmp_path / "pb_webui"
    ext.mkdir(parents=True, exist_ok=True)
    (ext / "ai_extension.json").write_text(json.dumps({"token": "tok"}), encoding="utf-8")

    client = RecordingRedis()
    client.raise_on_get = OSError("socket reset")
    bind_required(monkeypatch, client)

    app = FastAPI()
    monkeypatch.setattr("nonebot.get_app", lambda: app)
    from pallas.core.platform.ai_callback import llm_tools_http

    llm_tools_http.register_llm_tools_http()
    executor = AsyncMock()
    monkeypatch.setattr("pallas.product.llm.tools.registry.execute_tool_async", executor)

    resp = TestClient(app).post(
        "/pallas/api/internal/llm/tools/execute",
        json={
            "name": "memory.recall",
            "arguments": {},
            "bot_id": 1,
            "group_id": 2,
            "user_id": 3,
            "request_id": "tools-lookup",
        },
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 503
    executor.assert_not_awaited()
    assert client.writes == []


# ---------- R3：取消失败领域化，DELETE 503 ----------


def test_cancel_client_missing_raises(monkeypatch) -> None:
    monkeypatch.setattr(rs, "coord_redis_enabled", lambda: True)
    monkeypatch.setattr(rc, "get_coord_redis_client", lambda: None)
    with pytest.raises(reg.AiTaskRedisError):
        reg.remove_ai_task("c")


def test_cancel_eval_failure_raises(monkeypatch) -> None:
    client = RecordingRedis()
    client.raise_on_eval = OSError("socket reset")
    bind_required(monkeypatch, client)
    with pytest.raises(reg.AiTaskRedisError):
        reg.remove_ai_task("c")


async def test_cancel_failure_does_not_fake_success_and_retry_works(reset_task_state, monkeypatch) -> None:
    manager = reset_task_state
    client = RecordingRedis()
    bind_required(monkeypatch, client)
    assert reg.write_ai_task_redis_sync(task_rec("c2"), ttl_sec=3600) == "ok"
    manager._tasks["c2"] = task_rec("c2")

    client.raise_on_eval = OSError("socket reset")
    with pytest.raises(reg.AiTaskRedisError):
        await manager.remove_task("c2")
    # 共享 pending 仍在、本地未宣称终态
    assert reg.ai_task_redis_key("c2") in client.store
    assert reg.ai_task_terminal_key("c2") not in client.store
    assert "c2" not in manager._terminal

    client.raise_on_eval = None
    await manager.remove_task("c2")
    assert reg.ai_task_terminal_key("c2") in client.store
    assert reg.ai_task_redis_key("c2") not in client.store
    assert "c2" in manager._terminal
    assert reg.claim_ai_task_record("c2") is None
    assert reg.write_ai_task_redis_sync(task_rec("c2"), ttl_sec=3600) == "conflict"


async def test_delete_route_maps_cancel_failure_to_503(tmp_path, monkeypatch) -> None:
    from pallas.core.platform.ai_callback.internal_auth import (
        PURPOSE_AI_TASK_REGISTRATION,
        derive_internal_token,
    )
    from pallas.core.platform.ai_callback.task_registration import unregister_ai_task_from_aux

    monkeypatch.setattr("pallas.core.foundation.paths.DATA_ROOT", tmp_path)
    client = RecordingRedis()
    bind_required(monkeypatch, client)
    assert reg.write_ai_task_redis_sync(task_rec("c3"), ttl_sec=3600) == "ok"
    client.raise_on_eval = OSError("socket reset")

    with pytest.raises(HTTPException) as exc:
        await unregister_ai_task_from_aux(
            "c3",
            internal_token=derive_internal_token(PURPOSE_AI_TASK_REGISTRATION),
        )
    assert exc.value.status_code == 503
    assert reg.ai_task_redis_key("c3") in client.store
