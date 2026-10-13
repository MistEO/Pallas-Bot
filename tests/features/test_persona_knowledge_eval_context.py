from __future__ import annotations

import importlib
import time
from unittest.mock import AsyncMock

import pytest

from pallas.product.llm.assembler.chat_prompt import ChatPromptAssembler
from pallas.product.llm.assembler.context import assemble_direct_chat_context
from pallas.product.llm.config import LlmConfig
from pallas.product.llm.knowledge.metadata import knowledge_sources_from_metadata
from pallas.product.llm.memory.inject import (
    MemoryInjectionResult,
    PersonFactsInjectionResult,
    RelationshipInjectionResult,
)
from pallas.product.llm.persona_context import build_persona_llm_context
from pallas.product.llm.reply_shape import ReplyShapePolicy
from pallas.product.llm.session_store import LlmChatTurn
from pallas.product.llm.turn_policy import TurnPolicy
from pallas.product.persona.auto import derive_persona_from_bot_id


def _patch_real_persona_compile(monkeypatch: pytest.MonkeyPatch) -> None:
    """让正式 persona 编译在离线可用：只 mock 数据源，保留真实 at_chat 基座与组装。"""
    compile_mod = importlib.import_module("pallas.product.persona.compile_persona_prompt")

    async def fake_resolve_persona(bot_id: int, group_id: int | None = None):
        return derive_persona_from_bot_id(bot_id)

    async def fake_resolve_persona_for_message(bot_id: int, group_id: int, plain_text: str):
        return derive_persona_from_bot_id(bot_id)

    async def fake_login_nickname(bot_id: int) -> str:
        return "牛牛"

    class FakeRepo:
        async def get(self, _id):
            return None

    monkeypatch.setattr(compile_mod, "resolve_persona", fake_resolve_persona)
    monkeypatch.setattr(compile_mod, "resolve_persona_for_message", fake_resolve_persona_for_message)
    monkeypatch.setattr(compile_mod, "resolve_login_nickname", fake_login_nickname)
    monkeypatch.setattr(compile_mod, "resolve_managed_display_name", lambda _bot_id: "")
    monkeypatch.setattr(compile_mod, "make_bot_config_repository", lambda: FakeRepo())
    monkeypatch.setattr(compile_mod, "make_group_config_repository", lambda: FakeRepo())


def _register_real_faq(monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.mark.asyncio
async def test_real_persona_and_invite_knowledge_land_in_distinct_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_real_persona_compile(monkeypatch)
    _register_real_faq(monkeypatch)

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

    now = int(time.time())
    history = [LlmChatTurn(role="user", content="我想邀请牛牛进群", user_id=7, created_at=now - 10)]
    cfg = LlmConfig(llm_chat_enabled=True, llm_knowledge_sources_enabled=True)

    bundle, _temperature, _token_count = await build_persona_llm_context(1, 2, "有啥要求吗")
    context = await assemble_direct_chat_context(
        bot_id=1,
        group_id=2,
        user_id=7,
        query_text="有啥要求吗",
        cfg=cfg,
        allow_persistent_memory=False,
        recent_user_turns=history,
    )
    prompt = ChatPromptAssembler().assemble(
        core_persona=bundle.sections.base,
        self_identity=bundle.sections.self_identity,
        turn_policy=TurnPolicy("fact", "serious", "ANSWER", False, False, False, True),
        context=context,
        group_expression=None,
        reply_shape=ReplyShapePolicy(1, 2, 1, 40, "complete", "single", 128),
    )

    # 正式帕拉斯身份与普通群友/反客服规则来自真实 persona 基座段
    assert "帕拉斯" in prompt
    assert "普通群友" in prompt
    assert "客服" in prompt
    assert "【相关知识参考" in prompt
    assert "普通群友想拉牛牛进群" in prompt
    assert context.knowledge_retrieval_trace.get("context_carry") is True
