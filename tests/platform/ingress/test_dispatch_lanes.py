from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from nonebot.internal.rule import Rule
from nonebot.rule import command, to_me

from pallas.core.platform.ingress import dispatch_lanes, dispatch_runtime_config, message_load
from pallas.core.platform.ingress.dispatch_lanes import DispatchLane, LaneController


class _CommandMatcher:
    plugin_name = "packages.help"
    rule = Rule(command("foo"))


class _AiMatcher:
    plugin_name = "packages.llm_chat"
    rule = Rule(to_me())


class _RegexMatcher:
    plugin_name = "packages.duel"
    rule = Rule(to_me())


class _ChatMatcher:
    plugin_name = "packages.chat"
    rule = Rule(to_me())


class _SingMatcher:
    plugin_name = "packages.sing"
    rule = Rule(to_me())


@pytest.fixture(autouse=True)
def reset_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pallas.core.platform.ingress.fleet_dispatch_scale.connected_bot_count",
        lambda: 1,
    )
    dispatch_runtime_config.clear_ingress_dispatch_runtime_config_cache()
    dispatch_lanes.clear_dispatch_lanes_cache()
    dispatch_lanes.uninstall_dispatch_lanes()
    message_load.reset_message_load_for_tests()
    yield
    dispatch_runtime_config.clear_ingress_dispatch_runtime_config_cache()
    dispatch_lanes.clear_dispatch_lanes_cache()
    dispatch_lanes.uninstall_dispatch_lanes()
    message_load.reset_message_load_for_tests()


def test_normalize_lane_accepts_legacy_names() -> None:
    assert dispatch_lanes.normalize_lane("passive_ai") == DispatchLane.REMOTE
    assert dispatch_lanes.normalize_lane("command_exact") == DispatchLane.COMMAND
    assert dispatch_lanes.normalize_lane("passive_db") == DispatchLane.STORAGE


def test_lane_for_matcher_command_and_chat_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dispatch_lanes, "plugin_lane_override", lambda _module: None)
    assert dispatch_lanes.lane_for_matcher(_CommandMatcher) == DispatchLane.COMMAND
    assert dispatch_lanes.lane_for_matcher(_AiMatcher) == DispatchLane.CHAT


def test_lane_for_matcher_uses_plugin_lane_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dispatch_lanes,
        "plugin_lane_override",
        lambda module: "remote" if module in {"llm_chat", "ollama"} else None,
    )
    assert dispatch_lanes.lane_for_matcher(_AiMatcher) == DispatchLane.REMOTE


def test_lane_for_matcher_marks_chat_and_sing_as_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dispatch_lanes,
        "plugin_lane_override",
        lambda module: "remote" if module in {"chat", "sing"} else None,
    )
    assert dispatch_lanes.lane_for_matcher(_ChatMatcher) == DispatchLane.REMOTE
    assert dispatch_lanes.lane_for_matcher(_SingMatcher) == DispatchLane.REMOTE


def test_storage_limit_tightens_under_pool_pressure(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = LaneController(DispatchLane.STORAGE, 8)
    monkeypatch.setattr(dispatch_lanes, "pg_pool_under_pressure", lambda **kwargs: False)
    assert controller.effective_limit() == 8
    monkeypatch.setattr(dispatch_lanes, "pg_pool_under_pressure", lambda **kwargs: True)
    assert controller.effective_limit() == 4


def test_lane_limits_read_runtime_config_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SimpleNamespace(
        dispatch_lanes_enabled=False,
        lane_acquire_timeout_sec=0.25,
        lane_busy_reply=False,
        lane_command=3,
        lane_chat=5,
        lane_storage=7,
        lane_remote=9,
    )
    monkeypatch.setattr(dispatch_lanes, "get_ingress_dispatch_runtime_config", lambda: config)

    assert dispatch_lanes.dispatch_lanes_enabled() is False
    assert dispatch_lanes.lane_acquire_timeout_sec() == 0.25
    assert dispatch_lanes.lane_busy_reply_enabled() is False
    limits = dispatch_lanes.default_lane_limits()
    assert limits[DispatchLane.COMMAND] == 3
    assert limits[DispatchLane.CHAT] == 5
    assert limits[DispatchLane.STORAGE] == 7
    assert limits[DispatchLane.REMOTE] == 9


def test_install_dispatch_lanes_uses_snapshot_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dispatch_lanes,
        "default_lane_limits",
        lambda: {
            DispatchLane.COMMAND: 12,
            DispatchLane.TOOL: 4,
            DispatchLane.CHAT: 9,
            DispatchLane.STORAGE: 6,
            DispatchLane.REMOTE: 3,
        },
    )
    dispatch_lanes.install_dispatch_lanes()
    controller = dispatch_lanes.lane_controller(DispatchLane.STORAGE)
    assert controller is not None
    assert controller.base_limit == 6
    assert dispatch_lanes.lane_controller(DispatchLane.REMOTE).base_limit == 3


@pytest.mark.asyncio
async def test_config_refresh_keeps_lane_controller_identity_and_in_use(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = {
        DispatchLane.COMMAND: 2,
        DispatchLane.TOOL: 4,
        DispatchLane.CHAT: 6,
        DispatchLane.STORAGE: 8,
        DispatchLane.REMOTE: 4,
    }
    monkeypatch.setattr(dispatch_lanes, "default_lane_limits", lambda: dict(limits))
    dispatch_lanes.install_dispatch_lanes()
    controller = dispatch_lanes.lane_controller(DispatchLane.COMMAND)
    assert controller is not None
    assert (await controller.acquire(0.01))[0] is True

    limits[DispatchLane.COMMAND] = 1
    dispatch_lanes.clear_dispatch_lanes_cache()

    assert dispatch_lanes.lane_controller(DispatchLane.COMMAND) is controller
    assert controller.in_use == 1
    assert dispatch_lanes.lane_status()[DispatchLane.COMMAND] == {"limit": 1, "in_use": 1}
    await controller.release()
    assert controller.in_use == 0


@pytest.mark.asyncio
async def test_refresh_keeps_adaptive_chat_expansion(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = {
        DispatchLane.COMMAND: 16,
        DispatchLane.TOOL: 4,
        DispatchLane.CHAT: 6,
        DispatchLane.STORAGE: 8,
        DispatchLane.REMOTE: 4,
    }
    monkeypatch.setattr(dispatch_lanes, "default_lane_limits", lambda: dict(limits))
    dispatch_lanes.install_dispatch_lanes()
    controller = dispatch_lanes.lane_controller(DispatchLane.CHAT)
    assert controller is not None
    assert await dispatch_lanes.set_lane_limit(DispatchLane.CHAT, 9) is True

    dispatch_lanes.clear_dispatch_lanes_cache()

    assert dispatch_lanes.lane_status()[DispatchLane.CHAT] == {"limit": 9, "in_use": 0}


@pytest.mark.asyncio
async def test_metadata_refresh_does_not_bypass_lane_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dispatch_lanes,
        "default_lane_limits",
        lambda: {
            DispatchLane.COMMAND: 1,
            DispatchLane.TOOL: 4,
            DispatchLane.CHAT: 6,
            DispatchLane.STORAGE: 8,
            DispatchLane.REMOTE: 4,
        },
    )
    dispatch_lanes.install_dispatch_lanes()
    controller = dispatch_lanes.lane_controller(DispatchLane.COMMAND)
    assert controller is not None
    assert (await dispatch_lanes.acquire_lane(DispatchLane.COMMAND, wait_budget_sec=0.01))[0] is True

    dispatch_lanes.clear_dispatch_lanes_cache()

    acquired, _wait_ms = await dispatch_lanes.acquire_lane(DispatchLane.COMMAND, wait_budget_sec=0.01)
    assert acquired is False
    assert dispatch_lanes.lane_status()[DispatchLane.COMMAND] == {"limit": 1, "in_use": 1}
    await dispatch_lanes.release_lane(DispatchLane.COMMAND)
    assert controller.in_use == 0


@pytest.mark.asyncio
async def test_lowered_limit_blocks_new_acquisitions_until_released(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = {
        DispatchLane.COMMAND: 2,
        DispatchLane.TOOL: 4,
        DispatchLane.CHAT: 6,
        DispatchLane.STORAGE: 8,
        DispatchLane.REMOTE: 4,
    }
    monkeypatch.setattr(dispatch_lanes, "default_lane_limits", lambda: dict(limits))
    dispatch_lanes.install_dispatch_lanes()
    controller = dispatch_lanes.lane_controller(DispatchLane.COMMAND)
    assert controller is not None
    assert (await controller.acquire(0.01))[0] is True
    assert (await controller.acquire(0.01))[0] is True

    limits[DispatchLane.COMMAND] = 1
    dispatch_lanes.clear_dispatch_lanes_cache()

    assert controller.in_use == 2
    acquired, _wait_ms = await dispatch_lanes.acquire_lane(DispatchLane.COMMAND, wait_budget_sec=0.01)
    assert acquired is False
    await controller.release()
    acquired, _wait_ms = await dispatch_lanes.acquire_lane(DispatchLane.COMMAND, wait_budget_sec=0.01)
    assert acquired is False
    await controller.release()
    assert controller.in_use == 0
    assert (await dispatch_lanes.acquire_lane(DispatchLane.COMMAND, wait_budget_sec=0.01))[0] is True
    await dispatch_lanes.release_lane(DispatchLane.COMMAND)


@pytest.mark.asyncio
async def test_startup_disabled_lanes_require_restart_to_enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dispatch_lanes, "dispatch_lanes_enabled", lambda: False)
    dispatch_lanes.install_dispatch_lanes()

    assert dispatch_lanes.lane_controller(DispatchLane.COMMAND) is None
    acquired, wait_ms = await dispatch_lanes.acquire_lane(DispatchLane.COMMAND, wait_budget_sec=0.0)
    assert (acquired, wait_ms) == (True, 0.0)

    monkeypatch.setattr(dispatch_lanes, "dispatch_lanes_enabled", lambda: True)
    dispatch_lanes.clear_dispatch_lanes_cache()

    assert dispatch_lanes.lane_controller(DispatchLane.COMMAND) is None
    assert dispatch_lanes.dispatch_lanes_runtime_enabled() is False

    dispatch_lanes.uninstall_dispatch_lanes()
    dispatch_lanes.install_dispatch_lanes()

    assert dispatch_lanes.lane_controller(DispatchLane.COMMAND) is not None
    assert dispatch_lanes.dispatch_lanes_runtime_enabled() is True


@pytest.mark.asyncio
async def test_wrapper_and_acquire_use_stable_runtime_enabled_state(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatch_lanes.install_dispatch_lanes()
    controller = dispatch_lanes.lane_controller(DispatchLane.COMMAND)
    assert controller is not None
    assert (await controller.acquire(0.01))[0] is True

    values = iter([True, False])
    monkeypatch.setattr(dispatch_lanes, "dispatch_lanes_enabled", lambda: next(values, False))
    run_mock = AsyncMock()
    monkeypatch.setattr("nonebot.message.check_and_run_matcher", run_mock)

    result = await dispatch_lanes.check_and_run_matcher_with_lane(
        _CommandMatcher,
        AsyncMock(),
        MagicMock(),
        {},
        MagicMock(),
        {},
        command_traffic=True,
    )

    assert result.acquired is True
    run_mock.assert_awaited_once()
    assert controller.in_use == 1
    await controller.release()
    assert controller.in_use == 0


@pytest.mark.asyncio
async def test_new_config_revision_syncs_existing_controller_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = {
        DispatchLane.COMMAND: 4,
        DispatchLane.TOOL: 4,
        DispatchLane.CHAT: 6,
        DispatchLane.STORAGE: 8,
        DispatchLane.REMOTE: 4,
    }
    snapshot = SimpleNamespace()
    monkeypatch.setattr(dispatch_lanes, "get_ingress_dispatch_runtime_config", lambda: snapshot)
    monkeypatch.setattr(dispatch_lanes, "default_lane_limits", lambda: dict(limits))
    monkeypatch.setattr(dispatch_lanes, "dispatch_lanes_enabled", lambda: True)
    dispatch_lanes.install_dispatch_lanes()
    controller = dispatch_lanes.lane_controller(DispatchLane.COMMAND)
    assert controller is not None
    assert (await controller.acquire(0.01))[0] is True
    assert (await controller.acquire(0.01))[0] is True

    limits[DispatchLane.COMMAND] = 1
    monkeypatch.setattr(dispatch_lanes, "get_ingress_dispatch_runtime_config", lambda: SimpleNamespace())

    acquired, _wait_ms = await dispatch_lanes.acquire_lane(DispatchLane.COMMAND, wait_budget_sec=0.01)

    assert acquired is False
    assert dispatch_lanes.lane_controller(DispatchLane.COMMAND) is controller
    assert controller.in_use == 2
    assert dispatch_lanes.lane_status()[DispatchLane.COMMAND] == {"limit": 1, "in_use": 2}
    await controller.release()
    await controller.release()
    assert controller.in_use == 0
    assert (await dispatch_lanes.acquire_lane(DispatchLane.COMMAND, wait_budget_sec=0.01))[0] is True
    await dispatch_lanes.release_lane(DispatchLane.COMMAND)


@pytest.mark.asyncio
async def test_raising_limit_wakes_waiting_acquire_after_config_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    limits = {
        DispatchLane.COMMAND: 1,
        DispatchLane.TOOL: 4,
        DispatchLane.CHAT: 6,
        DispatchLane.STORAGE: 8,
        DispatchLane.REMOTE: 4,
    }
    monkeypatch.setattr(dispatch_lanes, "default_lane_limits", lambda: dict(limits))
    dispatch_lanes.install_dispatch_lanes()
    controller = dispatch_lanes.lane_controller(DispatchLane.COMMAND)
    assert controller is not None
    assert (await controller.acquire(0.01))[0] is True

    waiting = asyncio.create_task(controller.acquire(0.5))
    await asyncio.sleep(0)
    limits[DispatchLane.COMMAND] = 2
    dispatch_lanes.clear_dispatch_lanes_cache()

    assert (await asyncio.wait_for(waiting, timeout=0.3))[0] is True
    await controller.release()
    await controller.release()


@pytest.mark.asyncio
async def test_lane_controller_blocks_when_full() -> None:
    controller = LaneController(DispatchLane.REMOTE, 1)
    ok1, _ = await controller.acquire(0.2)
    ok2, _ = await controller.acquire(0.05)
    assert ok1 is True
    assert ok2 is False
    await controller.release()
    ok3, _ = await controller.acquire(0.2)
    assert ok3 is True
    await controller.release()


@pytest.mark.asyncio
async def test_record_lane_wait_signals_overload() -> None:
    message_load.reset_message_load_for_tests()
    message_load.record_lane_wait(float(message_load.lane_wait_overload_threshold_ms()))
    assert message_load.should_pause_tasks() is True


@pytest.mark.asyncio
async def test_check_and_run_matcher_with_lane_skips_when_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatch_lanes.install_dispatch_lanes()
    controller = dispatch_lanes.lane_controller(DispatchLane.REMOTE)
    assert controller is not None
    await controller.acquire(0.01)
    await controller.acquire(0.01)
    await controller.acquire(0.01)
    await controller.acquire(0.01)

    run_mock = AsyncMock()
    monkeypatch.setattr(
        dispatch_lanes,
        "plugin_lane_override",
        lambda module: "remote" if module in {"llm_chat", "ollama"} else None,
    )
    monkeypatch.setattr("nonebot.message.check_and_run_matcher", run_mock)

    result = await dispatch_lanes.check_and_run_matcher_with_lane(
        _AiMatcher,
        AsyncMock(),
        MagicMock(),
        {},
        MagicMock(),
        {},
        command_traffic=True,
    )
    assert result.acquired is False
    assert result.lane_busy is True
    run_mock.assert_not_awaited()
    for _ in range(4):
        await controller.release()


@pytest.mark.asyncio
async def test_check_and_run_matcher_with_lane_runs_hard_wake_when_remote_is_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatch_lanes.install_dispatch_lanes()
    remote = dispatch_lanes.lane_controller(DispatchLane.REMOTE)
    assert remote is not None
    for _ in range(remote.base_limit):
        ok, _ = await remote.acquire(0.01)
        assert ok is True

    run_mock = AsyncMock()
    monkeypatch.setattr(
        dispatch_lanes,
        "plugin_lane_override",
        lambda module: "remote" if module in {"llm_chat", "ollama"} else None,
    )
    monkeypatch.setattr("nonebot.message.check_and_run_matcher", run_mock)

    result = await dispatch_lanes.check_and_run_matcher_with_lane(
        _AiMatcher,
        AsyncMock(),
        MagicMock(),
        {},
        MagicMock(),
        {},
        command_traffic=False,
        hard_speak_trigger=True,
    )

    assert result.acquired is True
    run_mock.assert_awaited_once()
    for _ in range(remote.base_limit):
        await remote.release()


@pytest.mark.asyncio
async def test_synthetic_llm_command_uses_dedicated_tool_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatch_lanes.install_dispatch_lanes()
    command_lane = dispatch_lanes.lane_controller(DispatchLane.COMMAND)
    assert command_lane is not None
    for _ in range(command_lane.base_limit):
        ok, _ = await command_lane.acquire(0.01)
        assert ok is True

    run_mock = AsyncMock()
    monkeypatch.setattr("nonebot.message.check_and_run_matcher", run_mock)

    result = await dispatch_lanes.check_and_run_matcher_with_lane(
        _CommandMatcher,
        AsyncMock(),
        MagicMock(),
        {},
        MagicMock(),
        {},
        command_traffic=True,
        synthetic_llm_command=True,
    )

    assert result.acquired is True
    run_mock.assert_awaited_once()
    for _ in range(command_lane.base_limit):
        await command_lane.release()


@pytest.mark.asyncio
async def test_chat_lane_limit_can_be_adjusted_and_observed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dispatch_lanes,
        "default_lane_limits",
        lambda: {
            DispatchLane.COMMAND: 16,
            DispatchLane.TOOL: 4,
            DispatchLane.CHAT: 6,
            DispatchLane.STORAGE: 8,
            DispatchLane.REMOTE: 4,
        },
    )
    dispatch_lanes.install_dispatch_lanes()

    assert dispatch_lanes.lane_status()[DispatchLane.CHAT] == {"limit": 6, "in_use": 0}
    assert await dispatch_lanes.set_lane_limit(DispatchLane.CHAT, 8) is True
    assert dispatch_lanes.lane_status()[DispatchLane.CHAT] == {"limit": 8, "in_use": 0}


@pytest.mark.asyncio
async def test_increasing_lane_limit_wakes_waiting_matcher() -> None:
    controller = LaneController(DispatchLane.CHAT, 1)
    acquired, _ = await controller.acquire(0.01)
    assert acquired is True

    waiting = asyncio.create_task(controller.acquire(0.2))
    await asyncio.sleep(0)
    await controller.set_limit(2)

    assert (await waiting)[0] is True
    await controller.release()
    await controller.release()
