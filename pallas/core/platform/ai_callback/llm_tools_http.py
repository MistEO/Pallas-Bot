"""兼容 AI 扩展回调 Bot 执行 LLM tools；内核 tool loop 不经此路由。

必须有效 AI Bearer 或维护者 API Key；request_id 必填且有界，并绑定到已登记的待处理 LLM 任务；
上下文主体一律来自任务登记，body 身份仅作兼容断言，不接受 body 自授 approved_tools。
"""

from __future__ import annotations

import re

from fastapi import Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from pallas.core.platform.ai_callback import ai_bearer
from pallas.core.platform.ai_callback.boundary_guard import install_ai_boundary_guard
from pallas.core.platform.ai_callback.task_types import CHAT_DRUNK_TASK_TYPE, LEGACY_LLM_CHAT_TASK_TYPES
from pallas.product.llm.tools.context import ToolInvokeContext

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_LLM_TASK_TYPES = LEGACY_LLM_CHAT_TASK_TYPES | {CHAT_DRUNK_TASK_TYPE}


class LlmToolExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    arguments: dict = Field(default_factory=dict)
    bot_id: int
    group_id: int | None = None
    user_id: int
    request_id: str = Field(min_length=1, max_length=128)


def _require_tools_auth(authorization: str | None, api_key: str | None) -> None:
    if authorization and ai_bearer.verify_ai_bearer(authorization):
        return
    if api_key:
        from pallas.console.webui.console_login import verify_api_key

        if verify_api_key(api_key):
            return
    if not ai_bearer.resolve_ai_bearer_token():
        raise HTTPException(status_code=503, detail="ai_bearer_unconfigured")
    raise HTTPException(status_code=401, detail="ai_bearer_required")


async def _load_pending_task(task_id: str) -> dict | None:
    from pallas.core.platform.coord.redis_settings import coord_redis_task_required

    if coord_redis_task_required():
        from pallas.core.platform.shard.coord.ai_task_registry import AiTaskRedisError, get_ai_task_record

        try:
            return get_ai_task_record(task_id)
        except AiTaskRedisError as exc:
            raise HTTPException(status_code=503, detail="task_lookup_retry") from exc
    from pallas.core.foundation.config import TaskManager

    return await TaskManager.get_task(task_id)


def build_tool_context(body: LlmToolExecuteRequest, task: dict) -> ToolInvokeContext:
    """按任务登记构造工具上下文；校验 request_id/任务类型/身份断言/social 阻挡。"""
    from pallas.product.llm.tools.registry import from_provider_tool_name

    request_id = str(body.request_id or "").strip()
    if not _REQUEST_ID_RE.match(request_id):
        raise HTTPException(status_code=400, detail="invalid_request_id")
    task_type = str(task.get("task_type") or "").strip()
    if task_type not in _LLM_TASK_TYPES:
        raise HTTPException(status_code=403, detail="tools_require_llm_task_context")
    for field, provided in (("bot_id", body.bot_id), ("group_id", body.group_id), ("user_id", body.user_id)):
        bound = task.get(field)
        if bound is None:
            if provided is not None:
                raise HTTPException(status_code=403, detail=f"{field}_mismatch")
            continue
        if int(bound) != int(provided):
            raise HTTPException(status_code=403, detail=f"{field}_mismatch")
    resolved = from_provider_tool_name(body.name)
    if resolved.startswith("social."):
        raise HTTPException(status_code=403, detail="social_tools_require_task_context")
    return ToolInvokeContext(
        bot_id=int(task.get("bot_id")),
        group_id=int(task["group_id"]) if task.get("group_id") is not None else None,
        user_id=int(task.get("user_id") or 0),
        request_id=request_id,
        source_segments=tuple(
            item for item in (task.get("command_source_segments") or []) if isinstance(item, dict) and item.get("type")
        ),
    )


def register_llm_tools_http() -> None:
    from nonebot import get_app

    app = get_app()
    install_ai_boundary_guard(app)

    @app.post("/pallas/api/internal/llm/tools/execute")
    async def llm_tool_execute_route(
        body: LlmToolExecuteRequest,
        authorization: str | None = Header(default=None),
        x_pallas_api_key: str | None = Header(default=None, alias="X-Pallas-Api-Key"),
    ) -> dict:
        from pallas.product.llm.tools.registry import execute_tool_async, from_provider_tool_name

        _require_tools_auth(authorization, x_pallas_api_key)
        task = await _load_pending_task(str(body.request_id or "").strip())
        if not task:
            raise HTTPException(status_code=404, detail="pending_task_not_found")
        ctx = build_tool_context(body, task)
        result = await execute_tool_async(from_provider_tool_name(body.name), body.arguments, context=ctx)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result)
        return result
