"""单轮 llm_chat 生成预算对象、配置与 console 接入。"""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from pallas.product.llm.config import LlmConfig
from pallas.product.llm.turn_budget import (
    LlmTurnBudget,
    LlmTurnBudgetExceeded,
    budget_trace_fields,
    clamp_timeout_sec,
    new_llm_chat_turn_budget,
)


def test_budget_claim_counts_and_caps() -> None:
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 60, max_http_attempts=2)
    budget.claim_http_attempt()
    budget.claim_http_attempt()
    assert budget.used_http_attempts == 2
    assert budget.http_attempts_exhausted() is True
    with pytest.raises(LlmTurnBudgetExceeded) as exc:
        budget.claim_http_attempt()
    assert exc.value.reason == "http_attempts_exhausted"


def test_budget_deadline_not_refreshed_by_claims() -> None:
    deadline = time.monotonic() + 60
    budget = LlmTurnBudget(deadline_monotonic=deadline, max_http_attempts=6)
    budget.claim_http_attempt()
    budget.claim_http_attempt()
    assert budget.deadline_monotonic == deadline


def test_budget_claim_rejects_after_deadline() -> None:
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() - 1, max_http_attempts=6)
    assert budget.expired() is True
    with pytest.raises(LlmTurnBudgetExceeded) as exc:
        budget.claim_http_attempt()
    assert exc.value.reason == "deadline_exceeded"


def test_budget_clamp_and_trace_fields() -> None:
    budget = LlmTurnBudget(deadline_monotonic=time.monotonic() + 5, max_http_attempts=6)
    assert clamp_timeout_sec(30.0, budget) <= 5.0
    assert clamp_timeout_sec(30.0, None) == 30.0
    fields = budget_trace_fields(budget, reason="deadline_exceeded", side_effect_started=True)
    assert fields["budget_exhausted"] is True
    assert fields["budget_exhaust_reason"] == "deadline_exceeded"
    assert fields["side_effect_started"] is True
    assert fields["budget_http_attempts_max"] == 6


def test_new_turn_budget_defaults() -> None:
    budget = new_llm_chat_turn_budget(LlmConfig())
    assert budget.max_http_attempts == 6
    remaining = budget.remaining_sec()
    assert remaining is not None
    assert 0 < remaining <= 60


def test_new_turn_budget_deadline_anchored_to_started_at() -> None:
    cfg = LlmConfig(llm_chat_turn_timeout_sec=60)
    now = time.monotonic()
    expired = new_llm_chat_turn_budget(cfg, started_at=now - 100)
    assert expired.deadline_monotonic == pytest.approx(now - 40, abs=0.01)
    assert expired.expired() is True
    fresh = new_llm_chat_turn_budget(cfg, started_at=now)
    assert fresh.deadline_monotonic == pytest.approx(now + 60, abs=0.01)


def test_turn_budget_config_bounds() -> None:
    with pytest.raises(ValidationError):
        LlmConfig(llm_chat_turn_timeout_sec=0)
    with pytest.raises(ValidationError):
        LlmConfig(llm_chat_turn_timeout_sec=601)
    with pytest.raises(ValidationError):
        LlmConfig(llm_chat_turn_max_http_attempts=0)
    with pytest.raises(ValidationError):
        LlmConfig(llm_chat_turn_max_http_attempts=65)


def test_turn_budget_env_read(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.product.llm.config import clear_llm_config_cache, get_llm_config

    monkeypatch.setattr(
        "pallas.product.llm.feedback_embedding_cache.schedule_feedback_trigger_backfill",
        lambda: None,
    )
    values = {"LLM_CHAT_TURN_TIMEOUT_SEC": "12.5", "LLM_CHAT_TURN_MAX_HTTP_ATTEMPTS": "3"}
    monkeypatch.setattr("pallas.product.llm.config.repo_env_raw_value", lambda key: values.get(key))
    clear_llm_config_cache()
    try:
        cfg = get_llm_config()
        assert cfg.llm_chat_turn_timeout_sec == 12.5
        assert cfg.llm_chat_turn_max_http_attempts == 3
    finally:
        clear_llm_config_cache()


def test_turn_budget_console_registration() -> None:
    from pallas.console.webui.env_sections import _llm_section
    from pallas.console.webui.field_labels import FIELD_LABELS
    from pallas.product.llm.webui_config import LlmWebuiConfig

    for field in ("llm_chat_turn_timeout_sec", "llm_chat_turn_max_http_attempts"):
        assert FIELD_LABELS.get(field)
        assert field in LlmWebuiConfig.model_fields
        assert LlmWebuiConfig.model_fields[field].description
    section = _llm_section()
    assert section.field_to_env["llm_chat_turn_timeout_sec"] == "LLM_CHAT_TURN_TIMEOUT_SEC"
    assert section.field_to_env["llm_chat_turn_max_http_attempts"] == "LLM_CHAT_TURN_MAX_HTTP_ATTEMPTS"
