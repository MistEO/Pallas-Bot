"""分片 hub：将 Pallas-Bot-AI 的 /callback 转发到登记 worker。

hub 先认证/校验/限字节（边界守卫与路由层已做）再转发；只构造必需 auth header，
不转 Cookie/Forwarded 等，trust_env=False 且不跟随重定向；worker 侧同样校验 AI Bearer。
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, UploadFile
from nonebot import logger

from pallas.core.platform.ai_callback.ai_bearer import ai_bearer_headers
from pallas.core.platform.shard.coord.ai_task_registry import AiTaskRedisError, resolve_worker_port_for_task


async def _read_bounded(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            await file.close()
            raise HTTPException(status_code=413, detail="file_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


async def forward_ai_callback_to_worker(
    task_id: str,
    *,
    status: str,
    text: str | None = None,
    agent_trace: str | None = None,
    song_id: str | None = None,
    chunk_index: int | None = None,
    key: int | None = None,
    history_summary: str | None = None,
    history_keep_messages: int | None = None,
    file: UploadFile | None = None,
) -> dict[str, Any]:
    try:
        port = resolve_worker_port_for_task(task_id)
    except AiTaskRedisError as exc:
        raise HTTPException(status_code=503, detail="task_lookup_retry") from exc
    if port is None:
        raise HTTPException(status_code=404, detail="Task not found")

    data: dict[str, str] = {"status": status}
    if text is not None:
        data["text"] = text
    if agent_trace is not None:
        data["agent_trace"] = agent_trace
    if song_id is not None:
        data["song_id"] = str(song_id)
    if chunk_index is not None:
        data["chunk_index"] = str(chunk_index)
    if key is not None:
        data["key"] = str(key)
    if history_summary is not None:
        data["history_summary"] = history_summary
    if history_keep_messages is not None:
        data["history_keep_messages"] = str(int(history_keep_messages))

    files = None
    if file is not None:
        from pallas.core.platform.ai_callback.boundary_limits import callback_max_file_bytes

        body = await _read_bounded(file, callback_max_file_bytes())
        files = {"file": (file.filename or "audio", body, file.content_type or "application/octet-stream")}

    url = f"http://127.0.0.1:{port}/callback/{task_id}"
    timeout = httpx.Timeout(120.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            resp = await client.post(url, data=data, files=files, headers=ai_bearer_headers())
    except httpx.HTTPError as err:
        logger.warning("AI callback forwarding failed for task [{}] on port [{}]: [{}].", task_id, port, err)
        raise HTTPException(status_code=502, detail="分片节点回调不可达") from err

    if resp.status_code >= 400:
        logger.warning(
            "AI callback forwarding for task [{}] on port [{}] returned status [{}] with body [{}].",
            task_id,
            port,
            resp.status_code,
            resp.text[:200],
        )
        detail = "分片节点上未找到任务" if resp.status_code == 404 else "分片节点回调失败"
        raise HTTPException(status_code=resp.status_code, detail=detail)
    try:
        return resp.json()
    except Exception:
        return {"message": "ok"}
