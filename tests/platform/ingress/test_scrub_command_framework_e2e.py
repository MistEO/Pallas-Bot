"""群屏蔽词命令：真实 NoneBot 事件 → matcher 执行（框架 DI，非 helper 直调）。

控制并恢复全局 matchers / preprocessor / run_preprocessor / TrieRule 状态，
只装本地 fake bot 与 fake repo，不触真实 DB/网络。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot import matcher as nb_matcher
from nonebot import message as nb_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
from nonebot.rule import TrieRule

import packages.blacklist.scrub_commands as scrub_commands  # noqa: F401  注册真实命令前缀/ matcher
from pallas.core.platform.ingress.gate import message_scrub_global_hook
from pallas.core.platform.ingress.scrub_command_fence import scrub_command_target_fence
from pallas.product.message_scrub import group_extra, reload_message_scrub_caches


def _make_bot():
    from nonebot import get_driver
    from nonebot.adapters.onebot.v11 import Adapter, Bot

    bot = Bot(Adapter(get_driver()), self_id="100")
    bot.call_api = AsyncMock(return_value={"message_id": 1})  # type: ignore[method-assign]
    return bot


def _group_event(text: str, *, group_id: int = 1) -> GroupMessageEvent:
    return GroupMessageEvent(
        time=1,
        self_id=100,
        post_type="message",
        message_type="group",
        sub_type="normal",
        message_id=1,
        user_id=7,
        message=Message(text),
        raw_message=text,
        font=0,
        sender={"user_id": 7, "nickname": "a", "card": "", "role": "member"},
        group_id=group_id,
    )


@pytest.fixture
def framework_state(monkeypatch: pytest.MonkeyPatch):
    """快照并恢复 NoneBot 全局注册状态，避免污染其它测试。"""
    saved_matchers = {p: list(v) for p, v in nb_matcher.matchers.items()}
    saved_event_pre = set(nb_message._event_preprocessors)
    saved_event_post = set(nb_message._event_postprocessors)
    saved_run_pre = set(nb_message._run_preprocessors)
    saved_run_post = set(nb_message._run_postprocessors)
    saved_trie = dict(TrieRule.prefix)
    saved_handle_event = nb_message.handle_event

    nb_matcher.matchers.clear()
    nb_message._event_preprocessors.clear()
    nb_message._event_postprocessors.clear()
    nb_message._run_preprocessors.clear()
    nb_message._run_postprocessors.clear()

    reload_message_scrub_caches()
    group_extra.reset_group_scrub_snapshot()
    yield
    group_extra.reset_group_scrub_snapshot()
    reload_message_scrub_caches()

    from pallas.core.platform.ingress.matcher_dispatch import uninstall_matcher_dispatch

    uninstall_matcher_dispatch()
    nb_message.handle_event = saved_handle_event  # type: ignore[assignment]
    nb_matcher.matchers.clear()
    for priority, classes in saved_matchers.items():
        nb_matcher.matchers[priority] = list(classes)
    nb_message._event_preprocessors.clear()
    nb_message._event_preprocessors.update(saved_event_pre)
    nb_message._event_postprocessors.clear()
    nb_message._event_postprocessors.update(saved_event_post)
    nb_message._run_preprocessors.clear()
    nb_message._run_preprocessors.update(saved_run_pre)
    nb_message._run_postprocessors.clear()
    nb_message._run_postprocessors.update(saved_run_post)
    TrieRule.prefix.clear()
    TrieRule.prefix.update(saved_trie)


def _install_hook_and_fence() -> None:
    nb_message.event_preprocessor(message_scrub_global_hook)
    nb_message.run_preprocessor(scrub_command_target_fence)


def _register_target_with_cd(handler_calls: list[int]):
    from pallas.api.commands import bind_alias_handlers, group_command

    cmd = group_command("blacklist.scrub_add", "添加屏蔽词", cd_sec=3, priority=5, block=True)

    async def handler(_ctx) -> None:  # noqa: ANN001
        handler_calls.append(1)

    bind_alias_handlers(cmd, handler)
    return cmd


def _register_catchall(handler_calls: list[int]):
    matcher = nonebot.on_message(priority=1, block=False)

    @matcher.handle()
    async def _catchall() -> None:
        handler_calls.append(1)

    return matcher


# ---------------------------------------------------------------------------
# stock path（PALLAS_MATCHER_DISPATCH_ENABLED=false，框架原生 handle_event）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_path_authorized_command_runs_target_only(
    monkeypatch: pytest.MonkeyPatch, framework_state: None
) -> None:
    target_calls: list[int] = []
    catchall_calls: list[int] = []
    _register_target_with_cd(target_calls)
    _register_catchall(catchall_calls)
    _install_hook_and_fence()
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.refresh_command_cooldown", AsyncMock())

    await nb_message.handle_event(_make_bot(), _group_event("/添加屏蔽词 secret"))

    assert target_calls == [1]
    assert catchall_calls == []


@pytest.mark.asyncio
async def test_stock_path_disabled_target_has_no_fallback(
    monkeypatch: pytest.MonkeyPatch, framework_state: None
) -> None:
    catchall_calls: list[int] = []
    _register_catchall(catchall_calls)  # 无目标 matcher（模拟插件禁用）
    _install_hook_and_fence()
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))

    await nb_message.handle_event(_make_bot(), _group_event("/添加屏蔽词 secret"))

    assert catchall_calls == []


@pytest.mark.asyncio
async def test_stock_path_cd_failure_has_no_fallback(monkeypatch: pytest.MonkeyPatch, framework_state: None) -> None:
    target_calls: list[int] = []
    catchall_calls: list[int] = []
    _register_target_with_cd(target_calls)
    _register_catchall(catchall_calls)
    _install_hook_and_fence()
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.get_command_cooldown_sec", lambda *_a, **_k: 3)
    monkeypatch.setattr("pallas.core.commands.matcher.is_command_cooldown_ready", AsyncMock(return_value=False))

    await nb_message.handle_event(_make_bot(), _group_event("/添加屏蔽词 secret"))

    assert target_calls == []
    assert catchall_calls == []


@pytest.mark.asyncio
async def test_stock_path_permission_revoked_has_no_fallback(
    monkeypatch: pytest.MonkeyPatch, framework_state: None
) -> None:
    target_calls: list[int] = []
    catchall_calls: list[int] = []
    _register_target_with_cd(target_calls)
    _register_catchall(catchall_calls)
    _install_hook_and_fence()
    # hook 授权（True）→ 标记；随后 matcher 完整 permission 撤销（False）
    monkeypatch.setattr(
        "pallas.core.perm.check.satisfies_command_permission",
        AsyncMock(side_effect=[True, False]),
    )

    await nb_message.handle_event(_make_bot(), _group_event("/添加屏蔽词 secret"))

    assert target_calls == []
    assert catchall_calls == []


@pytest.mark.asyncio
async def test_stock_path_real_remove_command_executes(monkeypatch: pytest.MonkeyPatch, framework_state: None) -> None:
    catchall_calls: list[int] = []
    _register_catchall(catchall_calls)
    nb_matcher.matchers[5] = [*nb_matcher.matchers.get(5, []), scrub_commands.remove_scrub_cmd.matcher]
    _install_hook_and_fence()
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.refresh_command_cooldown", AsyncMock())

    row = SimpleNamespace(group_id=1, message_scrub_extra=["A", "B"])
    saved: dict = {}

    class _Repo:
        async def get(self, gid, *, ignore_cache: bool = False):  # noqa: ARG002
            return row

        async def upsert_field(self, gid, field, value):  # noqa: ARG002
            saved[field] = list(value)
            setattr(row, field, list(value))

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())
    group_extra.apply_group_scrub_extra_local(1, ["A", "B"])
    bot = _make_bot()

    await nb_message.handle_event(bot, _group_event("/删除屏蔽词 a"))

    assert saved["message_scrub_extra"] == ["B"]
    assert group_extra.group_scrub_extra_hits(group_id=1, plain_text="a", raw_message="") is False
    assert catchall_calls == []
    bot.call_api.assert_awaited()  # 真实 handler 通过框架 finish/send 回执


# ---------------------------------------------------------------------------
# patched path（PALLAS_MATCHER_DISPATCH_ENABLED=true，patched handle_event）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patched_path_authorized_command_runs_target_only(
    monkeypatch: pytest.MonkeyPatch, framework_state: None
) -> None:
    from pallas.core.platform.ingress import matcher_dispatch as md
    from pallas.core.platform.ingress import message_recorder as mr

    target_calls: list[int] = []
    catchall_calls: list[int] = []
    _register_target_with_cd(target_calls)
    _register_catchall(catchall_calls)
    _install_hook_and_fence()
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.refresh_command_cooldown", AsyncMock())
    monkeypatch.setattr(md, "conversation_scheduler_enabled", lambda: False)
    monkeypatch.setattr(md, "matcher_dispatch_enabled", lambda: True)
    monkeypatch.setattr(mr, "make_message_repository", lambda: SimpleNamespace(bulk_insert=AsyncMock()))
    mr._recorder = None

    md.install_matcher_dispatch()
    assert md.matcher_dispatch_installed() is True

    await nb_message.handle_event(_make_bot(), _group_event("/添加屏蔽词 secret"))

    assert target_calls == [1]
    assert catchall_calls == []
