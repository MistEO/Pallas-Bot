from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from pallas.product.llm.assembler.chat_prompt import ChatPromptAssembler
from pallas.product.llm.assembler.context import assemble_direct_chat_context
from pallas.product.llm.config import LlmConfig
from pallas.product.llm.knowledge.inject import (
    enrich_system_with_knowledge_sources,
    looks_like_invite_followup,
    looks_like_knowledge_query,
    resolve_knowledge_query,
)
from pallas.product.llm.knowledge.metadata import knowledge_sources_from_metadata
from pallas.product.llm.knowledge.models import (
    KnowledgeInjectionResult,
    KnowledgeSourceDecl,
    KnowledgeSourceScope,
)
from pallas.product.llm.knowledge.registry import retrieve_from_knowledge_sources
from pallas.product.llm.memory.inject import (
    MemoryInjectionResult,
    PersonFactsInjectionResult,
    RelationshipInjectionResult,
)
from pallas.product.llm.reply_shape import ReplyShapePolicy
from pallas.product.llm.session_store import LlmChatTurn
from pallas.product.llm.turn_policy import TurnPolicy

NOW = int(time.time())


def _invite_turn(*, user_id: int = 7, age: int = 10, text: str = "我想邀请牛牛进群") -> LlmChatTurn:
    return LlmChatTurn(role="user", content=text, user_id=user_id, created_at=NOW - age)


@pytest.fixture
def real_llm_chat_faq(monkeypatch: pytest.MonkeyPatch) -> KnowledgeSourceDecl:
    """真实 llm_chat.faq 声明（静态读取插件元数据，不 mock 假 FAQ）。"""
    from packages.llm_chat import __plugin_meta__

    faq = next(decl for decl in knowledge_sources_from_metadata(__plugin_meta__) if decl.source_id == "llm_chat.faq")
    monkeypatch.setattr(
        "pallas.product.llm.knowledge.registry.iter_loaded_plugin_knowledge_sources",
        lambda: [("llm_chat", "智能对话", faq)],
    )
    monkeypatch.setattr(
        "pallas.product.llm.knowledge.file_ingest.ensure_file_knowledge_registered",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr("pallas.product.llm.knowledge.registry._BUILTIN_SOURCES", [])
    monkeypatch.setattr("pallas.product.llm.knowledge.vector_backend.vector_retrieve_mode", lambda _cfg=None: "keyword")
    return faq


def _cfg(**overrides) -> LlmConfig:
    return LlmConfig(llm_chat_enabled=True, llm_knowledge_sources_enabled=True, **overrides)


@pytest.mark.parametrize(
    "query",
    ["怎么邀请牛牛进群", "牛牛能来我们群吗", "进群要什么条件"],
)
def test_explicit_invite_questions_gate(query: str) -> None:
    assert looks_like_knowledge_query(query)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    ["怎么邀请牛牛进群", "牛牛能来我们群吗", "进群要什么条件"],
)
async def test_explicit_invite_questions_hit_real_faq_at_default_threshold(
    query: str,
    real_llm_chat_faq: KnowledgeSourceDecl,
) -> None:
    result = await enrich_system_with_knowledge_sources(
        "你是牛牛。",
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text=query,
        cfg=_cfg(),
    )
    assert result.trace["hit_count"] >= 1
    assert "llm_chat.faq" in result.trace["sources"]
    assert "普通群友想拉牛牛进群" in result.system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["有啥要求吗", "什么时候同意", "收到了吗", "能不能"])
async def test_invite_followup_carries_with_recent_same_user_invite(
    query: str,
    real_llm_chat_faq: KnowledgeSourceDecl,
) -> None:
    result = await enrich_system_with_knowledge_sources(
        "你是牛牛。",
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text=query,
        cfg=_cfg(),
        recent_user_turns=[_invite_turn()],
    )
    assert result.trace.get("context_carry") is True
    assert "llm_chat.faq" in result.trace["sources"]
    assert "普通群友想拉牛牛进群" in result.system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["有啥要求吗", "什么时候同意", "收到了吗", "能不能"])
async def test_invite_followup_without_history_does_not_inject(
    query: str,
    real_llm_chat_faq: KnowledgeSourceDecl,
) -> None:
    result = await enrich_system_with_knowledge_sources(
        "你是牛牛。",
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text=query,
        cfg=_cfg(),
        recent_user_turns=[],
    )
    assert result.trace.get("context_carry") is None
    assert result.trace["hit_count"] == 0
    assert result.system_prompt == "你是牛牛。"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "turns",
    [
        [_invite_turn(), LlmChatTurn(role="user", content="今天天气不错", user_id=7, created_at=NOW - 5)],
        [_invite_turn(age=999)],
        [_invite_turn(age=-50)],
        [_invite_turn(user_id=9)],
        [LlmChatTurn(role="assistant", content="我想邀请牛牛进群", user_id=7, created_at=NOW - 5)],
    ],
)
async def test_invite_carry_rejects_untrusted_history(
    turns: list[LlmChatTurn],
    real_llm_chat_faq: KnowledgeSourceDecl,
) -> None:
    result = await enrich_system_with_knowledge_sources(
        "你是牛牛。",
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text="有啥要求吗",
        cfg=_cfg(),
        recent_user_turns=turns,
    )
    assert result.trace.get("context_carry") is None
    assert result.trace["hit_count"] == 0


@pytest.mark.asyncio
async def test_invite_carry_inherits_through_prior_followup(
    real_llm_chat_faq: KnowledgeSourceDecl,
) -> None:
    history = [
        LlmChatTurn(role="user", content="我想邀请牛牛进群", user_id=7, created_at=NOW - 40),
        LlmChatTurn(role="user", content="有啥要求吗", user_id=7, created_at=NOW - 20),
    ]
    result = await enrich_system_with_knowledge_sources(
        "你是牛牛。",
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text="收到了吗",
        cfg=_cfg(),
        recent_user_turns=history,
    )
    assert result.trace.get("context_carry") is True
    assert "llm_chat.faq" in result.trace["sources"]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["抱抱", "喜欢你", "邀请朋友吃饭", "邀请你吃饭", "邀请牛牛吃饭"])
async def test_plain_social_or_non_bot_invite_not_injected(
    query: str,
    real_llm_chat_faq: KnowledgeSourceDecl,
) -> None:
    assert not looks_like_knowledge_query(query)
    result = await enrich_system_with_knowledge_sources(
        "你是牛牛。",
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text=query,
        cfg=_cfg(),
        recent_user_turns=[_invite_turn()],
    )
    assert result.trace.get("context_carry") is None
    assert result.trace["hit_count"] == 0


@pytest.mark.parametrize(
    "later_turns",
    [
        [_invite_turn(text="现在换个话题，考试报名有什么要求，" + "补充报名信息。" * 10)],
        [
            _invite_turn(age=30, text="现在谈考试报名，" + "补充考试要求。" * 10),
            _invite_turn(text="还有条件吗"),
        ],
        [_invite_turn(age=-5, text="有啥要求吗")],
        [_invite_turn(text="邀请你吃饭")],
        [LlmChatTurn(role="user", content="有啥要求吗", user_id=7, created_at=0)],
    ],
)
def test_invalid_or_changed_latest_topic_does_not_recover_old_invite(later_turns: list[LlmChatTurn]) -> None:
    history = [_invite_turn(age=50), *later_turns]
    assert resolve_knowledge_query("有啥要求吗", recent_user_turns=history, user_id=7, now=NOW) == ("有啥要求吗", False)


@pytest.mark.asyncio
async def test_knowledge_disabled_skips_invite_carry(real_llm_chat_faq: KnowledgeSourceDecl) -> None:
    result = await enrich_system_with_knowledge_sources(
        "你是牛牛。",
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text="有啥要求吗",
        cfg=LlmConfig(llm_chat_enabled=True, llm_knowledge_sources_enabled=False),
        recent_user_turns=[_invite_turn()],
    )
    assert result.system_prompt == "你是牛牛。"
    assert result.trace["hit_count"] == 0


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("有啥要求吗", True),
        ("什么时候同意", True),
        ("收到了吗", True),
        ("能不能", True),
        ("你对我有什么要求", False),
        ("考试有什么要求", False),
        ("轨道力学", False),
        ("清空要求", False),
    ],
)
def test_invite_followup_gate_avoids_subject_switch(query: str, expected: bool) -> None:
    assert looks_like_invite_followup(query) is expected


def test_resolve_knowledge_query_keeps_explicit_and_unrelated_queries() -> None:
    history = [_invite_turn()]
    assert resolve_knowledge_query("怎么邀请牛牛进群", recent_user_turns=history, user_id=7, now=NOW) == (
        "怎么邀请牛牛进群",
        False,
    )
    assert resolve_knowledge_query("邀请朋友吃饭", recent_user_turns=history, user_id=7, now=NOW) == (
        "邀请朋友吃饭",
        False,
    )
    assert resolve_knowledge_query("今天天气", recent_user_turns=history, user_id=7, now=NOW) == ("今天天气", False)


def test_retrieve_scope_filter_still_applies_for_bot_scoped_source(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_only = KnowledgeSourceDecl(
        source_id="test.invite_bot_only",
        title="某牛私有知识",
        scope=KnowledgeSourceScope.BOT,
        bot_id=777,
        chunks=[{"title": "邀请牛牛进群", "content": "只有777号牛知道的邀请流程", "keywords": "邀请牛牛,进群"}],
    )
    monkeypatch.setattr(
        "pallas.product.llm.knowledge.registry.iter_loaded_plugin_knowledge_sources",
        lambda: [("test", "test", bot_only)],
    )
    monkeypatch.setattr(
        "pallas.product.llm.knowledge.file_ingest.ensure_file_knowledge_registered",
        lambda **_kwargs: False,
    )
    monkeypatch.setattr("pallas.product.llm.knowledge.registry._BUILTIN_SOURCES", [])
    monkeypatch.setattr("pallas.product.llm.knowledge.vector_backend.vector_retrieve_mode", lambda _cfg=None: "keyword")

    hits_other = retrieve_from_knowledge_sources("邀请牛牛进群", bot_id=123, group_id=2, user_id=7, cfg=_cfg())
    hits_owner = retrieve_from_knowledge_sources("邀请牛牛进群", bot_id=777, group_id=2, user_id=7, cfg=_cfg())
    assert not any(hit.source_id == "test.invite_bot_only" for hit in hits_other)
    assert any(hit.source_id == "test.invite_bot_only" for hit in hits_owner)


@pytest.mark.asyncio
async def test_assemble_passes_history_to_knowledge_and_keeps_memory_query(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = AsyncMock(return_value=MemoryInjectionResult(system_prompt="memory", trace={"hit_count": 0}))
    knowledge = AsyncMock(return_value=KnowledgeInjectionResult(system_prompt="knowledge", trace={"hit_count": 0}))
    monkeypatch.setattr("pallas.product.llm.assembler.context.enrich_system_with_memory_context", memory)
    monkeypatch.setattr("pallas.product.llm.assembler.context.enrich_system_with_knowledge_sources", knowledge)
    monkeypatch.setattr(
        "pallas.product.llm.assembler.context.enrich_system_with_relationship_context",
        AsyncMock(return_value=RelationshipInjectionResult(system_prompt="", trace={"hit_count": 0})),
    )
    monkeypatch.setattr(
        "pallas.product.llm.assembler.context.enrich_system_with_person_facts",
        AsyncMock(return_value=PersonFactsInjectionResult(system_prompt="", trace={"hit_count": 0})),
    )
    monkeypatch.setattr("pallas.product.llm.knowledge.embedding_client.embedding_capability_trace", lambda _cfg: {})
    monkeypatch.setattr("pallas.product.llm.knowledge.vector_backend.vector_retrieve_mode", lambda _cfg: "keyword")

    history = [_invite_turn()]
    await assemble_direct_chat_context(
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text="有啥要求吗",
        cfg=_cfg(),
        allow_persistent_memory=False,
        recent_user_turns=history,
    )

    memory.assert_awaited_once()
    assert memory.await_args.kwargs["query_text"] == "有啥要求吗"
    knowledge.assert_awaited_once()
    assert knowledge.await_args.kwargs["query_text"] == "有啥要求吗"
    assert knowledge.await_args.kwargs["recent_user_turns"] == history


@pytest.mark.asyncio
async def test_real_knowledge_reaches_chat_prompt_through_history(
    monkeypatch: pytest.MonkeyPatch,
    real_llm_chat_faq: KnowledgeSourceDecl,
) -> None:
    monkeypatch.setattr(
        "pallas.product.llm.assembler.context.enrich_system_with_memory_context",
        AsyncMock(return_value=MemoryInjectionResult(system_prompt="", trace={"hit_count": 0})),
    )
    monkeypatch.setattr(
        "pallas.product.llm.assembler.context.enrich_system_with_relationship_context",
        AsyncMock(return_value=RelationshipInjectionResult(system_prompt="", trace={"hit_count": 0})),
    )
    monkeypatch.setattr(
        "pallas.product.llm.assembler.context.enrich_system_with_person_facts",
        AsyncMock(return_value=PersonFactsInjectionResult(system_prompt="", trace={"hit_count": 0})),
    )
    monkeypatch.setattr("pallas.product.llm.knowledge.embedding_client.embedding_capability_trace", lambda _cfg: {})

    context = await assemble_direct_chat_context(
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text="有啥要求吗",
        cfg=_cfg(),
        allow_persistent_memory=False,
        recent_user_turns=[_invite_turn()],
    )
    prompt = ChatPromptAssembler().assemble(
        core_persona="核心人设",
        self_identity="",
        turn_policy=TurnPolicy("fact", "serious", "ANSWER", False, False, False, True),
        context=context,
        group_expression=None,
        reply_shape=ReplyShapePolicy(1, 2, 1, 40, "complete", "single", 128),
    )

    assert "【相关知识参考" in prompt
    assert "普通群友想拉牛牛进群" in prompt
    assert context.knowledge_retrieval_trace.get("context_carry") is True
