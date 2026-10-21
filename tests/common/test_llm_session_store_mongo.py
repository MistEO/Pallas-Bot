from __future__ import annotations

import time

import pytest

from pallas.core.foundation.db.modules import LlmChatMessage
from pallas.product.llm.config import LlmConfig, clear_llm_config_cache
from pallas.product.llm.session_models import SESSION_SUMMARY_PREFIX
from pallas.product.llm.session_store import (
    append_llm_message,
    build_llm_chat_messages,
    clear_llm_messages,
    clear_user_llm_messages,
    compact_user_llm_history_with_summary,
    get_llm_history_session_detail,
    is_llm_session_store_available,
    list_group_ambient_messages,
    list_llm_history_sessions,
    list_user_llm_messages,
)
from pallas.product.llm.session_store_mongo import MongoLlmSessionMessageBackend


def _patch_mongo_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pallas.core.foundation.db.runtime.is_postgresql_backend",
        lambda _backend=None: False,
    )
    monkeypatch.setattr(
        "pallas.core.foundation.db.runtime.is_mongodb_backend",
        lambda _backend=None: True,
    )
    monkeypatch.setattr(
        "pallas.core.foundation.db.runtime_storage_ready",
        lambda _backend=None: True,
    )
    clock = {"t": 1_700_000_000}

    def fake_time() -> int:
        clock["t"] += 1
        return clock["t"]

    monkeypatch.setattr("pallas.product.llm.session_store_mongo.time.time", fake_time)


@pytest.mark.asyncio
async def test_mongo_llm_session_user_window_and_ambient(beanie_fixture, monkeypatch) -> None:
    clear_llm_config_cache()
    _patch_mongo_backend(monkeypatch)
    cfg = LlmConfig(
        llm_session_enabled=True,
        llm_session_user_window=2,
        llm_session_user_storage_window=2,
        llm_session_group_window=2,
        llm_session_user_ttl_sec=0,
    )
    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)
    assert is_llm_session_store_available() is True

    for index in range(3):
        assert await append_llm_message(10001, 20002, 30003, "user", f"a-{index}") is True
    for index in range(3):
        assert await append_llm_message(10001, 20002, 40004, "user", f"b-{index}") is True

    user_a = await list_user_llm_messages(10001, 20002, 30003)
    user_b = await list_user_llm_messages(10001, 20002, 40004)
    assert [turn.content for turn in user_a] == ["a-1", "a-2"]
    assert [turn.content for turn in user_b] == ["b-1", "b-2"]

    ambient = await list_group_ambient_messages(10001, 20002)
    # group_window=2 → 群内按时间最近 2 条（trim 后剩 a-1/a-2/b-1/b-2）
    assert len(ambient) == 2
    assert {turn.content for turn in ambient} == {"b-1", "b-2"}


@pytest.mark.asyncio
async def test_mongo_build_llm_chat_messages_user_thread_and_ambient(beanie_fixture, monkeypatch) -> None:
    clear_llm_config_cache()
    _patch_mongo_backend(monkeypatch)
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_user_window=8,
        llm_session_group_window=4,
        llm_session_user_ttl_sec=0,
    )
    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)

    from pallas.product.llm.kernel.memory_governance import can_read_runtime_state

    assert can_read_runtime_state(cfg) is True

    await append_llm_message(1, 100, 200, "user", "other-user-msg")
    await append_llm_message(1, 100, 200, "assistant", "reply-to-other")
    await append_llm_message(1, 100, 300, "user", "my-old")
    await append_llm_message(1, 100, 300, "assistant", "my-reply")

    messages = await build_llm_chat_messages(1, 100, 300, "my-new", cfg=cfg)
    assert messages[-1].role == "user"
    assert "my-new" in messages[-1].content
    joined = "\n".join(item.content for item in messages)
    assert "群环境摘录" in joined, joined
    assert "my-old" in joined


@pytest.mark.asyncio
async def test_mongo_clear_and_history(beanie_fixture, monkeypatch) -> None:
    clear_llm_config_cache()
    _patch_mongo_backend(monkeypatch)
    cfg = LlmConfig(
        llm_session_enabled=True,
        llm_session_user_window=20,
        llm_session_group_window=20,
        llm_session_user_ttl_sec=0,
    )
    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)

    await append_llm_message(10, 100, 200, "user", "u200-1")
    await append_llm_message(10, 100, 200, "assistant", "a200-1")
    await append_llm_message(10, 100, 300, "user", "u300-1")
    await append_llm_message(10, 100, 300, "assistant", "a300-1")

    sessions = await list_llm_history_sessions(bot_id=10, group_id=100, limit=10)
    assert [row.user_id for row in sessions] == [300, 200]
    assert sessions[0].last_content == "a300-1"
    assert sessions[0].turn_count == 2

    detail = await get_llm_history_session_detail(bot_id=10, group_id=100, user_id=200, limit=10)
    assert detail is not None
    assert [turn.content for turn in detail.turns] == ["u200-1", "a200-1"]

    assert await clear_user_llm_messages(10, 100, 200) == 2
    assert await list_user_llm_messages(10, 100, 200) == []
    assert await clear_llm_messages(10, 100) == 2


@pytest.mark.asyncio
async def test_mongo_compact_user_history(beanie_fixture, monkeypatch) -> None:
    clear_llm_config_cache()
    _patch_mongo_backend(monkeypatch)
    cfg = LlmConfig(
        llm_session_enabled=True,
        llm_session_user_window=20,
        llm_session_user_ttl_sec=0,
    )
    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)

    for index in range(5):
        await append_llm_message(1, 10, 20, "user", f"msg-{index}")
    assert await compact_user_llm_history_with_summary(
        1,
        10,
        20,
        "summary-text",
        keep_messages=2,
        cfg=cfg,
    )
    turns = await list_user_llm_messages(1, 10, 20, limit=20)
    assert any("此前对话摘要" in turn.content and "summary-text" in turn.content for turn in turns)
    assert len(turns) == 3


@pytest.mark.asyncio
async def test_mongo_snapshot_and_compact_by_source_ids(beanie_fixture) -> None:
    backend = MongoLlmSessionMessageBackend()
    for index in range(6):
        await LlmChatMessage(
            bot_id=1,
            group_id=10,
            user_id=20,
            role="user",
            content=f"{SESSION_SUMMARY_PREFIX}旧摘要" if index == 0 else f"m-{index}",
            created_at=index + 1,
        ).insert()
    await LlmChatMessage(
        bot_id=1,
        group_id=10,
        user_id=21,
        role="user",
        content="other-user",
        created_at=1,
    ).insert()
    await LlmChatMessage(
        bot_id=1,
        group_id=11,
        user_id=20,
        role="user",
        content="other-group",
        created_at=1,
    ).insert()

    snapshot = await backend.read_user_compaction_snapshot(1, 10, 20, limit=6, ttl_sec=0)
    assert [turn.message_id for turn in snapshot] == sorted(turn.message_id for turn in snapshot)
    source_ids = [turn.message_id for turn in snapshot[:-2]]
    summary_created_at = snapshot[-2].created_at - 1
    assert await backend.compact_user_with_summary(
        1,
        10,
        20,
        f"{SESSION_SUMMARY_PREFIX}新摘要",
        keep_messages=99,
        source_message_ids=source_ids,
        summary_created_at=summary_created_at,
    )

    turns = await backend.list_user_messages(1, 10, 20, limit=20, ttl_sec=0)
    assert len(turns) == 3
    assert turns[0].content == f"{SESSION_SUMMARY_PREFIX}新摘要"
    assert [turn.content for turn in turns[1:]] == [turn.content for turn in snapshot[-2:]]
    other_user = await backend.list_user_messages(1, 10, 21, limit=20, ttl_sec=0)
    assert [turn.content for turn in other_user] == ["other-user"]
    other_group = await backend.list_user_messages(1, 11, 20, limit=20, ttl_sec=0)
    assert [turn.content for turn in other_group] == ["other-group"]


@pytest.mark.asyncio
async def test_mongo_snapshot_same_second_order_and_over_window(beanie_fixture) -> None:
    backend = MongoLlmSessionMessageBackend()
    docs = []
    for index in range(4):
        doc = LlmChatMessage(
            bot_id=1,
            group_id=10,
            user_id=20,
            role="user",
            content=f"same-second-{index}",
            created_at=50,
        )
        await doc.insert()
        docs.append(doc)

    snapshot = await backend.read_user_compaction_snapshot(1, 10, 20, limit=4, ttl_sec=0)
    assert [turn.message_id for turn in snapshot] == [str(doc.id) for doc in docs]
    assert await backend.read_user_compaction_snapshot(1, 10, 20, limit=3, ttl_sec=0) is None


@pytest.mark.asyncio
async def test_mongo_snapshot_excludes_expired_and_compact_leaves_it(beanie_fixture, monkeypatch) -> None:
    backend = MongoLlmSessionMessageBackend()
    now = int(time.time())
    expired = LlmChatMessage(
        bot_id=1,
        group_id=10,
        user_id=20,
        role="user",
        content="expired",
        created_at=now - 1000,
    )
    current = LlmChatMessage(
        bot_id=1,
        group_id=10,
        user_id=20,
        role="user",
        content="current",
        created_at=now - 10,
    )
    await expired.insert()
    await current.insert()

    snapshot = await backend.read_user_compaction_snapshot(1, 10, 20, limit=10, ttl_sec=60)
    assert [turn.message_id for turn in snapshot] == [str(current.id)]
    assert await backend.compact_user_with_summary(
        1,
        10,
        20,
        f"{SESSION_SUMMARY_PREFIX}摘要",
        keep_messages=1,
        source_message_ids=[str(current.id)],
        summary_created_at=now - 11,
    )
    docs = await LlmChatMessage.find({"bot_id": 1, "group_id": 10, "user_id": 20}).to_list()
    assert any(doc.content == "expired" for doc in docs)
    assert not any(doc.content == "current" for doc in docs)


@pytest.mark.asyncio
async def test_mongo_compact_insert_failure_deletes_nothing(beanie_fixture, monkeypatch) -> None:
    backend = MongoLlmSessionMessageBackend()
    for index in range(3):
        await LlmChatMessage(
            bot_id=1,
            group_id=10,
            user_id=20,
            role="user",
            content=f"m-{index}",
            created_at=index + 1,
        ).insert()
    snapshot = await backend.read_user_compaction_snapshot(1, 10, 20, limit=10, ttl_sec=0)

    async def fail_insert(_self):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(LlmChatMessage, "insert", fail_insert)
    assert not await backend.compact_user_with_summary(
        1,
        10,
        20,
        f"{SESSION_SUMMARY_PREFIX}摘要",
        keep_messages=1,
        source_message_ids=[turn.message_id for turn in snapshot[:2]],
        summary_created_at=0,
    )
    docs = (
        await LlmChatMessage
        .get_pymongo_collection()
        .find({
            "bot_id": 1,
            "group_id": 10,
            "user_id": 20,
        })
        .to_list(length=20)
    )
    assert {doc["content"] for doc in docs} == {"m-0", "m-1", "m-2"}


@pytest.mark.asyncio
async def test_mongo_compact_delete_failure_keeps_summary_and_originals(beanie_fixture, monkeypatch) -> None:
    backend = MongoLlmSessionMessageBackend()
    for index in range(3):
        await LlmChatMessage(
            bot_id=1,
            group_id=10,
            user_id=20,
            role="user",
            content=f"m-{index}",
            created_at=index + 1,
        ).insert()
    snapshot = await backend.read_user_compaction_snapshot(1, 10, 20, limit=10, ttl_sec=0)
    original_find = LlmChatMessage.find

    class FailingDeleteQuery:
        def __init__(self, query):
            self._query = query

        def __getattr__(self, name):
            return getattr(self._query, name)

        async def delete(self):
            raise RuntimeError("delete failed")

    def fake_find(*args, **kwargs):
        return FailingDeleteQuery(original_find(*args, **kwargs))

    monkeypatch.setattr(LlmChatMessage, "find", fake_find)
    assert not await backend.compact_user_with_summary(
        1,
        10,
        20,
        f"{SESSION_SUMMARY_PREFIX}摘要",
        keep_messages=1,
        source_message_ids=[turn.message_id for turn in snapshot[:2]],
        summary_created_at=0,
    )
    docs = (
        await LlmChatMessage
        .get_pymongo_collection()
        .find({
            "bot_id": 1,
            "group_id": 10,
            "user_id": 20,
        })
        .to_list(length=20)
    )
    contents = {doc["content"] for doc in docs}
    assert {"m-0", "m-1", "m-2"}.issubset(contents)
    assert any(content.startswith(SESSION_SUMMARY_PREFIX) for content in contents)


@pytest.mark.asyncio
async def test_mongo_compact_rejects_invalid_object_id(beanie_fixture) -> None:
    backend = MongoLlmSessionMessageBackend()
    await LlmChatMessage(
        bot_id=1,
        group_id=10,
        user_id=20,
        role="user",
        content="m-0",
        created_at=1,
    ).insert()
    assert not await backend.compact_user_with_summary(
        1,
        10,
        20,
        f"{SESSION_SUMMARY_PREFIX}摘要",
        keep_messages=1,
        source_message_ids=["not-an-object-id"],
        summary_created_at=0,
    )
    assert await LlmChatMessage.find({"bot_id": 1, "group_id": 10, "user_id": 20}).count() == 1
