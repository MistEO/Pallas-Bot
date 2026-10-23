"""message_scrub Bot 级追加屏蔽词：快照、隔离、校验、存储与迁移。"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pallas.product.message_scrub import (
    bot_scrub_extra_hits,
    group_extra,
    is_message_scrub_blocked_async,
    is_message_scrub_blocked_sync,
    reload_message_scrub_caches,
)


@pytest.fixture
def scrub_env(monkeypatch: pytest.MonkeyPatch):
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
    group_extra.reset_bot_scrub_snapshot()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    reload_message_scrub_caches()
    group_extra.reset_group_scrub_snapshot()
    group_extra.reset_bot_scrub_snapshot()


def _install_fake_bot_repo(monkeypatch: pytest.MonkeyPatch, rows=None) -> None:
    class _Repo:
        async def list_all(self):
            return list(rows or [])

    monkeypatch.setattr("pallas.core.foundation.db.make_bot_config_repository", lambda: _Repo())


# ---------------------------------------------------------------------------
# 快照作用域与隔离
# ---------------------------------------------------------------------------


def test_bot_words_apply_to_all_groups_and_private(scrub_env: None) -> None:
    group_extra.apply_bot_scrub_extra_local(100, ["BotWord"])

    # 同一 Bot 的所有群与私聊（bot_id 传当前 Bot，group_id 可空）
    assert is_message_scrub_blocked_sync(plain_text="botword", raw_message="", group_id=1, bot_id=100)
    assert is_message_scrub_blocked_sync(plain_text="BOTWORD", raw_message="", group_id=2, bot_id=100)
    assert is_message_scrub_blocked_sync(plain_text="botword", raw_message="", bot_id=100)
    # 其他 Bot 不受影响
    assert not is_message_scrub_blocked_sync(plain_text="botword", raw_message="", group_id=1, bot_id=200)
    assert not is_message_scrub_blocked_sync(plain_text="botword", raw_message="", bot_id=200)


def test_missing_bot_id_does_not_pick_any_bot(scrub_env: None) -> None:
    group_extra.apply_bot_scrub_extra_local(100, ["BotWord"])
    # 未传 bot_id：不选任意 Bot，保持旧行为
    assert not is_message_scrub_blocked_sync(plain_text="botword", raw_message="", group_id=1)
    assert bot_scrub_extra_hits(bot_id=None, plain_text="botword", raw_message="") is False


def test_group_and_bot_same_numeric_id_do_not_cross(scrub_env: None) -> None:
    group_extra.apply_group_scrub_extra_local(5, ["GroupOnly"])
    group_extra.apply_bot_scrub_extra_local(5, ["BotOnly"])

    assert is_message_scrub_blocked_sync(plain_text="grouponly", raw_message="", group_id=5, bot_id=5)
    assert is_message_scrub_blocked_sync(plain_text="botonly", raw_message="", group_id=5, bot_id=5)
    # 群 5 命中不应来自 Bot 词，Bot 5 命中不应来自群词
    assert not is_message_scrub_blocked_sync(plain_text="botonly", raw_message="", group_id=5)
    assert not is_message_scrub_blocked_sync(plain_text="grouponly", raw_message="", bot_id=5)


def test_bot_word_removal_does_not_weaken_global_or_group(scrub_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PALLAS_INBOUND_FILTER_SUBSTRINGS", "globalword")
    reload_message_scrub_caches()
    group_extra.apply_group_scrub_extra_local(7, ["groupword"])
    group_extra.apply_bot_scrub_extra_local(100, ["botword"])

    group_extra.apply_bot_scrub_extra_local(100, [])
    assert is_message_scrub_blocked_sync(plain_text="globalword", raw_message="", group_id=7, bot_id=100)
    assert is_message_scrub_blocked_sync(plain_text="groupword", raw_message="", group_id=7, bot_id=100)
    assert not is_message_scrub_blocked_sync(plain_text="botword", raw_message="", group_id=7, bot_id=100)


def test_global_off_disables_bot_words(scrub_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PALLAS_MESSAGE_SCRUB_ENABLED", "false")
    reload_message_scrub_caches()
    group_extra.apply_bot_scrub_extra_local(100, ["botword"])
    assert not is_message_scrub_blocked_sync(plain_text="botword", raw_message="", group_id=1, bot_id=100)


@pytest.mark.asyncio
async def test_async_bot_hit_skips_remote(scrub_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    group_extra.apply_bot_scrub_extra_local(100, ["badterm"])
    remote = AsyncMock(side_effect=AssertionError("remote must not run on bot hit"))
    monkeypatch.setattr("pallas.product.message_scrub.run_review_chain", remote)

    assert await is_message_scrub_blocked_async(plain_text="BADTERM", raw_message="", bot_id=100)
    remote.assert_not_called()


def test_bot_words_match_raw_message(scrub_env: None) -> None:
    group_extra.apply_bot_scrub_extra_local(100, ["cqword"])
    raw = "[CQ:at,qq=1] cqword"
    assert is_message_scrub_blocked_sync(plain_text="", raw_message=raw, group_id=1, bot_id=100)
    assert not is_message_scrub_blocked_sync(plain_text="", raw_message=raw, group_id=1, bot_id=200)


# ---------------------------------------------------------------------------
# 刷新：成功替换 / 失败保留 / 独立 / 旧 load 不覆盖 patch / 清空不复活
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_bot_snapshot_loads_and_scopes(scrub_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        SimpleNamespace(account=100, message_scrub_extra=["Alpha"]),
        SimpleNamespace(account=200, message_scrub_extra=[]),
    ]
    _install_fake_bot_repo(monkeypatch, rows)
    await group_extra.init_bot_scrub_snapshot()

    assert is_message_scrub_blocked_sync(plain_text="alpha", raw_message="", bot_id=100)
    assert not is_message_scrub_blocked_sync(plain_text="alpha", raw_message="", bot_id=200)


@pytest.mark.asyncio
async def test_bot_refresh_failure_keeps_old_and_group_unaffected(
    scrub_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    group_extra.apply_bot_scrub_extra_local(100, ["keepme"])
    group_extra.apply_group_scrub_extra_local(9, ["groupkeep"])

    class _BotRepo:
        async def list_all(self):
            raise RuntimeError("db down")

    monkeypatch.setattr("pallas.core.foundation.db.make_bot_config_repository", lambda: _BotRepo())
    await group_extra.refresh_bot_scrub_snapshot_once()

    assert is_message_scrub_blocked_sync(plain_text="keepme", raw_message="", bot_id=100)
    assert is_message_scrub_blocked_sync(plain_text="groupkeep", raw_message="", group_id=9)


@pytest.mark.asyncio
async def test_group_refresh_failure_keeps_group_and_bot_unaffected(
    scrub_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    group_extra.apply_group_scrub_extra_local(9, ["groupkeep"])
    group_extra.apply_bot_scrub_extra_local(100, ["botkeep"])

    class _GroupRepo:
        async def list_all(self):
            raise RuntimeError("db down")

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _GroupRepo())
    await group_extra.refresh_group_scrub_snapshot_once()

    assert is_message_scrub_blocked_sync(plain_text="groupkeep", raw_message="", group_id=9)
    assert is_message_scrub_blocked_sync(plain_text="botkeep", raw_message="", bot_id=100)


@pytest.mark.asyncio
async def test_stale_bot_refresh_does_not_override_local_patch(
    scrub_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _Repo:
        async def list_all(self):
            started.set()
            await release.wait()
            return [SimpleNamespace(account=100, message_scrub_extra=["fromdb"])]

    monkeypatch.setattr("pallas.core.foundation.db.make_bot_config_repository", lambda: _Repo())
    task = asyncio.create_task(group_extra.refresh_bot_scrub_snapshot_once())
    await started.wait()
    group_extra.apply_bot_scrub_extra_local(100, ["fresh"])
    release.set()
    await task

    assert is_message_scrub_blocked_sync(plain_text="fresh", raw_message="", bot_id=100)
    assert not is_message_scrub_blocked_sync(plain_text="fromdb", raw_message="", bot_id=100)


@pytest.mark.asyncio
async def test_cleared_bot_snapshot_not_revived_by_old_load(scrub_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _Repo:
        async def list_all(self):
            started.set()
            await release.wait()
            return [SimpleNamespace(account=100, message_scrub_extra=["fromdb"])]

    monkeypatch.setattr("pallas.core.foundation.db.make_bot_config_repository", lambda: _Repo())
    task = asyncio.create_task(group_extra.refresh_bot_scrub_snapshot_once())
    await started.wait()
    group_extra.apply_bot_scrub_extra_local(100, [])  # 清空并增版本
    release.set()
    await task

    assert not is_message_scrub_blocked_sync(plain_text="fromdb", raw_message="", bot_id=100)


@pytest.mark.asyncio
async def test_init_bot_tolerates_dirty_stored_rows(scrub_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [SimpleNamespace(account=100, message_scrub_extra=["ok", 5, "  ", "x" * 65, "OK"])]
    _install_fake_bot_repo(monkeypatch, rows)
    await group_extra.init_bot_scrub_snapshot()
    assert is_message_scrub_blocked_sync(plain_text="ok", raw_message="", bot_id=100)


# ---------------------------------------------------------------------------
# 存储形态与迁移
# ---------------------------------------------------------------------------


def test_mongo_bot_config_defaults_empty_list(beanie_fixture) -> None:
    from pallas.core.foundation.db.modules import BotConfigModule

    assert BotConfigModule(account=1).message_scrub_extra == []


def test_pg_bot_config_row_defaults_empty_list() -> None:
    from pallas.core.foundation.db.repository_pg import BotConfigRow

    row = BotConfigRow(account=1)
    assert row.message_scrub_extra in (None, [])


def test_bot_schema_ensure_step_registered() -> None:
    from pallas.core.foundation.db.schema_registry import list_pg_schema_ensure_steps

    ids = {s["id"] for s in list_pg_schema_ensure_steps()}
    assert "ddl.bot_config_message_scrub_extra" in ids


def test_bot_ensure_adds_column_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.core.foundation.db.repository_pg import lifecycle

    calls: list[str] = []

    class _Conn:
        def execute(self, stmt):
            calls.append(str(stmt))

    class _Insp:
        def has_table(self, name: str) -> bool:
            return True

        def get_columns(self, name: str):
            return [{"name": "account"}]

    monkeypatch.setattr(lifecycle._repo, "inspect", lambda conn: _Insp())
    lifecycle._ensure_pg_bot_config_message_scrub_extra(_Conn())
    assert any("message_scrub_extra" in c for c in calls)


def test_bot_ensure_idempotent_when_column_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.core.foundation.db.repository_pg import lifecycle

    calls: list[str] = []

    class _Conn:
        def execute(self, stmt):
            calls.append(str(stmt))

    class _Insp:
        def has_table(self, name: str) -> bool:
            return True

        def get_columns(self, name: str):
            return [{"name": "account"}, {"name": "message_scrub_extra"}]

    monkeypatch.setattr(lifecycle._repo, "inspect", lambda conn: _Insp())
    lifecycle._ensure_pg_bot_config_message_scrub_extra(_Conn())
    assert calls == []


def test_migrate_bot_config_includes_scrub_extra() -> None:
    """运行真实 `_migrate_bot_config`（fake Mongo collection + fake session/insert），
    断言 insert 行保留词表、ON CONFLICT 更新集合含新字段、旧记录缺字段为 []。"""
    import asyncio

    import tools.migrate_mongo_to_pg as migrate

    class _FakeCursor:
        def __init__(self, docs: list[dict]) -> None:
            self._docs = docs
            self._limit = len(docs)

        def sort(self, key: str, direction: int):  # noqa: ARG002
            return self

        def limit(self, n: int):
            self._limit = n
            return self

        async def to_list(self, length: int | None = None):
            size = length if length is not None else self._limit
            return self._docs[:size]

    class _FakeCollection:
        def __init__(self, docs: list[dict]) -> None:
            self._docs = docs

        async def count_documents(self, query: dict) -> int:  # noqa: ARG002
            return len(self._docs)

        def find(self, query: dict) -> _FakeCursor:
            gt = (query.get("_id") or {}).get("$gt")
            docs = [d for d in self._docs if gt is None or str(d["_id"]) > str(gt)]
            return _FakeCursor(docs)

    class _FakeResult:
        def scalar_one_or_none(self):
            return None

    class _FakeExcluded:
        def __getattr__(self, name: str) -> str:
            return f"excluded.{name}"

    class _FakeStmt:
        def __init__(self, rows: list[dict]) -> None:
            self.rows = rows
            self.excluded = _FakeExcluded()
            self.index_elements: list[str] | None = None
            self.set_: dict | None = None

        def on_conflict_do_update(self, *, index_elements, set_):
            self.index_elements = index_elements
            self.set_ = set_
            return self

    class _FakeInsert:
        def __init__(self) -> None:
            self.stmt: _FakeStmt | None = None

        def __call__(self, row_cls):  # noqa: ARG002
            return self

        def values(self, rows: list[dict]) -> _FakeStmt:
            self.stmt = _FakeStmt(rows)
            return self.stmt

    class _FakeSession:
        def __init__(self) -> None:
            self.executed: list[object] = []
            self.committed = False

        async def execute(self, stmt, params=None):  # noqa: ARG002
            self.executed.append(stmt)
            return _FakeResult()

        async def commit(self) -> None:
            self.committed = True

    class _SessionCtx:
        def __init__(self, session: _FakeSession) -> None:
            self._session = session

        async def __aenter__(self) -> _FakeSession:
            return self._session

        async def __aexit__(self, *exc) -> bool:
            return False

    docs = [
        {"_id": "a1", "account": 100, "message_scrub_extra": ["KeepMe", "Also"]},
        {"_id": "a2", "account": 200},  # 旧记录：无新字段
    ]
    session = _FakeSession()
    insert = _FakeInsert()
    fake_db = {"config": _FakeCollection(docs)}

    stats = asyncio.run(
        migrate._migrate_bot_config(fake_db, lambda: _SessionCtx(session), object, insert, batch_size=10, dry_run=False)
    )

    assert stats.migrated == 2
    assert insert.stmt is not None
    # insert rows 保留词表；旧记录缺字段落为 []
    by_account = {row["account"]: row for row in insert.stmt.rows}
    assert by_account[100]["message_scrub_extra"] == ["KeepMe", "Also"]
    assert by_account[200]["message_scrub_extra"] == []
    # ON CONFLICT 更新集合包含新字段（且包含既有字段）
    assert insert.stmt.index_elements == ["account"]
    assert insert.stmt.set_ is not None
    assert "message_scrub_extra" in insert.stmt.set_
    assert "disabled_plugins" in insert.stmt.set_
    assert session.committed is True
