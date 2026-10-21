from __future__ import annotations

import asyncio

import pytest

from pallas.product.llm.config import LlmConfig
from pallas.product.llm.session_models import (
    SESSION_SUMMARY_MARK,
    SESSION_SUMMARY_PREFIX,
    LlmChatTurn,
    LlmSessionSnapshotTurn,
    is_session_summary_turn,
)
from pallas.product.llm.session_summary import (
    _summary_messages,
    clear_session_summary_state_for_tests,
    maybe_compact_session_history,
    session_summary_status_snapshot,
)


def summary_cfg(**overrides: object) -> LlmConfig:
    values: dict[str, object] = {
        "llm_chat_enabled": True,
        "llm_session_enabled": True,
        "llm_session_summary_enabled": True,
        "llm_session_summary_threshold": 24,
        "llm_session_summary_keep_messages": 8,
        "llm_session_summary_cooldown_sec": 0,
        "llm_session_user_storage_window": 200,
        "llm_session_user_window": 18,
        "llm_session_summary_daily_budget": 5000,
    }
    values.update(overrides)
    return LlmConfig(**values)


def snapshot_turn(
    message_id: object,
    *,
    role: str = "user",
    content: str | None = None,
    created_at: int = 0,
    user_id: int = 3,
) -> LlmSessionSnapshotTurn:
    return LlmSessionSnapshotTurn(
        role=role,
        content=content if content is not None else f"问{message_id}",
        user_id=user_id,
        created_at=created_at,
        message_id=str(message_id),
    )


def summary_history(count: int = 24) -> list[LlmSessionSnapshotTurn]:
    return [snapshot_turn(i + 1, content=f"问{i}", created_at=i) for i in range(count)]


class FakeSnapshotBackend:
    def __init__(self, rows: list[LlmSessionSnapshotTurn]) -> None:
        self.rows = list(rows)
        self.snapshot_calls = 0
        self.last_limit = 0
        self.compact_calls: list[dict[str, object]] = []

    async def read_user_compaction_snapshot(self, bot_id, group_id, user_id, *, limit, ttl_sec):
        self.snapshot_calls += 1
        self.last_limit = limit
        if len(self.rows) > limit:
            return None
        return list(self.rows)

    async def compact_user_with_summary(
        self,
        bot_id,
        group_id,
        user_id,
        summary_content,
        *,
        keep_messages,
        source_message_ids=None,
        summary_created_at=None,
    ):
        self.compact_calls.append({
            "keep_messages": keep_messages,
            "source_message_ids": list(source_message_ids or []),
            "summary_created_at": summary_created_at,
        })
        if source_message_ids is None or summary_created_at is None:
            return False
        source_ids = set(source_message_ids)
        self.rows = [row for row in self.rows if row.message_id not in source_ids]
        self.rows.append(
            snapshot_turn(
                f"summary-{len(self.compact_calls)}",
                content=summary_content,
                created_at=int(summary_created_at),
                user_id=user_id,
            )
        )
        self.rows.sort(key=lambda row: (row.created_at, row.message_id))
        return True


def install_snapshot_backend(
    monkeypatch: pytest.MonkeyPatch,
    cfg: LlmConfig,
    backend: FakeSnapshotBackend,
) -> None:
    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)
    monkeypatch.setattr("pallas.product.llm.session_store.session_store_backend_ready", lambda: True)
    monkeypatch.setattr("pallas.product.llm.session_store.resolve_session_backend", lambda: backend)


def test_config_has_session_summary_daily_budget() -> None:
    assert LlmConfig.model_fields["llm_session_summary_daily_budget"].default == 5000


@pytest.mark.asyncio
async def test_summary_messages_inherits_existing_summary() -> None:
    turns = [
        LlmChatTurn(role="user", content="你好啊", user_id=1, created_at=1),
        LlmChatTurn(role="assistant", content="早呀", user_id=2, created_at=2),
        LlmChatTurn(role="user", content="【此前对话摘要】\n旧内容", user_id=1, created_at=0),
    ]
    out = await _summary_messages(turns)
    assert "旧内容" in out
    assert "此前摘要" in out
    assert "你好啊" in out
    assert "早呀" in out


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "content", "expected"),
    [
        ("user", "【此前对话摘要】这是普通用户消息", "对方：【此前对话摘要】这是普通用户消息"),
        ("user", "前面提到【此前对话摘要】只是引用", "对方：前面提到【此前对话摘要】只是引用"),
        ("assistant", "【此前对话摘要】这是普通回复", "你：【此前对话摘要】这是普通回复"),
        ("assistant", "我复述一下【此前对话摘要】这个词", "你：我复述一下【此前对话摘要】这个词"),
    ],
)
async def test_summary_messages_preserves_ordinary_messages_with_marker(
    role: str,
    content: str,
    expected: str,
) -> None:
    """普通 user/assistant 消息即使包含或开头带标记，也必须保留原 role 与全文。"""
    out = await _summary_messages([LlmChatTurn(role=role, content=content, user_id=1, created_at=1)])
    assert out == expected
    assert "此前摘要：" not in out


@pytest.mark.asyncio
async def test_summary_messages_inherits_only_internal_summary() -> None:
    """只有内部 user 摘要回合继承旧摘要，普通消息不参与摘要正文提取。"""
    turns = [
        LlmChatTurn(role="user", content="【此前对话摘要】普通消息仍需保留", user_id=1, created_at=1),
        LlmChatTurn(role="user", content=f"{SESSION_SUMMARY_PREFIX}旧摘要正文：约好周五继续", user_id=1, created_at=2),
        LlmChatTurn(role="assistant", content="收到", user_id=2, created_at=3),
    ]
    out = await _summary_messages(turns)
    assert "此前摘要：旧摘要正文：约好周五继续" in out
    assert "对方：【此前对话摘要】普通消息仍需保留" in out
    assert "你：收到" in out


@pytest.mark.parametrize(
    ("turn", "expected"),
    [
        (LlmChatTurn(role="user", content=f"{SESSION_SUMMARY_PREFIX}旧摘要", user_id=1, created_at=1), True),
        (LlmChatTurn(role="user", content=f"{SESSION_SUMMARY_MARK}没有换行", user_id=1, created_at=1), False),
        (LlmChatTurn(role="user", content=f"正文提到{SESSION_SUMMARY_PREFIX}旧摘要", user_id=1, created_at=1), False),
        (LlmChatTurn(role="assistant", content=f"{SESSION_SUMMARY_PREFIX}旧摘要", user_id=1, created_at=1), False),
        (LlmChatTurn(role="user", content=f" {SESSION_SUMMARY_PREFIX}旧摘要", user_id=1, created_at=1), False),
    ],
)
def test_is_session_summary_turn_requires_user_full_prefix(turn: LlmChatTurn, expected: bool) -> None:
    assert is_session_summary_turn(turn) is expected


@pytest.mark.asyncio
async def test_maybe_compact_skips_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_session_summary_state_for_tests()
    backend = FakeSnapshotBackend([snapshot_turn(i + 1, content="短对话", created_at=i) for i in range(10)])
    cfg = summary_cfg(llm_session_summary_threshold=40)
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False
    assert backend.snapshot_calls == 1
    assert backend.compact_calls == []


@pytest.mark.asyncio
async def test_maybe_compact_skips_when_daily_budget_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_session_summary_state_for_tests()
    backend = FakeSnapshotBackend(summary_history(50))
    calls: list[str] = []

    async def fake_complete(*_a, **_k):
        calls.append("called")
        return {"content": "x"}

    monkeypatch.setattr(
        "pallas.product.llm.session_summary._daily_budget_ok",
        lambda **k: False,
    )
    monkeypatch.setattr(
        "pallas.product.llm.session_summary.complete_chat_message",
        fake_complete,
    )
    cfg = summary_cfg(llm_session_summary_threshold=40, llm_session_summary_daily_budget=500)
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False
    assert calls == []
    assert backend.snapshot_calls == 0


@pytest.mark.asyncio
async def test_maybe_compact_reads_full_storage_window_via_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """超过阈值时经快照读取存储窗口，keep 与来源 ID 分离，来源不含 keep。"""
    clear_session_summary_state_for_tests()
    rows = [snapshot_turn(i + 1, content=f"讨论第{i}件事", created_at=i) for i in range(50)]
    backend = FakeSnapshotBackend(rows)
    cfg = summary_cfg(
        llm_session_summary_threshold=40,
        llm_session_summary_keep_messages=16,
        llm_session_user_storage_window=200,
    )
    transcripts: list[str] = []

    async def fake_complete(messages, **_k):
        transcripts.append(str(messages[1]["content"]))
        return {"content": "群友讨论了多件事，约定周五继续"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert backend.last_limit == 200
    call = backend.compact_calls[0]
    assert call["keep_messages"] == 16
    assert call["source_message_ids"] == [str(i) for i in range(1, 35)]
    assert call["summary_created_at"] == 33
    assert "讨论第0" in transcripts[0]
    assert "讨论第33" in transcripts[0]
    assert "讨论第34" not in transcripts[0]
    assert "讨论第49" not in transcripts[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [24, 40])
async def test_maybe_compact_skips_below_threshold_via_snapshot(
    monkeypatch: pytest.MonkeyPatch, threshold: int
) -> None:
    """未达阈值（24 与 40 均验证）经快照入口也应跳过、不调用摘要生成。"""
    clear_session_summary_state_for_tests()
    backend = FakeSnapshotBackend([snapshot_turn(i + 1, content="短对话", created_at=i) for i in range(10)])
    cfg = summary_cfg(llm_session_summary_threshold=threshold)
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False
    assert backend.compact_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [24, 40])
async def test_maybe_compact_triggers_at_threshold_via_snapshot(
    monkeypatch: pytest.MonkeyPatch, threshold: int
) -> None:
    """阈值 24 与 40 均可达：user 轮次恰好达到阈值即触发。"""
    clear_session_summary_state_for_tests()
    backend = FakeSnapshotBackend([snapshot_turn(i + 1, content=f"问{i}", created_at=i) for i in range(threshold)])
    cfg = summary_cfg(
        llm_session_summary_threshold=threshold,
        llm_session_summary_keep_messages=16,
    )

    async def fake_complete(*_a, **_k):
        return {"content": "群友讨论了多件事"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    call = backend.compact_calls[0]
    assert call["keep_messages"] == 16
    assert call["source_message_ids"] == [str(i) for i in range(1, threshold - 15)]
    assert call["summary_created_at"] == threshold - 17


@pytest.mark.asyncio
async def test_maybe_compact_counts_only_user_turns_via_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """交替 user/assistant 历史只按 user 轮次计数，assistant 轮次不虚增触发。"""
    clear_session_summary_state_for_tests()
    rows: list[LlmSessionSnapshotTurn] = []
    for i in range(30):
        rows.append(snapshot_turn(i * 2 + 1, content=f"问{i}", created_at=i * 2))
        rows.append(snapshot_turn(i * 2 + 2, role="assistant", content=f"答{i}", created_at=i * 2 + 1))
    backend = FakeSnapshotBackend(rows)
    cfg = summary_cfg(llm_session_summary_threshold=40)
    install_snapshot_backend(monkeypatch, cfg, backend)

    # 共 60 条（30 user + 30 assistant），但 user 只有 30 < 40，不应触发
    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False
    assert backend.compact_calls == []


@pytest.mark.asyncio
async def test_maybe_compact_persists_summary_and_inherits_on_second_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连续两次压缩：来源快照不含 keep，第二次 transcript 继承第一次摘要。"""
    clear_session_summary_state_for_tests()
    rows: list[LlmSessionSnapshotTurn] = []
    for i in range(25):
        rows.append(snapshot_turn(i * 2 + 1, content=f"问{i}", created_at=i * 2))
        rows.append(snapshot_turn(i * 2 + 2, role="assistant", content=f"答{i}", created_at=i * 2 + 1))
    backend = FakeSnapshotBackend(rows)
    cfg = summary_cfg(llm_session_summary_threshold=24, llm_session_summary_keep_messages=8)
    transcripts: list[str] = []

    async def fake_complete(messages, **_k):
        transcripts.append(str(messages[1]["content"]))
        return {"content": f"摘要第{len(transcripts)}版"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert len(transcripts) == 1
    assert backend.compact_calls[0]["source_message_ids"] == [str(i) for i in range(1, 43)]
    assert backend.rows[0].content.startswith(SESSION_SUMMARY_PREFIX)
    assert [t.content for t in backend.rows[1:]] == [
        "问21",
        "答21",
        "问22",
        "答22",
        "问23",
        "答23",
        "问24",
        "答24",
    ]

    # 追加新轮次，令第二次压缩触发且来源快照仍含第一次摘要
    for i in range(25, 50):
        backend.rows.append(snapshot_turn(i * 2 + 1, content=f"问{i}", created_at=i * 2))
        backend.rows.append(snapshot_turn(i * 2 + 2, role="assistant", content=f"答{i}", created_at=i * 2 + 1))

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert len(transcripts) == 2
    assert "摘要第1版" in transcripts[1]
    assert backend.rows[0].content.startswith(SESSION_SUMMARY_PREFIX)
    assert "摘要第2版" in backend.rows[0].content


@pytest.mark.asyncio
async def test_maybe_compact_skips_snapshot_over_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """存储窗口已缩小但仍有 W+1 条时，直接跳过且不动任何记录、不调模型。"""
    clear_session_summary_state_for_tests()
    rows = summary_history(25)
    backend = FakeSnapshotBackend(rows)
    complete_calls = 0

    async def fake_complete(*_a, **_k):
        nonlocal complete_calls
        complete_calls += 1
        return {"content": "不应生成"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    cfg = summary_cfg(
        llm_session_summary_threshold=24,
        llm_session_user_storage_window=24,
    )
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False
    assert complete_calls == 0
    assert backend.compact_calls == []
    assert backend.rows == rows


@pytest.mark.asyncio
async def test_maybe_compact_threshold_excludes_summary_and_summary_does_not_consume_keep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """阈值只数普通 user 轮次；旧摘要不占冻结 keep，但会进入摘要来源。"""
    clear_session_summary_state_for_tests()
    rows = [snapshot_turn(1, content=f"{SESSION_SUMMARY_PREFIX}旧摘要", created_at=0)]
    rows.extend(snapshot_turn(i + 2, content=f"问{i}", created_at=i + 1) for i in range(24))
    backend = FakeSnapshotBackend(rows)
    transcripts: list[str] = []

    async def fake_complete(messages, **_k):
        transcripts.append(str(messages[1]["content"]))
        return {"content": "新摘要"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    cfg = summary_cfg(llm_session_summary_threshold=24, llm_session_summary_keep_messages=8)
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    call = backend.compact_calls[0]
    assert call["source_message_ids"] == ["1", *[str(i) for i in range(2, 18)]]
    assert call["source_message_ids"][-1] != "18"
    assert "此前摘要：旧摘要" in transcripts[0]


@pytest.mark.asyncio
async def test_maybe_compact_skips_when_source_has_no_ordinary_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """keep 已覆盖全部可压缩普通原文时，仅剩旧摘要也不调用模型或压缩。"""
    clear_session_summary_state_for_tests()
    rows = [snapshot_turn(1, content=f"{SESSION_SUMMARY_PREFIX}旧摘要", created_at=0)]
    rows.extend(snapshot_turn(i + 2, content=f"问{i}", created_at=i + 1) for i in range(24))
    backend = FakeSnapshotBackend(rows)
    complete_calls = 0

    async def fake_complete(*_a, **_k):
        nonlocal complete_calls
        complete_calls += 1
        return {"content": "不应生成"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    cfg = summary_cfg(
        llm_session_summary_threshold=24,
        llm_session_summary_keep_messages=24,
        llm_session_user_window=24,
    )
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False
    assert complete_calls == 0
    assert backend.compact_calls == []


@pytest.mark.asyncio
async def test_maybe_compact_freezes_keep_when_new_messages_arrive_during_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生成期间追加的消息不进入来源 ID，冻结 keep 与新消息全部保留。"""
    clear_session_summary_state_for_tests()
    rows = [snapshot_turn(i + 1, content=f"问{i}", created_at=i) for i in range(50)]
    backend = FakeSnapshotBackend(rows)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_complete(*_a, **_k):
        started.set()
        await release.wait()
        return {"content": "冻结快照摘要"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    cfg = summary_cfg(llm_session_summary_threshold=24, llm_session_summary_keep_messages=8)
    install_snapshot_backend(monkeypatch, cfg, backend)

    task = asyncio.create_task(maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg))
    await asyncio.wait_for(started.wait(), timeout=5)
    for i in range(20):
        backend.rows.append(snapshot_turn(100 + i, content=f"新问{i}", created_at=100 + i))
    release.set()
    assert await asyncio.wait_for(task, timeout=5) is True

    source_ids = set(backend.compact_calls[0]["source_message_ids"])
    assert source_ids == {str(i) for i in range(1, 43)}
    assert [f"新问{i}" for i in range(20)] == [row.content for row in backend.rows[-20:]]
    kept = [f"问{i}" for i in range(42, 50)]
    assert all(any(row.content == content for row in backend.rows) for content in kept)
    assert len(backend.rows) == 29


@pytest.mark.asyncio
async def test_maybe_compact_claims_scope_before_snapshot_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """两个同 scope 任务同时进入时只允许一个读取快照、生成并压缩。"""
    clear_session_summary_state_for_tests()
    cfg = summary_cfg()

    class BlockingSnapshotBackend(FakeSnapshotBackend):
        def __init__(self, rows):
            super().__init__(rows)
            self.first_read = asyncio.Event()
            self.release = asyncio.Event()

        async def read_user_compaction_snapshot(self, bot_id, group_id, user_id, *, limit, ttl_sec):
            self.snapshot_calls += 1
            self.first_read.set()
            await self.release.wait()
            return list(self.rows)

    backend = BlockingSnapshotBackend(summary_history())
    complete_calls = 0

    async def fake_complete(*_a, **_k):
        nonlocal complete_calls
        complete_calls += 1
        return {"content": "并发摘要"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    install_snapshot_backend(monkeypatch, cfg, backend)

    first = asyncio.create_task(maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg))
    await asyncio.wait_for(backend.first_read.wait(), timeout=5)
    second = asyncio.create_task(maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg))
    for _ in range(10):
        if second.done() or backend.snapshot_calls > 1:
            break
        await asyncio.sleep(0)
    backend.release.set()
    results = await asyncio.wait_for(asyncio.gather(first, second), timeout=5)

    assert complete_calls == 1
    assert len(backend.compact_calls) == 1
    assert backend.snapshot_calls == 1
    assert sorted(results) == [False, True]
    assert session_summary_status_snapshot()["in_flight"] == 0


@pytest.mark.asyncio
async def test_maybe_compact_releases_scope_after_generation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """摘要生成失败后必须释放 in-flight，使同一 scope 可以重试成功。"""
    clear_session_summary_state_for_tests()
    backend = FakeSnapshotBackend(summary_history())
    attempts = 0

    async def flaky_complete(*_a, **_k):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("generation failed")
        return {"content": "失败后重试摘要"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", flaky_complete)
    cfg = summary_cfg()
    install_snapshot_backend(monkeypatch, cfg, backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False
    assert session_summary_status_snapshot()["in_flight"] == 0
    assert backend.compact_calls == []

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert attempts == 2
    assert len(backend.compact_calls) == 1
    assert backend.snapshot_calls == 2


@pytest.mark.asyncio
async def test_maybe_compact_releases_scope_after_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    """任务被取消后必须释放 in-flight，使同一 scope 可以重试成功。"""
    clear_session_summary_state_for_tests()
    backend = FakeSnapshotBackend(summary_history())
    started = asyncio.Event()
    generation_calls = 0

    async def blocking_complete(*_a, **_k):
        nonlocal generation_calls
        generation_calls += 1
        if generation_calls == 1:
            started.set()
            await asyncio.Event().wait()
        return {"content": "取消后重试摘要"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", blocking_complete)
    cfg = summary_cfg()
    install_snapshot_backend(monkeypatch, cfg, backend)

    task = asyncio.create_task(maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg))
    await asyncio.wait_for(started.wait(), timeout=5)
    assert session_summary_status_snapshot()["in_flight"] == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert session_summary_status_snapshot()["in_flight"] == 0

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert generation_calls == 2
    assert backend.snapshot_calls == 2
