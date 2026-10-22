"""异步任务 HTTP 回调路由。"""

from __future__ import annotations

from fastapi import File, Form, Header, HTTPException, Request, UploadFile
from nonebot import get_app

from pallas.core.platform.ai_callback import ai_bearer
from pallas.core.platform.ai_callback.boundary_guard import install_ai_boundary_guard
from pallas.core.platform.ai_callback.internal_auth import (
    INTERNAL_TOKEN_HEADER,
)
from pallas.core.platform.ai_callback.runner import run_ai_callback, validate_callback_payload
from pallas.core.platform.ai_callback.task_registration import (
    AiTaskRegistrationRequest,
    register_ai_task_from_aux,
    unregister_ai_task_from_aux,
)
from pallas.core.platform.bot_runtime.roles import is_hub_role
from pallas.core.platform.shard.coord.ai_callback_forward import forward_ai_callback_to_worker

_http_registered = False


def _require_ai_bearer(authorization: str | None) -> None:
    if not ai_bearer.resolve_ai_bearer_token():
        raise HTTPException(status_code=503, detail="ai_bearer_unconfigured")
    if not ai_bearer.verify_ai_bearer(authorization):
        raise HTTPException(status_code=401, detail="ai_bearer_required")


def register_ai_callback_http() -> None:
    global _http_registered
    if _http_registered:
        return

    app = get_app()
    install_ai_boundary_guard(app)

    @app.post("/pallas/api/internal/ai/tasks/{task_id}")
    async def register_ai_task_route(
        task_id: str,
        body: AiTaskRegistrationRequest,
        request: Request,
        x_pallas_internal_token: str | None = Header(default=None, alias=INTERNAL_TOKEN_HEADER),
    ):
        if body.task_id != task_id:
            raise HTTPException(status_code=400, detail="task_id_mismatch")
        client_host = request.client.host if request.client else None
        return await register_ai_task_from_aux(
            task_id,
            body.task_status,
            client_host=client_host,
            internal_token=x_pallas_internal_token,
        )

    @app.delete("/pallas/api/internal/ai/tasks/{task_id}")
    async def unregister_ai_task_route(
        task_id: str,
        request: Request,
        x_pallas_internal_token: str | None = Header(default=None, alias=INTERNAL_TOKEN_HEADER),
    ):
        client_host = request.client.host if request.client else None
        return await unregister_ai_task_from_aux(
            task_id,
            client_host=client_host,
            internal_token=x_pallas_internal_token,
        )

    @app.post("/callback/{task_id}")
    async def ai_callback_route(
        task_id: str,
        status: str = Form(...),
        text: str | None = Form(None),
        agent_trace: str | None = Form(None),
        song_id: str | None = Form(None),
        chunk_index: int | None = Form(None),
        key: int | None = Form(None),
        history_summary: str | None = Form(None),
        history_keep_messages: int | None = Form(None),
        file: UploadFile | None = File(None),  # noqa: B008
        authorization: str | None = Header(default=None),
    ):
        _require_ai_bearer(authorization)
        validate_callback_payload(
            status=status,
            text=text,
            agent_trace=agent_trace,
            song_id=song_id,
            chunk_index=chunk_index,
            key=key,
            history_summary=history_summary,
            history_keep_messages=history_keep_messages,
            file=file,
        )
        if is_hub_role():
            return await forward_ai_callback_to_worker(
                task_id,
                status=status,
                text=text,
                agent_trace=agent_trace,
                song_id=song_id,
                chunk_index=chunk_index,
                key=key,
                history_summary=history_summary,
                history_keep_messages=history_keep_messages,
                file=file,
            )
        return await run_ai_callback(
            task_id,
            status=status,
            text=text,
            agent_trace=agent_trace,
            song_id=song_id,
            chunk_index=chunk_index,
            key=key,
            history_summary=history_summary,
            history_keep_messages=history_keep_messages,
            file=file,
        )

    _http_registered = True
