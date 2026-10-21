from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace

import pytest

from pallas.product.llm.config import LlmConfig
from pallas.product.llm.session_models import SESSION_SUMMARY_PREFIX
from pallas.product.llm.session_store_pg import PgLlmSessionMessageBackend
from pallas.product.llm.session_summary import (
    clear_session_summary_state_for_tests,
    maybe_compact_session_history,
)


class FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


def _matches_scope(sql: str, row) -> bool:
    for field in ("bot_id", "group_id", "user_id"):
        match = re.search(rf"\b{field} = (\d+)", sql)
        if match is not None and int(getattr(row, field)) != int(match.group(1)):
            return False
    match = re.search(r"\bcreated_at >= (\d+)", sql)
    if match is not None and int(row.created_at) < int(match.group(1)):
        return False
    match = re.search(r"\bid IN \(([^)]*)\)", sql)
    if match is not None:
        ids = {int(item) for item in re.findall(r"\d+", match.group(1))}
        if int(row.id) not in ids:
            return False
    return True


class FakePgSession:
    def __init__(self, db: FakePgDatabase) -> None:
        self.db = db
        self.pending_deleted: list = []
        self.pending_inserted: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, statement):
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        if sql.lstrip().startswith("SELECT"):
            self.db.last_select_sql = sql
            rows = [row for row in self.db.rows if _matches_scope(sql, row)]
            order = re.search(
                r"ORDER BY llm_chat_message\.created_at (ASC|DESC), llm_chat_message\.id (ASC|DESC)",
                sql,
            )
            if order is not None:
                rows.sort(
                    key=lambda row: (int(row.created_at), int(row.id)),
                    reverse=order.group(1) == "DESC",
                )
            limit = re.search(r"\bLIMIT (\d+)", sql)
            if limit is not None:
                rows = rows[: int(limit.group(1))]
            return FakeResult(rows)
        if "DELETE FROM llm_chat_message" in sql:
            self.db.last_delete_sql = sql
            rows = [row for row in self.db.rows if _matches_scope(sql, row)]
            self.pending_deleted.extend(rows)
            return FakeResult([row.id for row in rows])
        raise AssertionError(f"unexpected SQL: {sql}")

    def add(self, row) -> None:
        self.pending_inserted.append(row)

    async def commit(self) -> None:
        if self.db.fail_next_commit:
            self.db.fail_next_commit = False
            raise RuntimeError("commit failed")
        deleted_ids = {row.id for row in self.pending_deleted}
        self.db.rows = [row for row in self.db.rows if row.id not in deleted_ids]
        for row in self.pending_inserted:
            if getattr(row, "id", None) is None:
                row.id = self.db.next_id
                self.db.next_id += 1
            self.db.rows.append(row)
        self.pending_deleted.clear()
        self.pending_inserted.clear()
        self.db.commits += 1

    async def rollback(self) -> None:
        self.pending_deleted.clear()
        self.pending_inserted.clear()
        self.db.rollbacks += 1


class FakePgDatabase:
    def __init__(self, rows: list) -> None:
        self.rows = list(rows)
        self.next_id = max((int(row.id) for row in rows), default=0) + 1
        self.fail_next_commit = False
        self.commits = 0
        self.rollbacks = 0
        self.last_select_sql = ""
        self.last_delete_sql = ""

    def session(self, **_kwargs) -> FakePgSession:
        return FakePgSession(self)


def pg_row(
    row_id: int,
    *,
    bot_id: int = 1,
    group_id: int = 2,
    user_id: int = 3,
    role: str = "user",
    content: str | None = None,
    created_at: int | None = None,
):
    return SimpleNamespace(
        id=row_id,
        bot_id=bot_id,
        group_id=group_id,
        user_id=user_id,
        role=role,
        content=content if content is not None else f"m-{row_id}",
        created_at=row_id if created_at is None else created_at,
    )


def install_fake_db(monkeypatch: pytest.MonkeyPatch, db: FakePgDatabase, *, now: int = 1000) -> None:
    monkeypatch.setattr(
        "pallas.product.llm.session_store_pg.get_session",
        lambda **kwargs: db.session(**kwargs),
    )
    monkeypatch.setattr("pallas.product.llm.session_store_pg.time.time", lambda: now)


@pytest.mark.asyncio
async def test_pg_snapshot_uses_limit_plus_one_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakePgDatabase([
        pg_row(1, created_at=90),
        pg_row(2, created_at=99),
        pg_row(3, created_at=100),
        pg_row(4, created_at=101),
    ])
    install_fake_db(monkeypatch, db, now=100)
    backend = PgLlmSessionMessageBackend()

    snapshot = await backend.read_user_compaction_snapshot(1, 2, 3, limit=10, ttl_sec=2)
    assert [turn.message_id for turn in snapshot] == ["2", "3", "4"]
    assert "ORDER BY llm_chat_message.created_at DESC, llm_chat_message.id DESC" in db.last_select_sql
    assert "LIMIT 11" in db.last_select_sql
    assert "created_at >= 98" in db.last_select_sql

    assert await backend.read_user_compaction_snapshot(1, 2, 3, limit=3, ttl_sec=0) is None


@pytest.mark.asyncio
async def test_pg_snapshot_orders_same_second_by_id(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakePgDatabase([
        pg_row(12, created_at=50),
        pg_row(10, created_at=50),
        pg_row(11, created_at=50),
    ])
    install_fake_db(monkeypatch, db)
    backend = PgLlmSessionMessageBackend()

    snapshot = await backend.read_user_compaction_snapshot(1, 2, 3, limit=10, ttl_sec=0)
    assert [turn.message_id for turn in snapshot] == ["10", "11", "12"]


@pytest.mark.asyncio
async def test_pg_compact_deletes_only_source_ids_and_inserts_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakePgDatabase([
        pg_row(i, content=f"{SESSION_SUMMARY_PREFIX}旧摘要" if i == 1 else f"m-{i}") for i in range(1, 11)
    ])
    install_fake_db(monkeypatch, db)
    backend = PgLlmSessionMessageBackend()

    assert await backend.compact_user_with_summary(
        1,
        2,
        3,
        f"{SESSION_SUMMARY_PREFIX}新摘要",
        keep_messages=2,
        source_message_ids=[str(i) for i in range(1, 7)],
        summary_created_at=6,
    )
    remaining_ids = [int(row.id) for row in db.rows if int(row.id) < 11]
    assert remaining_ids == [7, 8, 9, 10]
    summary = [row for row in db.rows if int(row.id) >= 11]
    assert len(summary) == 1
    assert summary[0].content == f"{SESSION_SUMMARY_PREFIX}新摘要"
    assert summary[0].created_at == 6
    assert "bot_id = 1" in db.last_delete_sql
    assert "group_id = 2" in db.last_delete_sql
    assert "user_id = 3" in db.last_delete_sql
    assert "id IN (1, 2, 3, 4, 5, 6)" in db.last_delete_sql
    assert "RETURNING" in db.last_delete_sql
    assert db.last_select_sql == ""
    assert db.commits == 1


@pytest.mark.asyncio
async def test_pg_compact_missing_source_id_rolls_back_without_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [pg_row(i) for i in range(1, 6)]
    db = FakePgDatabase(rows)
    install_fake_db(monkeypatch, db)
    backend = PgLlmSessionMessageBackend()

    assert not await backend.compact_user_with_summary(
        1,
        2,
        3,
        f"{SESSION_SUMMARY_PREFIX}摘要",
        keep_messages=2,
        source_message_ids=["1", "2", "999"],
        summary_created_at=0,
    )
    assert db.rows == rows
    assert db.rollbacks == 1
    assert db.commits == 0


@pytest.mark.asyncio
async def test_pg_compact_insert_failure_rolls_back_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [pg_row(i) for i in range(1, 5)]
    db = FakePgDatabase(rows)
    db.fail_next_commit = True
    install_fake_db(monkeypatch, db)
    backend = PgLlmSessionMessageBackend()

    assert not await backend.compact_user_with_summary(
        1,
        2,
        3,
        f"{SESSION_SUMMARY_PREFIX}摘要",
        keep_messages=2,
        source_message_ids=["1", "2"],
        summary_created_at=0,
    )
    assert db.rows == rows
    assert db.rollbacks >= 1


@pytest.mark.asyncio
async def test_pg_compact_rejects_invalid_ids_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [pg_row(i) for i in range(1, 4)]
    db = FakePgDatabase(rows)
    install_fake_db(monkeypatch, db)
    backend = PgLlmSessionMessageBackend()

    assert not await backend.compact_user_with_summary(
        1,
        2,
        3,
        f"{SESSION_SUMMARY_PREFIX}摘要",
        keep_messages=2,
        source_message_ids=["1", "abc"],
        summary_created_at=0,
    )
    assert db.rows == rows
    assert db.last_delete_sql == ""


@pytest.mark.asyncio
async def test_pg_compact_same_second_and_cross_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakePgDatabase([
        pg_row(10, created_at=50),
        pg_row(11, created_at=50),
        pg_row(12, created_at=50),
        pg_row(20, user_id=4, created_at=50),
        pg_row(21, group_id=9, created_at=50),
    ])
    install_fake_db(monkeypatch, db)
    backend = PgLlmSessionMessageBackend()

    snapshot = await backend.read_user_compaction_snapshot(1, 2, 3, limit=10, ttl_sec=0)
    assert [turn.message_id for turn in snapshot] == ["10", "11", "12"]

    assert await backend.compact_user_with_summary(
        1,
        2,
        3,
        f"{SESSION_SUMMARY_PREFIX}摘要",
        keep_messages=1,
        source_message_ids=["10", "12"],
        summary_created_at=49,
    )
    remaining_ids = {int(row.id) for row in db.rows if int(row.id) < 20}
    assert remaining_ids == {11}
    other_scope_ids = {int(row.id) for row in db.rows if int(row.id) in {20, 21}}
    assert other_scope_ids == {20, 21}


@pytest.mark.asyncio
async def test_pg_compact_leaves_ttl_expired_rows_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakePgDatabase([
        pg_row(1, content="expired", created_at=90),
        pg_row(2, content="current", created_at=100),
    ])
    install_fake_db(monkeypatch, db, now=100)
    backend = PgLlmSessionMessageBackend()

    snapshot = await backend.read_user_compaction_snapshot(1, 2, 3, limit=10, ttl_sec=5)
    assert [turn.message_id for turn in snapshot] == ["2"]
    assert await backend.compact_user_with_summary(
        1,
        2,
        3,
        f"{SESSION_SUMMARY_PREFIX}摘要",
        keep_messages=1,
        source_message_ids=["2"],
        summary_created_at=99,
    )
    assert any(int(row.id) == 1 and row.content == "expired" for row in db.rows)
    assert not any(int(row.id) == 2 for row in db.rows)


def install_session_summary_backend(
    monkeypatch: pytest.MonkeyPatch,
    db: FakePgDatabase,
    cfg: LlmConfig,
) -> None:
    install_fake_db(monkeypatch, db)
    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)
    monkeypatch.setattr("pallas.product.llm.session_store.session_store_backend_ready", lambda: True)
    monkeypatch.setattr(
        "pallas.product.llm.session_store.resolve_session_backend",
        lambda: PgLlmSessionMessageBackend(),
    )


@pytest.mark.asyncio
async def test_pg_automatic_compaction_freezes_keep_during_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_session_summary_state_for_tests()
    db = FakePgDatabase([pg_row(i, content=f"问{i}", created_at=i) for i in range(1, 51)])
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_summary_enabled=True,
        llm_session_summary_threshold=24,
        llm_session_summary_keep_messages=8,
        llm_session_summary_cooldown_sec=0,
        llm_session_user_storage_window=200,
        llm_session_user_window=18,
    )
    install_session_summary_backend(monkeypatch, db, cfg)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_complete(*_a, **_k):
        started.set()
        await release.wait()
        return {"content": "冻结快照摘要"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)

    task = asyncio.create_task(maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg))
    await asyncio.wait_for(started.wait(), timeout=5)
    for index in range(20):
        db.rows.append(pg_row(100 + index, content=f"新问{index}", created_at=100 + index))
    release.set()
    assert await asyncio.wait_for(task, timeout=5) is True

    contents = {row.content for row in db.rows}
    assert {f"新问{index}" for index in range(20)}.issubset(contents)
    assert {f"问{index}" for index in range(43, 51)}.issubset(contents)
    assert not any(f"问{index}" in contents for index in range(1, 43))
    assert len(db.rows) == 29
    expected_ids = ", ".join(str(index) for index in range(1, 43))
    assert f"id IN ({expected_ids})" in db.last_delete_sql


@pytest.mark.asyncio
async def test_pg_consecutive_compaction_inherits_prior_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_session_summary_state_for_tests()
    rows = []
    for index in range(25):
        rows.append(pg_row(index * 2 + 1, content=f"问{index}", created_at=index * 2))
        rows.append(pg_row(index * 2 + 2, role="assistant", content=f"答{index}", created_at=index * 2 + 1))
    db = FakePgDatabase(rows)
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_summary_enabled=True,
        llm_session_summary_threshold=24,
        llm_session_summary_keep_messages=8,
        llm_session_summary_cooldown_sec=0,
        llm_session_user_storage_window=200,
        llm_session_user_window=18,
    )
    install_session_summary_backend(monkeypatch, db, cfg)
    transcripts: list[str] = []

    async def fake_complete(messages, **_k):
        transcripts.append(str(messages[1]["content"]))
        return {"content": f"摘要第{len(transcripts)}版"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    for index in range(25, 50):
        db.rows.append(pg_row(100 + index * 2, content=f"问{index}", created_at=index * 2))
        db.rows.append(pg_row(100 + index * 2 + 1, role="assistant", content=f"答{index}", created_at=index * 2 + 1))

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert len(transcripts) == 2
    assert "摘要第1版" in transcripts[1]
    summaries = [row for row in db.rows if row.content.startswith(SESSION_SUMMARY_PREFIX)]
    assert len(summaries) == 1
    assert "摘要第2版" in summaries[0].content


@pytest.mark.asyncio
async def test_pg_legacy_compact_without_source_ids_keeps_last_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakePgDatabase([pg_row(i, content=f"m-{i}", created_at=i) for i in range(1, 6)])
    install_fake_db(monkeypatch, db, now=1000)
    backend = PgLlmSessionMessageBackend()

    assert await backend.compact_user_with_summary(
        1,
        2,
        3,
        f"{SESSION_SUMMARY_PREFIX}旧式摘要",
        keep_messages=2,
    )
    contents = {row.content for row in db.rows}
    assert {"m-4", "m-5"}.issubset(contents)
    assert not any(content in contents for content in ("m-1", "m-2", "m-3"))
    assert any(str(row.content).startswith(SESSION_SUMMARY_PREFIX) for row in db.rows)


@pytest.mark.asyncio
async def test_pg_automatic_compaction_over_window_skips_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_session_summary_state_for_tests()
    db = FakePgDatabase([pg_row(i, content=f"问{i}", created_at=i) for i in range(1, 26)])
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_summary_enabled=True,
        llm_session_summary_threshold=24,
        llm_session_summary_keep_messages=8,
        llm_session_summary_cooldown_sec=0,
        llm_session_user_storage_window=24,
        llm_session_user_window=18,
    )
    install_session_summary_backend(monkeypatch, db, cfg)
    complete_calls = 0

    async def fake_complete(*_a, **_k):
        nonlocal complete_calls
        complete_calls += 1
        return {"content": "不应生成"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    before = list(db.rows)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False
    assert complete_calls == 0
    assert db.rows == before
    assert db.last_delete_sql == ""
