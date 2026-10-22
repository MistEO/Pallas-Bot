from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from pallas.core.foundation.config import TaskManager
from pallas.core.platform.ai_callback.internal_auth import (
    INTERNAL_TOKEN_HEADER,
    PURPOSE_AI_TASK_REGISTRATION,
    derive_internal_token,
)
from pallas.core.platform.ai_callback.task_registration import (
    register_ai_task_from_aux,
    register_ai_task_in_bot_process,
    unregister_ai_task_from_aux,
    unregister_ai_task_in_bot_process,
)


@pytest.fixture(autouse=True)
def isolate_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr("pallas.core.foundation.paths.DATA_ROOT", tmp_path)
    return tmp_path


def _token() -> str:
    return derive_internal_token(PURPOSE_AI_TASK_REGISTRATION)


@pytest.mark.asyncio
async def test_aux_task_registration_requires_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    add_task = AsyncMock()
    monkeypatch.setattr(
        "pallas.core.platform.ai_callback.task_registration.TaskManager.add_task",
        add_task,
    )

    with pytest.raises(HTTPException) as exc_info:
        await register_ai_task_from_aux("task-1", {"bot_id": "123"})

    assert exc_info.value.status_code == 403
    add_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_aux_task_registration_adds_task_with_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    add_task = AsyncMock(return_value="ok")
    monkeypatch.setattr(
        "pallas.core.platform.ai_callback.task_registration.TaskManager.add_task",
        add_task,
    )

    result = await register_ai_task_from_aux(
        "task-1",
        {"bot_id": "123", "group_id": 456, "task_type": "sing"},
        internal_token=_token(),
    )

    assert result == {"message": "ok"}
    add_task.assert_awaited_once_with(
        "task-1",
        {"bot_id": "123", "group_id": 456, "task_type": "sing"},
    )


@pytest.mark.asyncio
async def test_aux_task_registration_conflict_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pallas.core.platform.ai_callback.task_registration.TaskManager.add_task",
        AsyncMock(return_value="conflict"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await register_ai_task_from_aux("task-1", {"bot_id": "123"}, internal_token=_token())

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_aux_task_registration_rejects_invalid_task_id(monkeypatch: pytest.MonkeyPatch) -> None:
    add_task = AsyncMock()
    monkeypatch.setattr(
        "pallas.core.platform.ai_callback.task_registration.TaskManager.add_task",
        add_task,
    )

    with pytest.raises(HTTPException) as exc_info:
        await register_ai_task_from_aux("bad id!", {"bot_id": "123"}, internal_token=_token())

    assert exc_info.value.status_code == 400
    add_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_work_task_manager_registers_task_in_bot_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PALLAS_BOT_ROLE", "work")
    monkeypatch.setattr(
        "pallas.core.platform.shard.coord.ai_task_registry.register_ai_task",
        lambda _task_id, _task_status: "skipped",
    )
    register_remote = AsyncMock()
    monkeypatch.setattr(
        "pallas.core.platform.ai_callback.task_registration.register_ai_task_in_bot_process",
        register_remote,
    )
    monkeypatch.setattr(TaskManager, "_tasks", {})
    monkeypatch.setattr(TaskManager, "_terminal", {})

    await TaskManager.add_task("task-work", {"bot_id": "123", "task_type": "sing", "start_time": 1234.0})

    register_remote.assert_awaited_once_with(
        "task-work",
        {"bot_id": "123", "task_type": "sing", "start_time": 1234.0},
    )


@pytest.mark.asyncio
async def test_aux_task_unregistration_removes_task_with_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    remove_task = AsyncMock()
    monkeypatch.setattr(
        "pallas.core.platform.ai_callback.task_registration.TaskManager.remove_task",
        remove_task,
    )

    result = await unregister_ai_task_from_aux("task-1", internal_token=_token())

    assert result == {"message": "ok"}
    remove_task.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_aux_task_unregistration_requires_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    remove_task = AsyncMock()
    monkeypatch.setattr(
        "pallas.core.platform.ai_callback.task_registration.TaskManager.remove_task",
        remove_task,
    )

    with pytest.raises(HTTPException) as exc_info:
        await unregister_ai_task_from_aux("task-1")

    assert exc_info.value.status_code == 403
    remove_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_registration_client_posts_task_with_internal_header(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock()
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = response
    monkeypatch.setattr(
        "pallas.core.platform.ai_callback.task_registration.httpx.AsyncClient",
        lambda **_kwargs: client,
    )
    monkeypatch.setenv("PORT", "7969")

    await register_ai_task_in_bot_process("task-1", {"task_type": "sing"})

    call = client.post.await_args
    assert call.args[0] == "http://127.0.0.1:7969/pallas/api/internal/ai/tasks/task-1"
    assert call.kwargs["json"] == {"task_id": "task-1", "task_status": {"task_type": "sing"}}
    assert call.kwargs["headers"][INTERNAL_TOKEN_HEADER] == _token()
    response.raise_for_status.assert_called_once_with()


@pytest.mark.asyncio
async def test_unregistration_client_deletes_task_with_internal_header(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock()
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.delete.return_value = response
    monkeypatch.setattr(
        "pallas.core.platform.ai_callback.task_registration.httpx.AsyncClient",
        lambda **_kwargs: client,
    )
    monkeypatch.setenv("PORT", "7969")

    await unregister_ai_task_in_bot_process("task-1")

    call = client.delete.await_args
    assert call.args[0] == "http://127.0.0.1:7969/pallas/api/internal/ai/tasks/task-1"
    assert call.kwargs["headers"][INTERNAL_TOKEN_HEADER] == _token()
    response.raise_for_status.assert_called_once_with()
