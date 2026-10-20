from __future__ import annotations

import pytest

from pallas.product.llm.config import LlmConfig
from pallas.product.llm.session_models import LlmChatTurn
from pallas.product.llm.session_summary import (
    _summary_messages,
    clear_session_summary_state_for_tests,
    maybe_compact_session_history,
)


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
async def test_maybe_compact_skips_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_session_summary_state_for_tests()

    async def fake_list(*_a, **_k):
        return [LlmChatTurn(role="user", content="短对话", user_id=1, created_at=i) for i in range(10)]

    monkeypatch.setattr(
        "pallas.product.llm.session_summary.is_llm_session_store_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "pallas.product.llm.session_summary.list_user_llm_messages",
        fake_list,
    )
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_summary_enabled=True,
        llm_session_summary_threshold=40,
        llm_session_summary_cooldown_sec=0,
        llm_session_user_storage_window=200,
    )
    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False


@pytest.mark.asyncio
async def test_maybe_compact_skips_when_daily_budget_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_session_summary_state_for_tests()
    calls: list[str] = []

    async def fake_list(*_a, **_k):
        return [LlmChatTurn(role="user", content=f"讨论第{i}件事", user_id=1, created_at=i) for i in range(50)]

    async def fake_complete(*_a, **_k):
        calls.append("called")
        return {"content": "x"}

    monkeypatch.setattr(
        "pallas.product.llm.session_summary.is_llm_session_store_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "pallas.product.llm.session_summary.list_user_llm_messages",
        fake_list,
    )
    monkeypatch.setattr(
        "pallas.product.llm.session_summary._daily_budget_ok",
        lambda **k: False,
    )
    monkeypatch.setattr(
        "pallas.product.llm.session_summary.complete_chat_message",
        fake_complete,
    )
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_summary_enabled=True,
        llm_session_summary_threshold=40,
        llm_session_summary_cooldown_sec=0,
        llm_session_user_storage_window=200,
        llm_session_summary_daily_budget=500,
    )
    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False
    assert calls == []


@pytest.mark.asyncio
async def test_maybe_compact_reads_full_storage_window_via_public_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """超过阈值时经真实公共读取入口（fake 底层持久化）生成并保存摘要，
    读取窗口不能被可见窗口 18 钳住，keep_messages 透传保最近轮次。"""
    clear_session_summary_state_for_tests()
    saved: dict[str, object] = {}
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_summary_enabled=True,
        llm_session_summary_threshold=40,
        llm_session_summary_keep_messages=16,
        llm_session_summary_cooldown_sec=0,
        llm_session_user_storage_window=200,
        llm_session_user_window=18,
    )

    class FakeBackend:
        async def list_user_messages(self, bot_id, group_id, user_id, *, limit, ttl_sec):
            return [
                LlmChatTurn(role="user", content=f"讨论第{i}件事", user_id=user_id, created_at=i)
                for i in range(50)
            ]

    async def fake_complete(*_a, **_k):
        return {"content": "群友讨论了多件事，约定周五继续"}

    async def fake_compact(*_a, **_k):
        saved["called"] = True
        saved["keep_messages"] = _k.get("keep_messages")
        return True

    monkeypatch.setattr(
        "pallas.product.llm.session_summary.complete_chat_message",
        fake_complete,
    )
    monkeypatch.setattr(
        "pallas.product.llm.session_summary.compact_user_llm_history_with_summary",
        fake_compact,
    )
    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)
    monkeypatch.setattr("pallas.product.llm.session_store.session_store_backend_ready", lambda: True)
    monkeypatch.setattr("pallas.product.llm.session_store.resolve_session_backend", lambda: FakeBackend())

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert saved.get("called") is True
    assert saved.get("keep_messages") == 16


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [24, 40])
async def test_maybe_compact_skips_below_threshold_via_public_entry(
    monkeypatch: pytest.MonkeyPatch, threshold: int
) -> None:
    """未达阈值（24 与 40 均验证）经公共读取入口也应跳过、不调用摘要生成。"""
    clear_session_summary_state_for_tests()
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_summary_enabled=True,
        llm_session_summary_threshold=threshold,
        llm_session_summary_cooldown_sec=0,
        llm_session_user_storage_window=200,
        llm_session_user_window=18,
    )

    class FakeBackend:
        async def list_user_messages(self, bot_id, group_id, user_id, *, limit, ttl_sec):
            return [LlmChatTurn(role="user", content="短对话", user_id=user_id, created_at=i) for i in range(10)]

    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)
    monkeypatch.setattr("pallas.product.llm.session_store.session_store_backend_ready", lambda: True)
    monkeypatch.setattr("pallas.product.llm.session_store.resolve_session_backend", lambda: FakeBackend())

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [24, 40])
async def test_maybe_compact_triggers_at_threshold_via_public_entry(
    monkeypatch: pytest.MonkeyPatch, threshold: int
) -> None:
    """阈值 24 与 40 均可达：user 轮次恰好达到阈值即触发，keep_messages 透传。"""
    clear_session_summary_state_for_tests()
    saved: dict[str, object] = {}
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_summary_enabled=True,
        llm_session_summary_threshold=threshold,
        llm_session_summary_keep_messages=16,
        llm_session_summary_cooldown_sec=0,
        llm_session_user_storage_window=200,
        llm_session_user_window=18,
    )

    class FakeBackend:
        async def list_user_messages(self, bot_id, group_id, user_id, *, limit, ttl_sec):
            return [LlmChatTurn(role="user", content=f"问{i}", user_id=user_id, created_at=i) for i in range(threshold)]

    async def fake_complete(*_a, **_k):
        return {"content": "群友讨论了多件事"}

    async def fake_compact(*_a, **_k):
        saved["called"] = True
        saved["keep_messages"] = _k.get("keep_messages")
        return True

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    monkeypatch.setattr("pallas.product.llm.session_summary.compact_user_llm_history_with_summary", fake_compact)
    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)
    monkeypatch.setattr("pallas.product.llm.session_store.session_store_backend_ready", lambda: True)
    monkeypatch.setattr("pallas.product.llm.session_store.resolve_session_backend", lambda: FakeBackend())

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert saved.get("called") is True
    assert saved.get("keep_messages") == 16


@pytest.mark.asyncio
async def test_maybe_compact_counts_only_user_turns_via_public_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """交替 user/assistant 历史只按 user 轮次计数，assistant 轮次不虚增触发。"""
    clear_session_summary_state_for_tests()
    cfg = LlmConfig(
        llm_chat_enabled=True,
        llm_session_enabled=True,
        llm_session_summary_enabled=True,
        llm_session_summary_threshold=40,
        llm_session_summary_cooldown_sec=0,
        llm_session_user_storage_window=200,
        llm_session_user_window=18,
    )

    class FakeBackend:
        async def list_user_messages(self, bot_id, group_id, user_id, *, limit, ttl_sec):
            data = []
            for i in range(30):
                data.append(LlmChatTurn(role="user", content=f"问{i}", user_id=user_id, created_at=i * 2))
                data.append(LlmChatTurn(role="assistant", content=f"答{i}", user_id=user_id, created_at=i * 2 + 1))
            return data

    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)
    monkeypatch.setattr("pallas.product.llm.session_store.session_store_backend_ready", lambda: True)
    monkeypatch.setattr("pallas.product.llm.session_store.resolve_session_backend", lambda: FakeBackend())

    # 共 60 条（30 user + 30 assistant），但 user 只有 30 < 40，不应触发
    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is False


@pytest.mark.asyncio
async def test_maybe_compact_persists_summary_and_inherits_on_second_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连续两次压缩：第一次回插摘要并保留最近 keep 条；第二次 transcript 继承第一次摘要。"""
    clear_session_summary_state_for_tests()
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

    class PersistentBackend:
        def __init__(self) -> None:
            self.data: list[LlmChatTurn] = []

        async def list_user_messages(self, bot_id, group_id, user_id, *, limit, ttl_sec):
            return list(self.data[-limit:])

        async def compact_user_with_summary(self, bot_id, group_id, user_id, summary_content, *, keep_messages):
            keep = max(2, int(keep_messages))
            if len(self.data) <= keep:
                return False
            kept = self.data[-keep:]
            self.data = [LlmChatTurn(role="user", content=summary_content, user_id=user_id, created_at=-1)] + kept
            return True

    backend = PersistentBackend()
    for i in range(25):
        backend.data.append(LlmChatTurn(role="user", content=f"问{i}", user_id=3, created_at=i * 2))
        backend.data.append(LlmChatTurn(role="assistant", content=f"答{i}", user_id=3, created_at=i * 2 + 1))

    transcripts: list[str] = []

    async def fake_complete(messages, **_k):
        transcripts.append(str(messages[1]["content"]))
        return {"content": f"摘要第{len(transcripts)}版"}

    monkeypatch.setattr("pallas.product.llm.session_summary.complete_chat_message", fake_complete)
    monkeypatch.setattr("pallas.product.llm.session_store.get_llm_config", lambda: cfg)
    monkeypatch.setattr("pallas.product.llm.session_store.session_store_backend_ready", lambda: True)
    monkeypatch.setattr("pallas.product.llm.session_store.resolve_session_backend", lambda: backend)

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert len(backend.data) == 9
    assert backend.data[0].content.startswith("【此前对话摘要】")
    assert [t.content for t in backend.data[1:]] == [
        "问21",
        "答21",
        "问22",
        "答22",
        "问23",
        "答23",
        "问24",
        "答24",
    ]

    # 追加新轮次，令第二次压缩触发且 history 仍含第一次摘要
    for i in range(25, 50):
        backend.data.append(LlmChatTurn(role="user", content=f"问{i}", user_id=3, created_at=i * 2))
        backend.data.append(LlmChatTurn(role="assistant", content=f"答{i}", user_id=3, created_at=i * 2 + 1))

    assert await maybe_compact_session_history(bot_id=1, group_id=2, user_id=3, cfg=cfg) is True
    assert len(transcripts) == 2
    assert "摘要第1版" in transcripts[1]
    assert backend.data[0].content.startswith("【此前对话摘要】")
    assert "摘要第2版" in backend.data[0].content
