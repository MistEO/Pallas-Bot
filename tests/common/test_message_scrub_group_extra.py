"""message_scrub 群级追加屏蔽词：内存快照、入口、校验与调用点。"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pallas.product.message_scrub import (
    group_extra,
    is_message_scrub_blocked_async,
    is_message_scrub_blocked_sync,
    reload_message_scrub_caches,
)


@pytest.fixture
def group_scrub_env(monkeypatch: pytest.MonkeyPatch):
    keys = [
        "PALLAS_MESSAGE_SCRUB_ENABLED",
        "PALLAS_INBOUND_FILTER_SUBSTRINGS",
        "PALLAS_SCRUB_LEXICON_PATH",
        "PALLAS_SCRUB_LEXICON_EXTRA",
        "PALLAS_SCRUB_REVIEW_PROVIDERS",
        "PALLAS_INBOUND_FILTER_API_URL",
        "PALLAS_SCRUB_API_URL",
    ]
    saved = {k: os.environ.pop(k, None) for k in keys}
    reload_message_scrub_caches()
    group_extra.reset_group_scrub_snapshot()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    reload_message_scrub_caches()
    group_extra.reset_group_scrub_snapshot()


def _install_fake_group_repo(monkeypatch: pytest.MonkeyPatch, row, rows=None) -> dict:
    saved: dict = {"fields": {}}

    class _Repo:
        async def list_all(self):
            return list(rows or [])

        async def get_or_create(self, gid, **kwargs):
            return row, False

        async def get(self, gid, *, ignore_cache: bool = False):
            return row

        async def upsert_field(self, gid, field, value):
            saved["fields"][field] = value
            setattr(row, field, value)

        async def upsert_fields(self, gid, fields):
            saved["fields"].update(fields)
            for k, v in fields.items():
                setattr(row, k, v)

        async def invalidate_cache(self):
            return None

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())
    return saved


# ---------------------------------------------------------------------------
# 归一化 / 校验
# ---------------------------------------------------------------------------


def test_normalize_strips_dedupes_case_insensitively_and_drops_empty() -> None:
    out = group_extra.normalize_group_scrub_extra(["  Bad ", "", "bad", "  ", "Word"])
    assert out == ["Bad", "Word"]


def test_normalize_rejects_non_list() -> None:
    with pytest.raises(ValueError, match="必须是字符串列表"):
        group_extra.normalize_group_scrub_extra("bad")


def test_normalize_rejects_non_string_item() -> None:
    with pytest.raises(ValueError, match="仅接受字符串"):
        group_extra.normalize_group_scrub_extra(["ok", 3])


def test_normalize_rejects_too_many_words() -> None:
    with pytest.raises(ValueError, match="最多"):
        group_extra.normalize_group_scrub_extra([f"w{i}" for i in range(201)])


def test_normalize_rejects_overlong_word() -> None:
    with pytest.raises(ValueError, match="最长"):
        group_extra.normalize_group_scrub_extra(["x" * 65])


def test_normalize_allows_limit_values() -> None:
    assert len(group_extra.normalize_group_scrub_extra([f"w{i}" for i in range(200)])) == 200
    assert group_extra.normalize_group_scrub_extra(["x" * 64]) == ["x" * 64]


# ---------------------------------------------------------------------------
# 内存快照：首载 / 群作用域 / 全局叠加
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_snapshot_loads_from_repo_and_scopes_by_group(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    rows = [
        SimpleNamespace(group_id=1, message_scrub_extra=["Alpha"]),
        SimpleNamespace(group_id=2, message_scrub_extra=[]),
    ]
    _install_fake_group_repo(monkeypatch, None, rows=rows)
    await group_extra.init_group_scrub_snapshot()

    assert is_message_scrub_blocked_sync(plain_text="alpha here", raw_message="", group_id=1)
    assert not is_message_scrub_blocked_sync(plain_text="alpha here", raw_message="", group_id=2)
    assert not is_message_scrub_blocked_sync(plain_text="alpha here", raw_message="")


def test_group_words_add_to_global_not_replace(monkeypatch: pytest.MonkeyPatch, group_scrub_env: None) -> None:
    monkeypatch.setenv("PALLAS_INBOUND_FILTER_SUBSTRINGS", "globalword")
    reload_message_scrub_caches()
    group_extra.apply_group_scrub_extra_local(5, ["groupword"])

    assert is_message_scrub_blocked_sync(plain_text="globalword", raw_message="", group_id=5)
    assert is_message_scrub_blocked_sync(plain_text="GROUPWORD", raw_message="", group_id=5)
    assert not is_message_scrub_blocked_sync(plain_text="groupword", raw_message="", group_id=6)


def test_global_off_disables_group_words(monkeypatch: pytest.MonkeyPatch, group_scrub_env: None) -> None:
    monkeypatch.setenv("PALLAS_MESSAGE_SCRUB_ENABLED", "false")
    monkeypatch.setenv("PALLAS_INBOUND_FILTER_SUBSTRINGS", "globalword")
    reload_message_scrub_caches()
    group_extra.apply_group_scrub_extra_local(5, ["groupword"])

    assert not is_message_scrub_blocked_sync(plain_text="globalword", raw_message="", group_id=5)
    assert not is_message_scrub_blocked_sync(plain_text="groupword", raw_message="", group_id=5)


def test_apply_local_clear_removes_words(group_scrub_env: None) -> None:
    group_extra.apply_group_scrub_extra_local(9, ["term"])
    assert is_message_scrub_blocked_sync(plain_text="term", raw_message="", group_id=9)
    group_extra.apply_group_scrub_extra_local(9, [])
    assert not is_message_scrub_blocked_sync(plain_text="term", raw_message="", group_id=9)


@pytest.mark.asyncio
async def test_async_group_hit_skips_remote(monkeypatch: pytest.MonkeyPatch, group_scrub_env: None) -> None:
    group_extra.apply_group_scrub_extra_local(7, ["badterm"])
    remote = AsyncMock(side_effect=AssertionError("remote must not run on group hit"))
    monkeypatch.setattr("pallas.product.message_scrub.run_review_chain", remote)

    assert await is_message_scrub_blocked_async(plain_text="BADTERM", raw_message="", group_id=7)
    remote.assert_not_called()


# ---------------------------------------------------------------------------
# 快照刷新：成功替换 / 失败保留 / 旧 load 不覆盖新 patch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_replaces_snapshot_from_db(monkeypatch: pytest.MonkeyPatch, group_scrub_env: None) -> None:
    rows = [SimpleNamespace(group_id=4, message_scrub_extra=["dbword"])]
    _install_fake_group_repo(monkeypatch, None, rows=rows)
    await group_extra.refresh_group_scrub_snapshot_once()
    assert is_message_scrub_blocked_sync(plain_text="dbword", raw_message="", group_id=4)


@pytest.mark.asyncio
async def test_refresh_failure_keeps_old_snapshot(monkeypatch: pytest.MonkeyPatch, group_scrub_env: None) -> None:
    group_extra.apply_group_scrub_extra_local(3, ["keepme"])

    class _Repo:
        async def list_all(self):
            raise RuntimeError("db down")

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())
    await group_extra.refresh_group_scrub_snapshot_once()
    assert is_message_scrub_blocked_sync(plain_text="keepme", raw_message="", group_id=3)


@pytest.mark.asyncio
async def test_stale_refresh_does_not_override_local_patch(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _Repo:
        async def list_all(self):
            started.set()
            await release.wait()
            return [SimpleNamespace(group_id=3, message_scrub_extra=["fromdb"])]

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())
    task = asyncio.create_task(group_extra.refresh_group_scrub_snapshot_once())
    await started.wait()
    group_extra.apply_group_scrub_extra_local(3, ["fresh"])
    release.set()
    await task

    assert is_message_scrub_blocked_sync(plain_text="fresh", raw_message="", group_id=3)
    assert not is_message_scrub_blocked_sync(plain_text="fromdb", raw_message="", group_id=3)


@pytest.mark.asyncio
async def test_init_tolerates_dirty_stored_rows(monkeypatch: pytest.MonkeyPatch, group_scrub_env: None) -> None:
    rows = [SimpleNamespace(group_id=1, message_scrub_extra=["ok", 5, "  ", "x" * 65, "OK"])]
    _install_fake_group_repo(monkeypatch, None, rows=rows)
    await group_extra.init_group_scrub_snapshot()
    assert is_message_scrub_blocked_sync(plain_text="ok", raw_message="", group_id=1)


# ---------------------------------------------------------------------------
# 调用点透传 group_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_gate_passes_group_id_to_scrub(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.repeater import event_gate

    captured: dict = {}

    def spy(*, plain_text: str, raw_message: str, group_id: int | None = None) -> bool:
        captured["group_id"] = group_id
        return True

    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_sync", spy)
    monkeypatch.setattr(event_gate, "repeater_worker_handles_message", lambda _b: True)
    monkeypatch.setattr(event_gate, "ingress_fanout_bypasses_claim", lambda _p: False)

    event = SimpleNamespace(
        group_id=200,
        user_id=300,
        message_id=400,
        raw_message="hello",
        get_plaintext=lambda: "hello",
    )
    result = await event_gate.build_repeater_event_context(100, event)

    assert result is None
    assert captured["group_id"] == 200


@pytest.mark.asyncio
async def test_handler_passes_group_id_to_scrub(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.repeater.handlers import message as mod

    captured: dict = {}

    async def spy(*, plain_text: str, raw_message: str, group_id: int | None = None) -> bool:
        captured["group_id"] = group_id
        return True

    async def fake_ctx(bot_id: int, event):
        return SimpleNamespace(plain_body="x", norm_raw="x", sharding_active=False)

    monkeypatch.setattr(mod, "is_message_scrub_blocked_async", spy)
    monkeypatch.setattr(mod, "build_repeater_event_context", fake_ctx)

    event = SimpleNamespace(self_id=100, group_id=200, user_id=300, message_id=400)
    await mod.execute_repeater_message(SimpleNamespace(self_id=100), event)

    assert captured["group_id"] == 200


@pytest.mark.asyncio
async def test_runtime_handler_passes_group_id_to_scrub(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.repeater import message_runtime_handler as mod

    captured: dict = {}

    async def spy(*, plain_text: str, raw_message: str, group_id: int | None = None) -> bool:
        captured["group_id"] = group_id
        return True

    async def fake_ctx(bot_id: int, event):
        return SimpleNamespace(plain_body="x", norm_raw="x", sharding_active=False)

    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_async", spy)
    monkeypatch.setattr("packages.repeater.event_gate.build_repeater_event_context", fake_ctx)

    from pallas.core.platform.message_runtime.models import MessageContext

    context = MessageContext(
        ingress_id="i-1",
        bot_id=1,
        group_id=22,
        message_id=3,
        plain_text="x",
        raw_text="x",
        is_to_me=False,
        command_traffic=False,
        route_modules=frozenset(),
    )
    event = SimpleNamespace(self_id=1, group_id=22, user_id=3, message_id=4, is_tome=lambda: False)
    handler = mod.RepeaterDirectHandler()
    outcome = await handler.build_fanout_plan(context, bot=SimpleNamespace(self_id=1), event=event)

    assert outcome.handled is True
    assert captured["group_id"] == 22


@pytest.mark.asyncio
async def test_gate_global_hook_passes_group_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.core.platform.ingress import gate

    captured: dict = {}

    def spy(*, plain_text: str, raw_message: str, group_id: int | None = None) -> bool:
        captured["group_id"] = group_id
        return False

    class _FakeMessageEvent:
        pass

    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_sync", spy)
    monkeypatch.setattr("nonebot.adapters.onebot.v11.MessageEvent", _FakeMessageEvent)

    group_event = _FakeMessageEvent()
    group_event.get_plaintext = lambda: "hi"
    group_event.raw_message = "hi"
    group_event.group_id = 555
    await gate.message_scrub_global_hook(SimpleNamespace(), group_event)
    assert captured["group_id"] == 555

    private_event = _FakeMessageEvent()
    private_event.get_plaintext = lambda: "hi"
    private_event.raw_message = "hi"
    await gate.message_scrub_global_hook(SimpleNamespace(), private_event)
    assert captured["group_id"] is None


# ---------------------------------------------------------------------------
# API 与写路径
# ---------------------------------------------------------------------------


def test_group_config_patch_accepts_and_normalizes() -> None:
    from packages.pb_webui.instances_configs_api import _GroupConfigPatch

    body = _GroupConfigPatch(message_scrub_extra=[" Bad ", "bad", "word"])
    assert body.message_scrub_extra == ["Bad", "word"]


def test_group_config_patch_rejects_over_limit() -> None:
    from pydantic import ValidationError

    from packages.pb_webui.instances_configs_api import _GroupConfigPatch

    with pytest.raises(ValidationError):
        _GroupConfigPatch(message_scrub_extra=[f"w{i}" for i in range(201)])


def test_group_config_patch_rejects_non_string() -> None:
    from pydantic import ValidationError

    from packages.pb_webui.instances_configs_api import _GroupConfigPatch

    with pytest.raises(ValidationError):
        _GroupConfigPatch(message_scrub_extra=[1])


@pytest.mark.asyncio
async def test_apply_group_config_patch_saves_and_patches_memory(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    from packages.pb_webui.instances_configs_api import _apply_group_config_patch, _GroupConfigPatch

    row = SimpleNamespace(
        group_id=11,
        roulette_mode=1,
        banned=False,
        sing_progress=None,
        disabled_plugins=[],
        disabled_plugins_audit=[],
        blocked_user_ids=[],
        style_profile=None,
        message_scrub_extra=[],
    )
    saved = _install_fake_group_repo(monkeypatch, row)

    data = await _apply_group_config_patch(11, _GroupConfigPatch(message_scrub_extra=["Term"]))

    assert saved["fields"]["message_scrub_extra"] == ["Term"]
    assert data["message_scrub_extra"] == ["Term"]
    assert is_message_scrub_blocked_sync(plain_text="term", raw_message="", group_id=11)


@pytest.mark.asyncio
async def test_db_write_path_saves_and_patches_memory(monkeypatch: pytest.MonkeyPatch, group_scrub_env: None) -> None:
    from packages.pb_webui import db_api

    row = SimpleNamespace(
        group_id=11,
        roulette_mode=1,
        banned=False,
        sing_progress=None,
        disabled_plugins=[],
        disabled_plugins_audit=[],
        blocked_user_ids=[],
        style_profile=None,
        message_scrub_extra=[],
    )
    _install_fake_group_repo(monkeypatch, row)

    got = await db_api._upsert_db_table_row("group_config", 11, {"message_scrub_extra": ["DbWord"]})

    assert got["message_scrub_extra"] == ["DbWord"]
    assert is_message_scrub_blocked_sync(plain_text="dbword", raw_message="", group_id=11)


@pytest.mark.asyncio
async def test_db_write_path_rejects_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.pb_webui import db_api

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: object())
    with pytest.raises(ValueError, match="最多"):
        await db_api._upsert_db_table_row("group_config", 1, {"message_scrub_extra": [f"w{i}" for i in range(201)]})


# ---------------------------------------------------------------------------
# 存储形态与迁移
# ---------------------------------------------------------------------------


def test_group_config_to_public_defaults_missing_field() -> None:
    from pallas.core.foundation.db.pallas_console_data import group_config_to_public

    doc = SimpleNamespace(
        group_id=1,
        roulette_mode=1,
        banned=False,
        sing_progress=None,
        disabled_plugins=[],
        blocked_user_ids=[],
        style_profile=None,
    )
    assert group_config_to_public(doc)["message_scrub_extra"] == []


def test_group_config_to_public_returns_saved_field() -> None:
    from pallas.core.foundation.db.pallas_console_data import group_config_to_public

    doc = SimpleNamespace(
        group_id=1,
        roulette_mode=1,
        banned=False,
        sing_progress=None,
        disabled_plugins=[],
        blocked_user_ids=[],
        style_profile=None,
        message_scrub_extra=["A", "B"],
    )
    assert group_config_to_public(doc)["message_scrub_extra"] == ["A", "B"]


@pytest.mark.asyncio
async def test_mongo_group_config_defaults_empty_list(beanie_fixture) -> None:
    from pallas.core.foundation.db.modules import GroupConfigModule

    assert GroupConfigModule(group_id=1).message_scrub_extra == []


def test_pg_group_config_row_defaults_empty_list() -> None:
    from pallas.core.foundation.db.repository_pg import GroupConfigRow

    row = GroupConfigRow(group_id=1)
    assert row.message_scrub_extra in (None, [])


def test_schema_ensure_step_registered() -> None:
    from pallas.core.foundation.db.schema_registry import list_pg_schema_ensure_steps

    ids = {s["id"] for s in list_pg_schema_ensure_steps()}
    assert "ddl.group_config_message_scrub_extra" in ids


def test_ensure_adds_column_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.core.foundation.db.repository_pg import lifecycle

    calls: list[str] = []

    class _Conn:
        def execute(self, stmt):
            calls.append(str(stmt))

    class _Insp:
        def has_table(self, name: str) -> bool:
            return True

        def get_columns(self, name: str):
            return [{"name": "group_id"}]

    monkeypatch.setattr(lifecycle._repo, "inspect", lambda conn: _Insp())
    lifecycle._ensure_pg_group_config_message_scrub_extra(_Conn())
    assert any("message_scrub_extra" in c for c in calls)


def test_ensure_idempotent_when_column_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.core.foundation.db.repository_pg import lifecycle

    calls: list[str] = []

    class _Conn:
        def execute(self, stmt):
            calls.append(str(stmt))

    class _Insp:
        def has_table(self, name: str) -> bool:
            return True

        def get_columns(self, name: str):
            return [{"name": "group_id"}, {"name": "message_scrub_extra"}]

    monkeypatch.setattr(lifecycle._repo, "inspect", lambda conn: _Insp())
    lifecycle._ensure_pg_group_config_message_scrub_extra(_Conn())
    assert calls == []


# ---------------------------------------------------------------------------
# 补：两写路径清空 / 其他字段不清词 / init 版本保护 / 删除清理 / HTTP
# ---------------------------------------------------------------------------


def _group_row(group_id: int = 11, **overrides):
    values = {
        "group_id": group_id,
        "roulette_mode": 1,
        "banned": False,
        "sing_progress": None,
        "disabled_plugins": [],
        "disabled_plugins_audit": [],
        "blocked_user_ids": [],
        "style_profile": None,
        "message_scrub_extra": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_patch_other_field_keeps_words_and_empty_list_clears(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    from packages.pb_webui.instances_configs_api import _apply_group_config_patch, _GroupConfigPatch

    row = _group_row(message_scrub_extra=["Keep"])
    _install_fake_group_repo(monkeypatch, row)
    group_extra.apply_group_scrub_extra_local(11, ["Keep"])

    await _apply_group_config_patch(11, _GroupConfigPatch(roulette_mode=0))
    assert is_message_scrub_blocked_sync(plain_text="keep", raw_message="", group_id=11)

    await _apply_group_config_patch(11, _GroupConfigPatch(message_scrub_extra=[]))
    assert not is_message_scrub_blocked_sync(plain_text="keep", raw_message="", group_id=11)


@pytest.mark.asyncio
async def test_db_write_other_field_keeps_words_and_empty_list_clears(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    from packages.pb_webui import db_api

    row = _group_row(message_scrub_extra=["Keep"])
    _install_fake_group_repo(monkeypatch, row)
    group_extra.apply_group_scrub_extra_local(11, ["Keep"])

    await db_api._upsert_db_table_row("group_config", 11, {"roulette_mode": 0})
    assert is_message_scrub_blocked_sync(plain_text="keep", raw_message="", group_id=11)

    got = await db_api._upsert_db_table_row("group_config", 11, {"message_scrub_extra": []})
    assert got["message_scrub_extra"] == []
    assert not is_message_scrub_blocked_sync(plain_text="keep", raw_message="", group_id=11)


@pytest.mark.asyncio
async def test_init_does_not_override_patch_made_during_load(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _Repo:
        async def list_all(self):
            started.set()
            await release.wait()
            return [SimpleNamespace(group_id=3, message_scrub_extra=["fromdb"])]

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())
    task = asyncio.create_task(group_extra.init_group_scrub_snapshot())
    await started.wait()
    group_extra.apply_group_scrub_extra_local(3, ["fresh"])
    release.set()
    await task

    assert is_message_scrub_blocked_sync(plain_text="fresh", raw_message="", group_id=3)
    assert not is_message_scrub_blocked_sync(plain_text="fromdb", raw_message="", group_id=3)


@pytest.mark.asyncio
async def test_async_global_off_skips_remote_and_group_words(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    monkeypatch.setenv("PALLAS_MESSAGE_SCRUB_ENABLED", "false")
    reload_message_scrub_caches()
    group_extra.apply_group_scrub_extra_local(7, ["badterm"])
    remote = AsyncMock(side_effect=AssertionError("remote must not run when globally off"))
    monkeypatch.setattr("pallas.product.message_scrub.run_review_chain", remote)

    assert not await is_message_scrub_blocked_async(plain_text="badterm", raw_message="", group_id=7)
    remote.assert_not_called()


def test_group_words_match_raw_message_and_stay_isolated(group_scrub_env: None) -> None:
    group_extra.apply_group_scrub_extra_local(1, ["cqword"])
    raw = "[CQ:at,qq=1] cqword"

    assert is_message_scrub_blocked_sync(plain_text="", raw_message=raw, group_id=1)
    assert not is_message_scrub_blocked_sync(plain_text="", raw_message=raw, group_id=2)
    assert not is_message_scrub_blocked_sync(plain_text="", raw_message=raw)


@pytest.mark.asyncio
async def test_delete_group_config_mongo_clears_snapshot(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    from packages.pb_webui import db_api

    group_extra.apply_group_scrub_extra_local(11, ["gone"])

    class _Doc:
        async def delete(self):
            return None

    class _Model:
        @staticmethod
        async def find_one(query):  # noqa: ARG004
            return _Doc()

    monkeypatch.setattr(db_api, "_release_config_derived_acl", AsyncMock())
    monkeypatch.setattr("pallas.core.foundation.db.get_db_backend", lambda: "mongodb")
    monkeypatch.setattr("pallas.core.foundation.db.modules.GroupConfigModule", _Model)

    assert await db_api._delete_db_table_row("group_config", 11) is True
    assert not is_message_scrub_blocked_sync(plain_text="gone", raw_message="", group_id=11)


@pytest.mark.asyncio
async def test_delete_group_config_mongo_absent_clears_snapshot(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    from packages.pb_webui import db_api

    group_extra.apply_group_scrub_extra_local(11, ["gone"])

    class _Model:
        @staticmethod
        async def find_one(query):  # noqa: ARG004
            return None

    monkeypatch.setattr(db_api, "_release_config_derived_acl", AsyncMock())
    monkeypatch.setattr("pallas.core.foundation.db.get_db_backend", lambda: "mongodb")
    monkeypatch.setattr("pallas.core.foundation.db.modules.GroupConfigModule", _Model)

    assert await db_api._delete_db_table_row("group_config", 11) is False
    assert not is_message_scrub_blocked_sync(plain_text="gone", raw_message="", group_id=11)


@pytest.mark.asyncio
async def test_delete_group_config_pg_clears_snapshot(monkeypatch: pytest.MonkeyPatch, group_scrub_env: None) -> None:
    from packages.pb_webui import db_api

    group_extra.apply_group_scrub_extra_local(11, ["gone"])

    class _Result:
        rowcount = 1

    class _Session:
        async def execute(self, stmt):  # noqa: ARG002
            return _Result()

        async def commit(self):
            return None

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(db_api, "_release_config_derived_acl", AsyncMock())
    monkeypatch.setattr("pallas.core.foundation.db.get_db_backend", lambda: "postgres")
    monkeypatch.setattr("pallas.core.foundation.db.repository_pg.get_session", lambda **kwargs: _Ctx())

    assert await db_api._delete_db_table_row("group_config", 11) is True
    assert not is_message_scrub_blocked_sync(plain_text="gone", raw_message="", group_id=11)


@pytest.mark.asyncio
async def test_delete_group_config_failure_keeps_snapshot(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    from packages.pb_webui import db_api

    group_extra.apply_group_scrub_extra_local(11, ["gone"])

    class _Model:
        @staticmethod
        async def find_one(query):  # noqa: ARG004
            raise RuntimeError("db error")

    monkeypatch.setattr(db_api, "_release_config_derived_acl", AsyncMock())
    monkeypatch.setattr("pallas.core.foundation.db.get_db_backend", lambda: "mongodb")
    monkeypatch.setattr("pallas.core.foundation.db.modules.GroupConfigModule", _Model)

    with pytest.raises(RuntimeError, match="db error"):
        await db_api._delete_db_table_row("group_config", 11)
    assert is_message_scrub_blocked_sync(plain_text="gone", raw_message="", group_id=11)


def test_group_config_patch_openapi_declares_scrub_limits() -> None:
    from packages.pb_webui.config import Config
    from packages.pb_webui.instances_configs_api import register_instances_configs_router

    app = FastAPI()
    register_instances_configs_router(app.router, x="/pallas/api", plugin_config=Config())
    prop = app.openapi()["components"]["schemas"]["_GroupConfigPatch"]["properties"]["message_scrub_extra"]
    array = next(branch for branch in prop["anyOf"] if branch.get("type") == "array")
    assert array["maxItems"] == 200
    assert array["items"]["maxLength"] == 64


@pytest.mark.asyncio
async def test_group_config_endpoint_put_get_message_scrub_extra(
    monkeypatch: pytest.MonkeyPatch, group_scrub_env: None
) -> None:
    from packages.pb_webui import instances_configs_api as api
    from packages.pb_webui.config import Config

    row = _group_row(group_id=7)

    class _Repo:
        async def get_or_create(self, gid, **kwargs):  # noqa: ARG002
            return row, False

        async def get(self, gid, *, ignore_cache: bool = False):  # noqa: ARG002
            return row

        async def upsert_fields(self, gid, fields):  # noqa: ARG002
            for k, v in fields.items():
                setattr(row, k, v)

    monkeypatch.setattr(api, "check_pallas_write_token", lambda *a, **k: None)
    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())
    app = FastAPI()
    api.register_instances_configs_router(app.router, x="/pallas/api", plugin_config=Config())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        put_ok = await client.put(
            "/pallas/api/group-configs/7",
            json={"message_scrub_extra": [" Term ", "term", "x"]},
        )
        assert put_ok.status_code == 200
        assert put_ok.json()["data"]["message_scrub_extra"] == ["Term", "x"]
        assert is_message_scrub_blocked_sync(plain_text="term", raw_message="", group_id=7)

        get_ok = await client.get("/pallas/api/group-configs/7")
        assert get_ok.status_code == 200
        assert get_ok.json()["data"]["message_scrub_extra"] == ["Term", "x"]

        put_other = await client.put("/pallas/api/group-configs/7", json={"roulette_mode": 0})
        assert put_other.status_code == 200
        assert put_other.json()["data"]["message_scrub_extra"] == ["Term", "x"]

        put_over = await client.put(
            "/pallas/api/group-configs/7",
            json={"message_scrub_extra": [f"w{i}" for i in range(201)]},
        )
        assert put_over.status_code == 422

        put_non_string = await client.put("/pallas/api/group-configs/7", json={"message_scrub_extra": [1]})
        assert put_non_string.status_code == 422

        put_clear = await client.put("/pallas/api/group-configs/7", json={"message_scrub_extra": []})
        assert put_clear.status_code == 200
        assert put_clear.json()["data"]["message_scrub_extra"] == []
        assert not is_message_scrub_blocked_sync(plain_text="term", raw_message="", group_id=7)
