"""任务状态原子性与终态防复活回归（独立审查 1–9）。

不依赖真实 Redis/PG/AI：本地用 TaskManager，Redis 协调用可注入交错的 fake。
fake 以 Python 复刻原子脚本语义（同一调用内完成 terminal 检查/绑定比较/创建），
用于证明“检查与写入之间不可插入”的原子性，而非跳过关键逻辑。
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi import HTTPException

from pallas.core.platform.shard.coord import ai_task_registry as reg


@pytest.fixture(autouse=True)
def reset_task_manager(monkeypatch):
    from pallas.core.foundation.config import TaskManager

    monkeypatch.setattr("pallas.core.platform.coord.redis_settings.coord_redis_enabled", lambda: False)
    monkeypatch.setattr(TaskManager, "_tasks", {})
    monkeypatch.setattr(TaskManager, "_terminal", {})
    monkeypatch.setattr(TaskManager, "_lock", asyncio.Lock())
    return TaskManager


class FakeAiTaskRedis:
    """支持 get/set/getdel/delete 与原子 eval；可在脚本内注入并发交错。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.register_race = None
        self.claim_race = None
        self.raise_on_eval = None

    # --- 旧调用面（修复前代码使用；保持可用以便红→绿对照） ---
    def get(self, key):  # noqa: ANN001
        value = self.store.get(key)
        if self.register_race is not None and key == self.register_race[0]:
            self.register_race[1]()
        return value

    def set(self, key, val, ex=None, nx=False):  # noqa: ANN001
        if nx and key in self.store:
            return False
        self.store[key] = val
        return True

    def getdel(self, key):  # noqa: ANN001
        value = self.store.pop(key, None)
        if self.claim_race is not None:
            self.claim_race()
        return value

    def delete(self, key):  # noqa: ANN001
        self.store.pop(key, None)
        return 1

    # --- 原子脚本调用面 ---
    def eval(self, script, numkeys, *args):  # noqa: ANN001
        if self.raise_on_eval is not None:
            raise self.raise_on_eval
        keys = list(args[:numkeys])
        argv = list(args[numkeys:])
        if "pallas:ai_task:register" in script:
            if self.register_race is not None:
                self.register_race[1]()
            return self._register(keys, argv)
        if "pallas:ai_task:claim" in script:
            raw = self.store.get(keys[0])
            if self.claim_race is not None:
                self.claim_race()
            if raw is None:
                return None
            self.store.pop(keys[0], None)
            self.store[keys[1]] = "1"
            return raw
        if "pallas:ai_task:terminal_remove" in script:
            self.store[keys[0]] = "1"
            self.store.pop(keys[1], None)
            return 1
        raise AssertionError(f"unexpected script: {script[:40]}")

    @staticmethod
    def _s(value):  # noqa: ANN001
        return "" if value is None else str(value).strip()

    def _register(self, keys, argv):  # noqa: ANN001
        terminal_key, task_key = keys
        body, _ttl, binding_sig, content_sig = argv
        if terminal_key in self.store:
            return "conflict"
        existing = self.store.get(task_key)
        if existing is not None:
            try:
                dec = json.loads(existing)
            except (TypeError, ValueError):
                return "conflict"
            if not isinstance(dec, dict):
                return "conflict"
            if self._s(dec.get("_binding_sig")) != binding_sig or self._s(dec.get("_content_sig")) != content_sig:
                return "conflict"
            return "ok"
        self.store[task_key] = body
        return "ok"


def bind_redis(monkeypatch, client) -> None:  # noqa: ANN001
    monkeypatch.setattr("pallas.core.platform.coord.redis_settings.coord_redis_enabled", lambda: True)
    monkeypatch.setattr("pallas.core.platform.coord.redis_claim.get_coord_redis_client", lambda: client)


def task_rec(task_id: str = "T", **overrides) -> dict:
    rec = {
        "task_id": task_id,
        "bot_id": "1",
        "group_id": 2,
        "user_id": 3,
        "task_type": "sing",
        "start_time": time.time(),
    }
    rec.update(overrides)
    return rec


# ---------- 1. 本地领取与重试登记交错 ----------


async def test_local_inflight_claim_blocks_reregister(reset_task_manager, monkeypatch) -> None:
    import threading

    manager = reset_task_manager
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    payload = {"bot_id": "123", "group_id": 9, "user_id": 7, "task_type": "sing", "start_time": time.time()}
    assert await manager.add_task("t1", dict(payload)) == "ok"

    started = threading.Event()
    allow = threading.Event()

    def blocking_remove(_tid) -> None:
        started.set()
        allow.wait(timeout=5)

    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.remove_ai_task",
        blocking_remove,
    )

    first = asyncio.create_task(manager.claim_task("t1"))
    for _ in range(200):
        if started.is_set():
            break
        await asyncio.sleep(0.01)
    assert started.is_set()
    # 在途领取尚未落终态：同绑定重试登记必须被拒
    assert await manager.add_task("t1", dict(payload)) == "conflict"
    allow.set()
    claimed = await asyncio.wait_for(first, timeout=5)

    assert claimed is not None
    assert await manager.claim_task("t1") is None
    assert "t1" not in manager._tasks


async def test_local_claim_sets_terminal_before_cleanup(reset_task_manager, monkeypatch) -> None:
    manager = reset_task_manager
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    payload = {"bot_id": "123", "group_id": 9, "task_type": "sing", "start_time": time.time()}
    await manager.add_task("t2", dict(payload))

    def boom(_tid):
        raise RuntimeError("redis down")

    monkeypatch.setattr("pallas.core.platform.shard.coord.ai_task_registry.remove_ai_task", boom)

    with pytest.raises(RuntimeError):
        await manager.claim_task("t2")
    # 清理失败也必须视为已消费：终态已落，不可再领、不可复活
    assert await manager.claim_task("t2") is None
    assert await manager.add_task("t2", dict(payload)) == "conflict"


# ---------- 2. Redis 登记不得复活终态 + pending 排除终态 ----------


def test_redis_register_is_atomic_against_concurrent_claim(monkeypatch) -> None:
    client = FakeAiTaskRedis()
    bind_redis(monkeypatch, client)
    rec = task_rec()
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "ok"

    terminal_key = reg.ai_task_terminal_key("T")

    def concurrent_claim() -> None:
        client.store.pop(reg.ai_task_redis_key("T"), None)
        client.store[terminal_key] = "1"

    client.register_race = (terminal_key, concurrent_claim)
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "conflict"
    assert reg.get_ai_task_record("T") is None


def test_redis_register_conflicts_after_claim(monkeypatch) -> None:
    client = FakeAiTaskRedis()
    bind_redis(monkeypatch, client)
    rec = task_rec()
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "ok"
    assert reg.claim_ai_task_record("T") is not None
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "conflict"
    assert reg.get_ai_task_record("T") is None


# ---------- 3. 旧空领取清理不得删除新终态 ----------


def test_stale_empty_claim_does_not_delete_new_terminal(monkeypatch) -> None:
    client = FakeAiTaskRedis()
    bind_redis(monkeypatch, client)
    terminal_key = reg.ai_task_terminal_key("T")

    def newer_claim_terminal() -> None:
        client.store[terminal_key] = "1"

    client.claim_race = newer_claim_terminal
    # 旧领取者在空记录上的清理不得抹掉更新的终态
    assert reg.claim_ai_task_redis_sync("T") is None
    assert client.store.get(terminal_key) == "1"
    assert reg.write_ai_task_redis_sync(task_rec(), ttl_sec=3600) == "conflict"


# ---------- 4. 协调失败统一领域错误 ----------


def test_redis_register_client_missing_raises(monkeypatch) -> None:
    monkeypatch.setattr("pallas.core.platform.coord.redis_settings.coord_redis_enabled", lambda: True)
    monkeypatch.setattr("pallas.core.platform.coord.redis_claim.get_coord_redis_client", lambda: None)
    with pytest.raises(reg.AiTaskRedisError):
        reg.write_ai_task_redis_sync(task_rec(), ttl_sec=3600)


def test_redis_claim_client_missing_raises(monkeypatch) -> None:
    monkeypatch.setattr("pallas.core.platform.coord.redis_settings.coord_redis_enabled", lambda: True)
    monkeypatch.setattr("pallas.core.platform.coord.redis_claim.get_coord_redis_client", lambda: None)
    with pytest.raises(reg.AiTaskRedisError):
        reg.claim_ai_task_redis_sync("T")


def test_redis_write_failure_raises_domain_error(monkeypatch) -> None:
    client = FakeAiTaskRedis()
    client.raise_on_eval = OSError("socket reset")
    bind_redis(monkeypatch, client)
    with pytest.raises(reg.AiTaskRedisError):
        reg.write_ai_task_redis_sync(task_rec(), ttl_sec=3600)


def test_redis_claim_failure_raises_domain_error(monkeypatch) -> None:
    client = FakeAiTaskRedis()
    client.raise_on_eval = OSError("socket reset")
    bind_redis(monkeypatch, client)
    with pytest.raises(reg.AiTaskRedisError):
        reg.claim_ai_task_redis_sync("T")


async def test_add_task_does_not_silently_succeed_when_register_fails(reset_task_manager, monkeypatch) -> None:
    manager = reset_task_manager
    monkeypatch.setattr("pallas.core.platform.coord.redis_settings.coord_redis_enabled", lambda: True)
    monkeypatch.setattr("pallas.core.platform.coord.redis_claim.get_coord_redis_client", lambda: None)

    with pytest.raises(reg.AiTaskRedisError):
        await manager.add_task("t4", {"bot_id": "123", "task_type": "sing", "start_time": time.time()})
    assert "t4" not in manager._tasks


async def test_registration_route_maps_redis_error_to_503(monkeypatch) -> None:
    from pallas.core.platform.ai_callback.task_registration import register_ai_task_from_aux

    monkeypatch.setattr("pallas.core.platform.coord.redis_settings.coord_redis_enabled", lambda: True)
    monkeypatch.setattr("pallas.core.platform.coord.redis_claim.get_coord_redis_client", lambda: None)
    from pallas.core.platform.ai_callback.internal_auth import (
        PURPOSE_AI_TASK_REGISTRATION,
        derive_internal_token,
    )

    with pytest.raises(HTTPException) as exc:
        await register_ai_task_from_aux(
            "t4",
            {"bot_id": "123", "task_type": "sing", "start_time": time.time()},
            internal_token=derive_internal_token(PURPOSE_AI_TASK_REGISTRATION),
        )
    assert exc.value.status_code == 503


# ---------- 5. 取消/删除写终态 ----------


async def test_local_remove_marks_terminal(reset_task_manager, monkeypatch) -> None:
    manager = reset_task_manager
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    monkeypatch.setattr("pallas.core.platform.shard.coord.ai_task_registry.remove_ai_task", lambda _tid: None)
    payload = {"bot_id": "123", "group_id": 9, "task_type": "sing", "start_time": time.time()}
    assert await manager.add_task("t5", dict(payload)) == "ok"
    await manager.remove_task("t5")
    assert await manager.get_task("t5") is None
    assert await manager.add_task("t5", dict(payload)) == "conflict"


def test_redis_remove_marks_terminal(monkeypatch) -> None:
    client = FakeAiTaskRedis()
    bind_redis(monkeypatch, client)
    rec = task_rec("t5")
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "ok"
    reg.remove_ai_task("t5")
    assert reg.get_ai_task_record("t5") is None
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "conflict"


# ---------- 6. task_status 规范化，不毒化本地表 ----------


@pytest.mark.parametrize(
    "start_time",
    ["not-a-number", "1234.5", float("nan"), float("inf"), None, -1.0],
)
async def test_add_task_rejects_invalid_start_time(reset_task_manager, monkeypatch, start_time) -> None:
    manager = reset_task_manager
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    bad = {"bot_id": "123", "group_id": 9, "task_type": "sing", "start_time": start_time}
    assert await manager.add_task("bad", bad) == "invalid"
    assert "bad" not in manager._tasks
    # 坏输入不得使后续 refresh/登记不可用
    await manager.refresh()
    good = {"bot_id": "123", "group_id": 9, "task_type": "sing", "start_time": time.time()}
    assert await manager.add_task("good", good) == "ok"
    assert await manager.claim_task("good") is not None


@pytest.mark.parametrize("bot_id", ["abc", "", None, "12 3"])
async def test_add_task_rejects_invalid_subject(reset_task_manager, bot_id) -> None:
    manager = reset_task_manager
    bad = {"bot_id": bot_id, "task_type": "sing", "start_time": time.time()}
    assert await manager.add_task("bad", bad) == "invalid"


async def test_registration_route_rejects_invalid_status(monkeypatch) -> None:
    from pallas.core.platform.ai_callback.internal_auth import (
        PURPOSE_AI_TASK_REGISTRATION,
        derive_internal_token,
    )
    from pallas.core.platform.ai_callback.task_registration import register_ai_task_from_aux

    with pytest.raises(HTTPException) as exc:
        await register_ai_task_from_aux(
            "bad",
            {"bot_id": "123", "task_type": "sing", "start_time": "nope"},
            internal_token=derive_internal_token(PURPOSE_AI_TASK_REGISTRATION),
        )
    assert exc.value.status_code == 400


# ---------- 7. 同绑定幂等保留原记录，受保护内容变更冲突 ----------


async def test_local_same_binding_preserves_protected_content(reset_task_manager, monkeypatch) -> None:
    manager = reset_task_manager
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    base = {
        "bot_id": "123",
        "group_id": 9,
        "user_id": 7,
        "task_type": "sing",
        "start_time": time.time(),
        "song_id": "A",
        "command_source_segments": [{"type": "command", "name": "sing"}],
    }
    assert await manager.add_task("t7", dict(base)) == "ok"
    # 同绑定但 song_id 变化 → 冲突，原记录保留
    assert await manager.add_task("t7", dict(base, song_id="B")) == "conflict"
    # 同绑定但来源消息段变化 → 冲突
    assert await manager.add_task("t7", dict(base, command_source_segments=[{"type": "at"}])) == "conflict"
    # 完全相同的受保护内容 → 幂等 ok
    assert await manager.add_task("t7", dict(base)) == "ok"
    stored = await manager.get_task("t7")
    assert stored is not None
    assert stored["song_id"] == "A"


def test_redis_same_binding_preserves_protected_content(monkeypatch) -> None:
    client = FakeAiTaskRedis()
    bind_redis(monkeypatch, client)
    base = task_rec("t7", song_id="A", command_source_segments=[{"type": "command"}])
    assert reg.write_ai_task_redis_sync(dict(base), ttl_sec=3600) == "ok"
    assert reg.write_ai_task_redis_sync(dict(base, song_id="B"), ttl_sec=3600) == "conflict"
    assert (
        reg.write_ai_task_redis_sync(dict(base, command_source_segments=[{"type": "at"}]), ttl_sec=3600) == "conflict"
    )
    assert reg.write_ai_task_redis_sync(dict(base), ttl_sec=3600) == "ok"
    stored = reg.read_ai_task_redis_sync("t7")
    assert stored is not None
    assert stored["song_id"] == "A"


# ---------- 8. song_id 校验在 claim 之前 ----------


async def test_song_id_mismatch_does_not_consume_task(reset_task_manager, monkeypatch) -> None:
    from pallas.core.platform.ai_callback import runner as callback_runner

    manager = reset_task_manager
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    monkeypatch.setattr("pallas.core.platform.shard.coord.ai_task_registry.remove_ai_task", lambda _tid: None)

    def no_bot(_bot_id):
        raise ValueError("bot not found")

    monkeypatch.setattr(callback_runner, "get_bot", no_bot)
    payload = {
        "bot_id": "123",
        "group_id": 9,
        "user_id": 7,
        "task_type": "sing",
        "start_time": time.time(),
        "song_id": "good",
    }
    await manager.add_task("t8", dict(payload))

    with pytest.raises(HTTPException) as exc:
        await callback_runner.run_ai_callback("t8", status="failed", song_id="wrong")
    assert exc.value.status_code == 400
    # 错 song_id 不得消费任务
    assert await manager.get_task("t8") is not None

    result = await callback_runner.run_ai_callback("t8", status="failed", song_id="good")
    assert result == {"message": "ok"}
    assert await manager.get_task("t8") is None


# ---------- 9. key 允许负音调，chunk/history 各自范围 ----------


@pytest.mark.parametrize("key", [-12, -1, 0, 12])
def test_validate_callback_payload_accepts_pitch_range(key) -> None:
    from pallas.core.platform.ai_callback.runner import validate_callback_payload

    validate_callback_payload(status="success", key=key)


@pytest.mark.parametrize("key", [-13, 13, 100])
def test_validate_callback_payload_rejects_pitch_out_of_range(key) -> None:
    from pallas.core.platform.ai_callback.runner import validate_callback_payload

    with pytest.raises(HTTPException) as exc:
        validate_callback_payload(status="success", key=key)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("field", ["chunk_index", "history_keep_messages"])
def test_validate_callback_payload_numeric_ranges(field) -> None:
    from pallas.core.platform.ai_callback.runner import validate_callback_payload

    validate_callback_payload(status="success", **{field: 0})
    with pytest.raises(HTTPException) as exc:
        validate_callback_payload(status="success", **{field: -1})
    assert exc.value.status_code == 400


# ---------- TTL / 并发 / 本地协调错误 ----------


async def test_terminal_expires_after_ttl(reset_task_manager, monkeypatch) -> None:
    manager = reset_task_manager
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _tid, _status: "skipped",
    )
    monkeypatch.setattr("pallas.core.platform.shard.coord.ai_task_registry.remove_ai_task", lambda _tid: None)
    monkeypatch.setattr("pallas.core.platform.shard.coord.ai_task_registry.ai_task_ttl_sec", lambda: 600.0)
    now = time.time()
    monkeypatch.setattr("pallas.core.foundation.config.time.time", lambda: now)
    payload = {"bot_id": "123", "group_id": 9, "task_type": "sing", "start_time": now}
    await manager.add_task("ttl", dict(payload))
    await manager.remove_task("ttl")
    assert await manager.add_task("ttl", dict(payload)) == "conflict"
    monkeypatch.setattr("pallas.core.foundation.config.time.time", lambda: now + 601.0)
    assert await manager.add_task("ttl", dict(payload)) == "ok"


def test_redis_binding_signature_is_stable_for_integral_float(monkeypatch) -> None:
    client = FakeAiTaskRedis()
    bind_redis(monkeypatch, client)
    rec = task_rec("sig", start_time=1750000000.0)
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "ok"
    stored = json.loads(client.store[reg.ai_task_redis_key("sig")])
    assert stored["_binding_sig"] == reg.ai_task_binding_signature(rec)
    # 同记录重登记幂等：不得因 Lua/Python 浮点格式化差异被判冲突
    assert reg.write_ai_task_redis_sync(dict(rec), ttl_sec=3600) == "ok"


def test_redis_claim_is_one_shot_concurrent(monkeypatch) -> None:
    client = FakeAiTaskRedis()
    bind_redis(monkeypatch, client)
    assert reg.write_ai_task_redis_sync(task_rec("cc"), ttl_sec=3600) == "ok"
    first = reg.claim_ai_task_record("cc")
    second = reg.claim_ai_task_record("cc")
    assert first is not None
    assert second is None


# ---------- 2（路由层）：终态后登记 409，tools 路由 404 且不执行 ----------


async def test_registration_route_conflicts_after_claim(tmp_path, monkeypatch) -> None:
    from pallas.core.platform.ai_callback.internal_auth import (
        PURPOSE_AI_TASK_REGISTRATION,
        derive_internal_token,
    )
    from pallas.core.platform.ai_callback.task_registration import register_ai_task_from_aux

    monkeypatch.setattr("pallas.core.foundation.paths.DATA_ROOT", tmp_path)
    client = FakeAiTaskRedis()
    bind_redis(monkeypatch, client)
    token = derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)
    rec = task_rec("route")
    assert await register_ai_task_from_aux("route", dict(rec), internal_token=token) == {"message": "ok"}
    assert reg.claim_ai_task_record("route") is not None
    with pytest.raises(HTTPException) as exc:
        await register_ai_task_from_aux("route", dict(rec), internal_token=token)
    assert exc.value.status_code == 409


def test_tools_route_404_when_task_terminal(tmp_path, monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from fastapi import FastAPI
    from starlette.testclient import TestClient

    monkeypatch.setattr("pallas.core.foundation.paths.DATA_ROOT", tmp_path)
    ext = tmp_path / "pb_webui"
    ext.mkdir(parents=True, exist_ok=True)
    (ext / "ai_extension.json").write_text(json.dumps({"token": "tok"}), encoding="utf-8")

    from pallas.core.foundation.config import TaskManager

    monkeypatch.setattr("pallas.core.platform.coord.redis_settings.coord_redis_enabled", lambda: False)
    monkeypatch.setattr(TaskManager, "_tasks", {})
    monkeypatch.setattr(TaskManager, "_terminal", {"t1": time.time() + 3600})
    monkeypatch.setattr(TaskManager, "_lock", asyncio.Lock())

    app = FastAPI()
    monkeypatch.setattr("nonebot.get_app", lambda: app)
    from pallas.core.platform.ai_callback import llm_tools_http

    llm_tools_http.register_llm_tools_http()
    executor = AsyncMock()
    monkeypatch.setattr("pallas.product.llm.tools.registry.execute_tool_async", executor)

    body = {
        "name": "memory.recall",
        "arguments": {},
        "bot_id": 123,
        "group_id": 9,
        "user_id": 7,
        "request_id": "t1",
    }
    client = TestClient(app)
    resp = client.post(
        "/pallas/api/internal/llm/tools/execute",
        json=body,
        headers={"Authorization": "Bearer tok"},
    )
    assert resp.status_code == 404
    executor.assert_not_awaited()
