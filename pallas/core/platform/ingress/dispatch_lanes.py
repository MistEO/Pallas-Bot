from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import TYPE_CHECKING

from nonebot import get_loaded_plugins
from nonebot.log import logger

from pallas.core.foundation.db.pool_budget import pg_pool_capacity, pg_pool_under_pressure
from pallas.core.platform.ingress.dispatch_runtime_config import (
    dispatch_env_int_any,
    get_ingress_dispatch_runtime_config,
)
from pallas.core.platform.ingress.fleet_dispatch_scale import scaled_dispatch_int
from pallas.core.platform.ingress.matcher_activation import iter_matcher_checker_calls, matcher_is_command_only
from pallas.core.platform.ingress.route_index import matcher_module_key, plugin_module_key_from_plugin

if TYPE_CHECKING:
    from nonebot.adapters import Bot, Event
    from nonebot.matcher import Matcher

_COMMAND_CHECKER_NAMES = frozenset({"CommandRule", "ShellCommandRule"})
_LANE_BUSY_REPLY = "我习惯了站着不动思考。有时候啊，也会被大家突然戳一戳，看看睡着了没有"
_LANE_ALIASES: dict[str, str] = {
    "command_exact": "command",
    "command_regex": "command",
    "passive_light": "chat",
    "passive_db": "storage",
    "passive_http": "remote",
    "passive_ai": "remote",
    "passive_render": "remote",
}
_LANES: dict[str, LaneController] | None = None
_LANES_RUNTIME_ENABLED: bool | None = None
_PLUGIN_LANE_CACHE: dict[str, str | None] | None = None
_LAST_LIMIT_SNAPSHOT: object | None = None
_WAKE_TASKS: set[asyncio.Task[None]] = set()


class DispatchLane(StrEnum):
    COMMAND = "command"
    TOOL = "tool"
    CHAT = "chat"
    STORAGE = "storage"
    REMOTE = "remote"


@dataclass(frozen=True, slots=True)
class MatcherLaneResult:
    acquired: bool
    lane_busy: bool


class LaneController:
    def __init__(self, lane: str, base_limit: int) -> None:
        self.lane = lane
        self.base_limit = max(1, int(base_limit))
        self.configured_limit = self.base_limit
        self.in_use = 0
        self._cond = asyncio.Condition()

    def effective_limit(self) -> int:
        limit = self.base_limit
        if self.lane == DispatchLane.STORAGE and pg_pool_under_pressure(threshold=0.75):
            return max(1, limit // 2)
        return limit

    async def set_limit(self, limit: int) -> None:
        async with self._cond:
            self.base_limit = max(1, int(limit))
            self._cond.notify_all()

    def sync_configured_limit(self, limit: int) -> None:
        """配置值变化时原地重设上限；无关刷新不打断自适应扩容。"""
        limit = max(1, int(limit))
        if limit == self.configured_limit:
            return
        self.configured_limit = limit
        self.apply_limit(limit)

    def apply_limit(self, limit: int) -> None:
        """原地更新上限：已持有的执行不受影响，等待者按新上限放行。"""
        limit = max(1, int(limit))
        if limit == self.base_limit:
            return
        increased = limit > self.base_limit
        self.base_limit = limit
        if increased:
            self.wake_waiters()

    def wake_waiters(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self.notify_waiters())
        _WAKE_TASKS.add(task)
        task.add_done_callback(_WAKE_TASKS.discard)

    async def notify_waiters(self) -> None:
        try:
            async with self._cond:
                self._cond.notify_all()
        except RuntimeError:
            return

    def snapshot(self) -> dict[str, int]:
        return {"limit": self.effective_limit(), "in_use": self.in_use}

    async def acquire(self, wait_budget_sec: float) -> tuple[bool, float]:
        start = time.monotonic()
        async with self._cond:
            while self.in_use >= self.effective_limit():
                remaining = wait_budget_sec - (time.monotonic() - start)
                if remaining <= 0:
                    return False, (time.monotonic() - start) * 1000.0
                try:
                    await asyncio.wait_for(self._cond.wait(), timeout=remaining)
                except TimeoutError:
                    return False, (time.monotonic() - start) * 1000.0
            self.in_use += 1
            return True, (time.monotonic() - start) * 1000.0

    async def release(self) -> None:
        async with self._cond:
            self.in_use = max(0, self.in_use - 1)
            self._cond.notify(1)


def normalize_lane(raw: str | None) -> str | None:
    text = (raw or "").strip().lower()
    if not text:
        return None
    if text in _LANE_ALIASES:
        return _LANE_ALIASES[text]
    try:
        return str(DispatchLane(text))
    except ValueError:
        return text


def dispatch_lanes_enabled() -> bool:
    return get_ingress_dispatch_runtime_config().dispatch_lanes_enabled


def dispatch_lanes_runtime_enabled() -> bool:
    """启动时确定的运行态；开关变更需重启，运行期保存不会切换。"""
    if _LANES_RUNTIME_ENABLED is None:
        install_dispatch_lanes()
    return _LANES_RUNTIME_ENABLED is True


def lane_acquire_timeout_sec() -> float:
    return get_ingress_dispatch_runtime_config().lane_acquire_timeout_sec


def lane_busy_reply_enabled() -> bool:
    return get_ingress_dispatch_runtime_config().lane_busy_reply


def default_lane_limits() -> dict[str, int]:
    config = get_ingress_dispatch_runtime_config()
    tool_default = scaled_dispatch_int(4, per_bot=1, cap=16)
    return {
        DispatchLane.COMMAND: config.lane_command,
        DispatchLane.TOOL: dispatch_env_int_any(
            ("PALLAS_LANE_TOOL",),
            default=tool_default,
            minimum=1,
            maximum=64,
        ),
        DispatchLane.CHAT: config.lane_chat,
        DispatchLane.STORAGE: config.lane_storage,
        DispatchLane.REMOTE: config.lane_remote,
    }


def clear_dispatch_lanes_cache() -> None:
    """配置保存或插件元数据刷新：重置路由映射，并在原 controller 上同步上限。"""
    global _PLUGIN_LANE_CACHE, _LAST_LIMIT_SNAPSHOT
    _PLUGIN_LANE_CACHE = None
    _LAST_LIMIT_SNAPSHOT = None
    lane_for_matcher.cache_clear()
    install_dispatch_lanes()


def sync_dispatch_lane_limits() -> None:
    """新快照出现时原地同步上限；保留 controller 身份/占用，不覆盖自适应扩容。"""
    global _LAST_LIMIT_SNAPSHOT
    if _LANES_RUNTIME_ENABLED is not True or not _LANES:
        return
    config = get_ingress_dispatch_runtime_config()
    if config is _LAST_LIMIT_SNAPSHOT:
        return
    _LAST_LIMIT_SNAPSHOT = config
    limits = default_lane_limits()
    for lane, controller in _LANES.items():
        controller.sync_configured_limit(limits.get(lane, controller.configured_limit))


def plugin_lane_override(module_key: str) -> str | None:
    global _PLUGIN_LANE_CACHE
    if _PLUGIN_LANE_CACHE is None:
        mapping: dict[str, str | None] = {}
        for plugin in get_loaded_plugins():
            key = plugin_module_key_from_plugin(plugin)
            meta = getattr(plugin, "metadata", None)
            extra = getattr(meta, "extra", None) if meta is not None else None
            lane: str | None = None
            if isinstance(extra, dict):
                ingress_route = extra.get("ingress_route")
                if isinstance(ingress_route, dict):
                    lane = normalize_lane(str(ingress_route.get("lane") or ""))
            mapping[key] = lane or None
        _PLUGIN_LANE_CACHE = mapping
    return _PLUGIN_LANE_CACHE.get(module_key)


def _checker_name(checker: object) -> str:
    return type(checker).__name__


@lru_cache(maxsize=512)
def lane_for_matcher(matcher: type[Matcher]) -> str:
    module_key = matcher_module_key(matcher)
    override = plugin_lane_override(module_key)
    if override:
        return override

    calls = tuple(iter_matcher_checker_calls(matcher))
    if matcher_is_command_only(matcher) or any(_checker_name(call) in _COMMAND_CHECKER_NAMES for call in calls):
        return DispatchLane.COMMAND

    return DispatchLane.CHAT


def install_dispatch_lanes() -> None:
    global _LANES, _LANES_RUNTIME_ENABLED
    if _LANES_RUNTIME_ENABLED is None:
        _LANES_RUNTIME_ENABLED = dispatch_lanes_enabled()
        if not _LANES_RUNTIME_ENABLED:
            _LANES = {}
            logger.debug("Dispatch lanes disabled at startup; restart is required to enable them.")
            return
    if _LANES_RUNTIME_ENABLED is not True:
        return
    if not _LANES:
        limits = default_lane_limits()
        _LANES = {lane: LaneController(lane, limit) for lane, limit in limits.items()}
        logger.debug(
            "Dispatch lanes initialized with command [{}], tool [{}], chat [{}], storage [{}], "
            "remote [{}], and pool capacity [{}].",
            limits[DispatchLane.COMMAND],
            limits[DispatchLane.TOOL],
            limits[DispatchLane.CHAT],
            limits[DispatchLane.STORAGE],
            limits[DispatchLane.REMOTE],
            pg_pool_capacity(),
        )
    sync_dispatch_lane_limits()


def uninstall_dispatch_lanes() -> None:
    global _LANES, _LANES_RUNTIME_ENABLED, _LAST_LIMIT_SNAPSHOT
    _LANES = None
    _LANES_RUNTIME_ENABLED = None
    _LAST_LIMIT_SNAPSHOT = None


def lane_controller(lane: str) -> LaneController | None:
    if _LANES is None:
        return None
    normalized = normalize_lane(lane)
    if normalized is None:
        return None
    return _LANES.get(normalized)


def lane_status() -> dict[str, dict[str, int]]:
    if _LANES is None:
        return {}
    return {str(lane): controller.snapshot() for lane, controller in _LANES.items()}


async def set_lane_limit(lane: str, limit: int) -> bool:
    controller = lane_controller(lane)
    if controller is None:
        return False
    await controller.set_limit(limit)
    return True


async def acquire_lane(lane: str, *, wait_budget_sec: float | None = None) -> tuple[bool, float]:
    normalized = normalize_lane(lane) or lane
    if not dispatch_lanes_runtime_enabled():
        return True, 0.0
    sync_dispatch_lane_limits()
    controller = lane_controller(normalized)
    if controller is None:
        return True, 0.0
    budget = lane_acquire_timeout_sec() if wait_budget_sec is None else max(0.0, wait_budget_sec)
    if normalized == DispatchLane.STORAGE and pg_pool_under_pressure(threshold=0.80) and budget > 0:
        budget = min(budget, 0.05)
    return await controller.acquire(budget)


async def release_lane(lane: str) -> None:
    normalized = normalize_lane(lane) or lane
    controller = lane_controller(normalized)
    if controller is None:
        return
    await controller.release()


async def maybe_send_lane_busy_reply(
    bot: Bot,
    event: Event,
    *,
    command_traffic: bool,
    already_sent: bool,
) -> bool:
    if already_sent or not command_traffic or not lane_busy_reply_enabled():
        return already_sent
    from nonebot.adapters.onebot.v11 import GroupMessageEvent

    if not isinstance(event, GroupMessageEvent):
        return already_sent
    try:
        await bot.send(event, _LANE_BUSY_REPLY)
    except Exception as exc:
        logger.debug("dispatch_lanes: busy reply failed: {}", exc)
        return already_sent
    return True


async def check_and_run_matcher_with_lane(
    matcher: type[Matcher],
    bot: Bot,
    event: Event,
    state: dict,
    stack,
    dependency_cache: dict,
    *,
    command_traffic: bool,
    synthetic_llm_command: bool = False,
    hard_speak_trigger: bool = False,
) -> MatcherLaneResult:
    import nonebot.message as nb_message

    from pallas.core.platform.ingress.message_load import record_lane_wait

    if not dispatch_lanes_runtime_enabled():
        await nb_message.check_and_run_matcher(matcher, bot, event, state, stack, dependency_cache)
        return MatcherLaneResult(acquired=True, lane_busy=False)

    if synthetic_llm_command:
        lane = DispatchLane.TOOL
    elif hard_speak_trigger:
        lane = DispatchLane.COMMAND
    else:
        lane = lane_for_matcher(matcher)
    acquired, wait_ms = await acquire_lane(lane)
    record_lane_wait(wait_ms, busy=not acquired)
    if not acquired:
        return MatcherLaneResult(acquired=False, lane_busy=command_traffic)
    try:
        await nb_message.check_and_run_matcher(matcher, bot, event, state, stack, dependency_cache)
    finally:
        await release_lane(lane)
    return MatcherLaneResult(acquired=True, lane_busy=False)
