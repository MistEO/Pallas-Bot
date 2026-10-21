from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

LlmChatRole = Literal["user", "assistant"]
ALLOWED_ROLES = frozenset({"user", "assistant"})

SESSION_SUMMARY_MARK = "【此前对话摘要】"
SESSION_SUMMARY_PREFIX = f"{SESSION_SUMMARY_MARK}\n"


def is_session_summary_turn(turn: Any) -> bool:
    """按固定 user 角色与完整前缀识别内部摘要。

    用户消息若完整复刻相同前缀，无法仅凭存储内容区分来源。
    """
    role = str(getattr(turn, "role", "") or "")
    content = str(getattr(turn, "content", "") or "")
    return role == "user" and content.startswith(SESSION_SUMMARY_PREFIX)


class LlmChatTurn(BaseModel):
    role: LlmChatRole
    content: str
    user_id: int
    created_at: int


class LlmSessionSnapshotTurn(LlmChatTurn):
    """压缩快照内部回合；message_id 不进入公开历史响应。"""

    message_id: str


class LlmSessionScope(BaseModel):
    bot_id: int
    group_id: int = 0
    user_id: int | None = None


class LlmHistorySessionSummary(BaseModel):
    session_key: str
    bot_id: int
    group_id: int
    user_id: int
    turn_count: int
    first_created_at: int
    last_created_at: int
    last_role: LlmChatRole
    last_content: str


class LlmHistorySessionDetail(BaseModel):
    session: LlmHistorySessionSummary
    turns: list[LlmChatTurn]
    behavior_runs: list[dict[str, Any]] = Field(default_factory=list)
    feedback_entries: list[dict[str, Any]] = Field(default_factory=list)


def normalize_group_scope(group_id: int | None) -> int:
    return int(group_id) if group_id is not None else 0


def is_private_scope(group_id: int | None) -> bool:
    return normalize_group_scope(group_id) == 0
