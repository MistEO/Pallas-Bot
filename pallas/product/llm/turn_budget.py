"""普通内核闲聊单轮的生成预算：墙钟截止 + 真实 HTTP 尝试次数。

一次 ``llm_chat`` 内核生成共享同一对象：候选准备、provider 补全、工具续轮、
final 与 persona retry 都经它计数，换 key / 换 provider / required→auto 不重置。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pallas.product.llm.config import LlmConfig


class LlmTurnBudgetExceeded(Exception):  # noqa: N818 — 预算耗尽信号，命名按决策固定
    """单轮生成预算耗尽：独立于 ProviderError，不冒充上游错误。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class LlmTurnBudget:
    """单轮 llm_chat 的共享预算；deadline 与 HTTP 次数对整轮固定，不随 failover 刷新。"""

    deadline_monotonic: float | None = None
    max_http_attempts: int | None = None
    used_http_attempts: int = field(default=0)

    def remaining_sec(self, *, now: float | None = None) -> float | None:
        if self.deadline_monotonic is None:
            return None
        current = time.monotonic() if now is None else now
        return self.deadline_monotonic - current

    def expired(self, *, now: float | None = None) -> bool:
        remaining = self.remaining_sec(now=now)
        return remaining is not None and remaining <= 0

    def http_attempts_exhausted(self) -> bool:
        return self.max_http_attempts is not None and self.used_http_attempts >= self.max_http_attempts

    def claim_http_attempt(self) -> None:
        """真正发起 client.post 前原子领取一次；过期或次数用尽即拒绝。"""
        if self.expired():
            raise LlmTurnBudgetExceeded("deadline_exceeded")
        if self.http_attempts_exhausted():
            raise LlmTurnBudgetExceeded("http_attempts_exhausted")
        self.used_http_attempts += 1


def new_llm_chat_turn_budget(cfg: LlmConfig, *, started_at: float | None = None) -> LlmTurnBudget:
    """kernel 开始生成时创建；deadline 锚在 ``started_at``，不随第一次 provider 调用另起时钟。"""
    anchor = time.monotonic() if started_at is None else started_at
    return LlmTurnBudget(
        deadline_monotonic=anchor + float(cfg.llm_chat_turn_timeout_sec),
        max_http_attempts=int(cfg.llm_chat_turn_max_http_attempts),
    )


async def await_within_budget(
    factory: Callable[[], Awaitable[Any]],
    budget: LlmTurnBudget | None,
) -> Any:
    """在剩余预算内等待 provider / 准备协程；仅自身到期才转预算异常。"""
    if budget is None:
        return await factory()
    remaining = budget.remaining_sec()
    if remaining is None:
        return await factory()
    if remaining <= 0:
        raise LlmTurnBudgetExceeded("deadline_exceeded")
    try:
        async with asyncio.timeout(remaining) as scope:
            return await factory()
    except TimeoutError:
        if scope.expired():
            raise LlmTurnBudgetExceeded("deadline_exceeded") from None
        raise


def clamp_timeout_sec(timeout_sec: float, budget: LlmTurnBudget | None) -> float:
    """httpx 分阶段超时钳到 min(原值, 剩余)；无预算保持原值。"""
    if budget is None:
        return timeout_sec
    remaining = budget.remaining_sec()
    if remaining is None:
        return timeout_sec
    return max(0.001, min(float(timeout_sec), remaining))


def budget_trace_fields(
    budget: LlmTurnBudget | None,
    *,
    reason: str = "",
    side_effect_started: bool = False,
) -> dict[str, Any]:
    if budget is None:
        return {}
    return {
        "budget_exhausted": True,
        "budget_exhaust_reason": reason or "deadline_exceeded",
        "budget_http_attempts_used": budget.used_http_attempts,
        "budget_http_attempts_max": budget.max_http_attempts,
        "side_effect_started": side_effect_started,
    }
