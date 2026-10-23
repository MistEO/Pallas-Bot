"""私聊 Bot 级屏蔽词命令：真实 NoneBot 事件 → matcher 执行（框架 DI）。

覆盖 stock / patched 路径下私聊命令精确只跑目标 matcher、群私同名不串、
缺插件 / CD 失败 / 权限二次撤销无 fallback，且群/全局屏蔽词命令仍可解除。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import nonebot
import pytest
from nonebot import matcher as nb_matcher
from nonebot import message as nb_message
from nonebot.adapters.onebot.v11 import Message, PrivateMessageEvent
from nonebot.rule import TrieRule

import packages.blacklist.scrub_commands  # noqa: F401  注册真实命令前缀 / matcher
from packages.blacklist.scrub_commands import (
    add_scrub_cmd,
    bot_add_scrub_cmd,
    bot_list_scrub_cmd,
    list_scrub_cmd,
)
from pallas.core.platform.ingress.gate import message_scrub_global_hook
from pallas.core.platform.ingress.scrub_command_fence import scrub_command_target_fence
from pallas.product.message_scrub import group_extra, reload_message_scrub_caches


def _make_bot():
    from nonebot import get_driver
    from nonebot.adapters.onebot.v11 import Adapter, Bot

    bot = Bot(Adapter(get_driver()), self_id="100")
    bot.call_api = AsyncMock(return_value={"message_id": 1})  # type: ignore[method-assign]
    return bot


def _private_event(text: str, *, user_id: int = 7) -> PrivateMessageEvent:
    return PrivateMessageEvent(
        time=1,
        self_id=100,
        post_type="message",
        message_type="private",
        sub_type="friend",
        message_id=1,
        user_id=user_id,
        message=Message(text),
        raw_message=text,
        font=0,
        sender={"user_id": user_id},
    )


def _group_event(text: str, *, group_id: int = 1, user_id: int = 7):
    from nonebot.adapters.onebot.v11 import GroupMessageEvent

    return GroupMessageEvent(
        time=1,
        self_id=100,
        post_type="message",
        message_type="group",
        sub_type="normal",
        message_id=1,
        user_id=user_id,
        message=Message(text),
        raw_message=text,
        font=0,
        sender={"user_id": user_id, "nickname": "a", "card": "", "role": "member"},
        group_id=group_id,
    )


@pytest.fixture
def framework_state(monkeypatch: pytest.MonkeyPatch):
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
    group_extra.reset_bot_scrub_snapshot()
    yield
    group_extra.reset_group_scrub_snapshot()
    group_extra.reset_bot_scrub_snapshot()
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


def _register_catchall(handler_calls: list[int]):
    matcher = nonebot.on_message(priority=1, block=False)

    @matcher.handle()
    async def _catchall() -> None:
        handler_calls.append(1)

    return matcher


def _install_bot_repo(monkeypatch: pytest.MonkeyPatch, row) -> dict:
    saved: dict = {}

    class _Repo:
        async def get(self, account, *, ignore_cache: bool = False):  # noqa: ARG002
            return row

        async def upsert_field(self, account, field, value):  # noqa: ARG002
            saved[field] = list(value)
            setattr(row, field, list(value))

    monkeypatch.setattr("pallas.core.foundation.db.make_bot_config_repository", lambda: _Repo())
    return saved


def _install_group_repo_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Repo:
        async def get(self, gid, *, ignore_cache: bool = False):  # noqa: ARG002
            raise AssertionError("group repo must not be touched for a private command")

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())


def _authorize(monkeypatch: pytest.MonkeyPatch, *, owner: bool = True, perm=True) -> None:
    monkeypatch.setattr("pallas.core.foundation.config.user_is_bot_admin", AsyncMock(return_value=owner))
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=perm))
    monkeypatch.setattr("pallas.core.commands.matcher.is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.refresh_command_cooldown", AsyncMock())


def _register_real_scrub_matchers(*commands) -> None:  # noqa: ANN002
    """framework_state 清空了全局 matchers，这里按需重挂真实目标 matcher。"""
    nb_matcher.matchers[5] = [*nb_matcher.matchers.get(5, []), *(cmd.matcher for cmd in commands)]


# ---------------------------------------------------------------------------
# stock path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stock_private_add_runs_target_only(monkeypatch: pytest.MonkeyPatch, framework_state: None) -> None:
    catchall_calls: list[int] = []
    _register_catchall(catchall_calls)
    _register_real_scrub_matchers(bot_add_scrub_cmd)
    row = SimpleNamespace(account=100, message_scrub_extra=[])
    saved = _install_bot_repo(monkeypatch, row)
    _install_group_repo_guard(monkeypatch)
    _install_hook_and_fence()
    _authorize(monkeypatch)
    bot = _make_bot()

    await nb_message.handle_event(bot, _private_event("/添加屏蔽词 secret"))

    assert saved["message_scrub_extra"] == ["secret"]
    assert group_extra.bot_scrub_extra_hits(bot_id=100, plain_text="secret", raw_message="")
    assert catchall_calls == []
    bot.call_api.assert_awaited()


@pytest.mark.asyncio
async def test_stock_private_command_does_not_cross_to_group(
    monkeypatch: pytest.MonkeyPatch, framework_state: None
) -> None:
    catchall_calls: list[int] = []
    _register_catchall(catchall_calls)
    _register_real_scrub_matchers(list_scrub_cmd, bot_list_scrub_cmd)
    row = SimpleNamespace(account=100, message_scrub_extra=[])
    _install_bot_repo(monkeypatch, row)
    _install_group_repo_guard(monkeypatch)  # 若串到群命令会抛错
    _install_hook_and_fence()
    _authorize(monkeypatch)

    await nb_message.handle_event(_make_bot(), _private_event("/查看屏蔽词"))

    assert catchall_calls == []


@pytest.mark.asyncio
async def test_stock_group_command_still_runs_group_handler(
    monkeypatch: pytest.MonkeyPatch, framework_state: None
) -> None:
    catchall_calls: list[int] = []
    _register_catchall(catchall_calls)
    _register_real_scrub_matchers(add_scrub_cmd, bot_add_scrub_cmd)
    group_row = SimpleNamespace(group_id=1, message_scrub_extra=[])
    saved: dict = {}

    class _GroupRepo:
        async def get(self, gid, *, ignore_cache: bool = False):  # noqa: ARG002
            return group_row

        async def upsert_field(self, gid, field, value):  # noqa: ARG002
            saved[field] = list(value)
            setattr(group_row, field, list(value))

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _GroupRepo())
    monkeypatch.setattr(
        "pallas.core.foundation.db.make_bot_config_repository",
        lambda: (_ for _ in ()).throw(AssertionError("bot repo must not be touched for a group command")),
    )
    _install_hook_and_fence()
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.refresh_command_cooldown", AsyncMock())

    await nb_message.handle_event(_make_bot(), _group_event("/添加屏蔽词 secret"))

    assert saved["message_scrub_extra"] == ["secret"]
    assert catchall_calls == []


@pytest.mark.asyncio
async def test_stock_missing_plugin_has_no_fallback(monkeypatch: pytest.MonkeyPatch, framework_state: None) -> None:
    catchall_calls: list[int] = []
    _register_catchall(catchall_calls)  # 无目标 matcher（模拟插件缺失）
    _install_hook_and_fence()
    _authorize(monkeypatch)

    await nb_message.handle_event(_make_bot(), _private_event("/添加屏蔽词 secret"))

    assert catchall_calls == []


@pytest.mark.asyncio
async def test_stock_cd_failure_has_no_fallback(monkeypatch: pytest.MonkeyPatch, framework_state: None) -> None:
    catchall_calls: list[int] = []
    _register_catchall(catchall_calls)
    _register_real_scrub_matchers(bot_add_scrub_cmd)
    row = SimpleNamespace(account=100, message_scrub_extra=[])
    saved = _install_bot_repo(monkeypatch, row)
    _install_hook_and_fence()
    _authorize(monkeypatch)
    monkeypatch.setattr("pallas.core.commands.matcher.get_command_cooldown_sec", lambda *_a, **_k: 3)
    monkeypatch.setattr("pallas.core.commands.matcher.is_command_cooldown_ready", AsyncMock(return_value=False))

    await nb_message.handle_event(_make_bot(), _private_event("/添加屏蔽词 secret"))

    assert saved == {}
    assert catchall_calls == []


@pytest.mark.asyncio
async def test_stock_permission_revoked_has_no_fallback(
    monkeypatch: pytest.MonkeyPatch, framework_state: None
) -> None:
    catchall_calls: list[int] = []
    _register_catchall(catchall_calls)
    _register_real_scrub_matchers(bot_add_scrub_cmd)
    row = SimpleNamespace(account=100, message_scrub_extra=[])
    saved = _install_bot_repo(monkeypatch, row)
    _install_hook_and_fence()
    monkeypatch.setattr("pallas.core.foundation.config.user_is_bot_admin", AsyncMock(return_value=True))
    # hook 授权（首次 True）→ 标记；随后 matcher 复核全部 False
    monkeypatch.setattr(
        "pallas.core.perm.check.satisfies_command_permission",
        AsyncMock(side_effect=[True, False, False, False]),
    )
    monkeypatch.setattr("pallas.core.commands.matcher.is_command_cooldown_ready", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.commands.matcher.refresh_command_cooldown", AsyncMock())

    await nb_message.handle_event(_make_bot(), _private_event("/添加屏蔽词 secret"))

    assert saved == {}
    assert catchall_calls == []


# ---------------------------------------------------------------------------
# patched path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patched_private_add_runs_target_only(monkeypatch: pytest.MonkeyPatch, framework_state: None) -> None:
    from pallas.core.platform.ingress import matcher_dispatch as md
    from pallas.core.platform.ingress import message_recorder as mr

    catchall_calls: list[int] = []
    _register_catchall(catchall_calls)
    _register_real_scrub_matchers(bot_add_scrub_cmd)
    row = SimpleNamespace(account=100, message_scrub_extra=[])
    saved = _install_bot_repo(monkeypatch, row)
    _install_hook_and_fence()
    _authorize(monkeypatch)
    monkeypatch.setattr(md, "conversation_scheduler_enabled", lambda: False)
    monkeypatch.setattr(md, "matcher_dispatch_enabled", lambda: True)
    monkeypatch.setattr(mr, "make_message_repository", lambda: SimpleNamespace(bulk_insert=AsyncMock()))
    mr._recorder = None

    md.install_matcher_dispatch()
    assert md.matcher_dispatch_installed() is True

    await nb_message.handle_event(_make_bot(), _private_event("/添加屏蔽词 secret"))

    assert saved["message_scrub_extra"] == ["secret"]
    assert catchall_calls == []
