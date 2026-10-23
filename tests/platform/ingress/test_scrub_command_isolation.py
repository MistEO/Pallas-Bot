"""群屏蔽词命令的免审识别与 matcher 隔离。"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment, PrivateMessageEvent

from pallas.product.message_scrub import group_extra, reload_message_scrub_caches
from pallas.product.message_scrub.scrub_command import (
    clear_scrub_command_marker,
    mark_scrub_command,
    marked_scrub_command_id,
    match_scrub_command,
)


def _group_event(
    text: str, *, group_id: int = 1, self_id: int = 100, message: Message | None = None
) -> GroupMessageEvent:
    raw = message if message is not None else Message(text)
    return GroupMessageEvent(
        time=1,
        self_id=self_id,
        post_type="message",
        message_type="group",
        sub_type="normal",
        message_id=1,
        user_id=7,
        message=raw,
        raw_message=str(raw),
        font=0,
        sender={"user_id": 7, "nickname": "a", "card": "", "role": "member"},
        group_id=group_id,
    )


def _private_event(text: str, *, self_id: int = 100, sub_type: str = "friend") -> PrivateMessageEvent:
    return PrivateMessageEvent(
        time=1,
        self_id=self_id,
        post_type="message",
        message_type="private",
        sub_type=sub_type,
        message_id=1,
        user_id=7,
        message=Message(text),
        raw_message=text,
        font=0,
        sender={"user_id": 7},
    )


@pytest.fixture
def scrub_env(monkeypatch: pytest.MonkeyPatch):
    keys = ["PALLAS_MESSAGE_SCRUB_ENABLED", "PALLAS_INBOUND_FILTER_SUBSTRINGS"]
    saved = {k: os.environ.pop(k, None) for k in keys}
    reload_message_scrub_caches()
    group_extra.reset_group_scrub_snapshot()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    reload_message_scrub_caches()
    group_extra.reset_group_scrub_snapshot()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _bot() -> SimpleNamespace:
    return SimpleNamespace(self_id="100", type="onebot.v11")


def test_parser_matches_valid_commands() -> None:
    import packages.blacklist.scrub_commands  # noqa: F401  注册 TrieRule 前缀

    add = match_scrub_command(_bot(), _group_event("/添加屏蔽词 广告 推广"))
    assert add is not None
    assert add.command_id == "blacklist.scrub_add"
    assert add.word == "广告 推广"

    remove = match_scrub_command(_bot(), _group_event("/删除屏蔽词 广告"))
    assert remove is not None
    assert remove.command_id == "blacklist.scrub_remove"
    assert remove.word == "广告"

    lst = match_scrub_command(_bot(), _group_event("/查看屏蔽词"))
    assert lst is not None
    assert lst.action == "list"
    assert lst.page == 1

    lst2 = match_scrub_command(_bot(), _group_event("/查看屏蔽词 3"))
    assert lst2 is not None
    assert lst2.page == 3


def test_parser_rejects_non_command_forms() -> None:
    import packages.blacklist.scrub_commands  # noqa: F401

    # 无 command_start（测试默认 command_start 为 '/'）
    assert match_scrub_command(_bot(), _group_event("添加屏蔽词 广告")) is None
    # 紧贴参数
    assert match_scrub_command(_bot(), _group_event("/添加屏蔽词广告")) is None
    assert match_scrub_command(_bot(), _group_event("/查看屏蔽词2")) is None
    # 伪前缀（命令后紧贴字符，非空白分隔）
    assert match_scrub_command(_bot(), _group_event("/添加屏蔽词条 广告")) is None
    # 空参数
    assert match_scrub_command(_bot(), _group_event("/添加屏蔽词")) is None
    # 超长词
    assert match_scrub_command(_bot(), _group_event("/添加屏蔽词 " + "x" * 65)) is None
    # 非法页码
    assert match_scrub_command(_bot(), _group_event("/查看屏蔽词 abc")) is None
    assert match_scrub_command(_bot(), _group_event("/查看屏蔽词 0")) is None
    # 非目标命令
    assert match_scrub_command(_bot(), _group_event("/牛牛黑名单")) is None


def test_parser_rejects_mixed_cq_and_at_reply() -> None:
    import packages.blacklist.scrub_commands  # noqa: F401

    at_msg = Message([MessageSegment.at(100), MessageSegment.text(" /添加屏蔽词 x")])
    event = _group_event("", message=at_msg)
    assert match_scrub_command(_bot(), event) is None

    image_msg = Message([MessageSegment.text("/添加屏蔽词 x"), MessageSegment.image("https://x/y.png")])
    event2 = _group_event("", message=image_msg)
    assert match_scrub_command(_bot(), event2) is None


def test_parser_maps_private_to_bot_command_ids() -> None:
    import packages.blacklist.scrub_commands  # noqa: F401

    add = match_scrub_command(_bot(), _private_event("/添加屏蔽词 广告"))
    assert add is not None
    assert add.command_id == "blacklist.bot_scrub_add"
    assert add.word == "广告"

    remove = match_scrub_command(_bot(), _private_event("/删除屏蔽词 广告"))
    assert remove is not None
    assert remove.command_id == "blacklist.bot_scrub_remove"

    lst = match_scrub_command(_bot(), _private_event("/查看屏蔽词 2"))
    assert lst is not None
    assert lst.command_id == "blacklist.bot_scrub_list"
    assert lst.page == 2

    # 私聊不因同命令字串成群命令 ID
    assert match_scrub_command(_bot(), _private_event("/添加屏蔽词 x")).command_id != "blacklist.scrub_add"

    # sub_type=other 也可管理
    other = match_scrub_command(_bot(), _private_event("/添加屏蔽词 广告", sub_type="other"))
    assert other is not None
    assert other.command_id == "blacklist.bot_scrub_add"


def test_matcher_scrub_command_id_from_rule() -> None:
    import packages.blacklist.scrub_commands as sc
    from pallas.product.message_scrub.scrub_command import matcher_scrub_command_id

    assert matcher_scrub_command_id(sc.add_scrub_cmd.matcher) == "blacklist.scrub_add"
    assert matcher_scrub_command_id(sc.remove_scrub_cmd.matcher) == "blacklist.scrub_remove"
    assert matcher_scrub_command_id(sc.list_scrub_cmd.matcher) == "blacklist.scrub_list"


def test_matcher_scrub_command_id_private_bot_commands() -> None:
    import packages.blacklist.scrub_commands as sc
    from pallas.product.message_scrub.scrub_command import matcher_scrub_command_id

    assert matcher_scrub_command_id(sc.bot_add_scrub_cmd.matcher) == "blacklist.bot_scrub_add"
    assert matcher_scrub_command_id(sc.bot_remove_scrub_cmd.matcher) == "blacklist.bot_scrub_remove"
    assert matcher_scrub_command_id(sc.bot_list_scrub_cmd.matcher) == "blacklist.bot_scrub_list"


def test_matcher_scrub_command_id_rejects_bad_fixed_target() -> None:
    import packages.blacklist.scrub_commands as sc
    from pallas.product.message_scrub.scrub_command import (
        mark_matcher_scrub_target,
        matcher_scrub_command_id,
    )

    class _Fake:
        pass

    fake = _Fake()
    fake.rule = sc.add_scrub_cmd.matcher.rule
    mark_matcher_scrub_target(fake, "blacklist.not_a_bot_command")
    # 固定属性非法时返回 None，不回退成群命令。
    assert matcher_scrub_command_id(fake) is None


# ---------------------------------------------------------------------------
# Global hook：标记 / 放行 / 回退 scrub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hook_marks_authorized_command(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    import packages.blacklist.scrub_commands  # noqa: F401
    from pallas.core.platform.ingress import gate

    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_sync", lambda **k: True)

    event = _group_event("/添加屏蔽词 secret")
    await gate.message_scrub_global_hook(_bot(), event)
    assert marked_scrub_command_id(event) == "blacklist.scrub_add"


@pytest.mark.asyncio
async def test_hook_scrubs_unauthorized_command(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from nonebot.exception import IgnoredException

    import packages.blacklist.scrub_commands  # noqa: F401
    from pallas.core.platform.ingress import gate

    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=False))
    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_sync", lambda **k: True)

    event = _group_event("/添加屏蔽词 secret")
    with pytest.raises(IgnoredException):
        await gate.message_scrub_global_hook(_bot(), event)
    assert marked_scrub_command_id(event) is None


@pytest.mark.asyncio
async def test_hook_does_not_mark_private(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from nonebot.exception import IgnoredException

    import packages.blacklist.scrub_commands  # noqa: F401
    from pallas.core.platform.ingress import gate

    # 私聊同命令字存在，但非当前 Bot 号主：不得标记，按 scrub 拦截。
    monkeypatch.setattr("pallas.core.foundation.config.user_is_bot_admin", AsyncMock(return_value=False))
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_sync", lambda **k: True)

    event = _private_event("/添加屏蔽词 secret")
    with pytest.raises(IgnoredException):
        await gate.message_scrub_global_hook(_bot(), event)
    assert marked_scrub_command_id(event) is None


@pytest.mark.asyncio
async def test_hook_marks_authorized_private_bot_command(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    import packages.blacklist.scrub_commands  # noqa: F401
    from pallas.core.platform.ingress import gate

    monkeypatch.setattr("pallas.core.foundation.config.user_is_bot_admin", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_sync", lambda **k: True)

    event = _private_event("/添加屏蔽词 secret")
    await gate.message_scrub_global_hook(_bot(), event)
    assert marked_scrub_command_id(event) == "blacklist.bot_scrub_add"


@pytest.mark.asyncio
async def test_hook_marks_when_global_off(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    import packages.blacklist.scrub_commands  # noqa: F401
    from pallas.core.platform.ingress import gate

    monkeypatch.setenv("PALLAS_MESSAGE_SCRUB_ENABLED", "false")
    reload_message_scrub_caches()
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))

    event = _group_event("/查看屏蔽词")
    await gate.message_scrub_global_hook(_bot(), event)
    assert marked_scrub_command_id(event) == "blacklist.scrub_list"


@pytest.mark.asyncio
async def test_hook_resets_stale_marker(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from pallas.core.platform.ingress import gate

    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_sync", lambda **k: False)

    event = _group_event("普通消息")
    mark_scrub_command(event, "blacklist.scrub_add")
    await gate.message_scrub_global_hook(_bot(), event)
    assert marked_scrub_command_id(event) is None


# ---------------------------------------------------------------------------
# 围栏
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fence_blocks_non_target_and_allows_target() -> None:
    from nonebot.exception import IgnoredException

    import packages.blacklist.scrub_commands as sc
    from pallas.core.platform.ingress.scrub_command_fence import scrub_command_target_fence

    event = _group_event("/添加屏蔽词 x")
    mark_scrub_command(event, "blacklist.scrub_add")

    await scrub_command_target_fence(sc.add_scrub_cmd.matcher, _bot(), event, {}, None, {})
    with pytest.raises(IgnoredException):
        await scrub_command_target_fence(sc.remove_scrub_cmd.matcher, _bot(), event, {}, None, {})

    clear_scrub_command_marker(event)
    await scrub_command_target_fence(sc.remove_scrub_cmd.matcher, _bot(), event, {}, None, {})


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


def test_recorder_skips_valid_command_but_records_normal(monkeypatch: pytest.MonkeyPatch) -> None:
    import packages.blacklist.scrub_commands  # noqa: F401
    from pallas.core.platform.ingress import message_recorder as mr

    monkeypatch.setattr(mr, "make_message_repository", lambda: SimpleNamespace(bulk_insert=AsyncMock()))
    rec = mr.MessageRecorder()

    rec.capture(_group_event("/添加屏蔽词 secret"), _bot())
    assert rec._queue.qsize() == 0

    rec.capture(_group_event("普通消息"), _bot())
    assert rec._queue.qsize() == 1


# ---------------------------------------------------------------------------
# 权限粗筛（F）
# ---------------------------------------------------------------------------


def test_prefilter_skips_member_but_not_marked_target() -> None:
    from nonebot.rule import Rule
    from nonebot.rule import command as command_rule

    import packages.blacklist.scrub_commands  # noqa: F401
    from pallas.core.perm.check import group_message_permission_for_command
    from pallas.core.platform.ingress import matcher_activation as activation

    class _Target:
        rule = Rule(command_rule("添加屏蔽词"))
        permission = group_message_permission_for_command("blacklist.scrub_add")

    member_event = _group_event("/添加屏蔽词 x")
    assert activation.matcher_permission_prefilter_should_skip(_Target, member_event) is True

    mark_scrub_command(member_event, "blacklist.scrub_add")
    assert activation.matcher_permission_prefilter_should_skip(_Target, member_event) is False


# ---------------------------------------------------------------------------
# 注册：dispatch 开关无关
# ---------------------------------------------------------------------------


def test_gate_registration_installs_fence(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.core.platform.ingress import gate
    from pallas.core.platform.ingress import scrub_command_fence as fence_mod

    monkeypatch.setattr(gate, "_GATE_REGISTERED", False)
    monkeypatch.setattr("pallas.core.platform.bot_runtime.roles.is_hub_role", lambda: False)
    monkeypatch.setattr("nonebot.message.event_preprocessor", lambda fn: fn)
    monkeypatch.setattr(
        "nonebot.get_driver", lambda: SimpleNamespace(on_startup=lambda fn: fn, on_shutdown=lambda fn: fn)
    )
    monkeypatch.setattr(fence_mod, "_INSTALLED", False)
    installed: list[object] = []
    monkeypatch.setattr(fence_mod, "run_preprocessor", lambda fn: installed.append(fn))

    gate.register_ingress_gate_runtime()

    assert fence_mod._INSTALLED is True
    assert installed == [fence_mod.scrub_command_target_fence]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("false", False), ("0", False), ("true", True), ("1", True), (None, True)],
)
def test_matcher_dispatch_enabled_switch(monkeypatch: pytest.MonkeyPatch, raw, expected) -> None:
    from pallas.core.platform.ingress import matcher_dispatch as md

    monkeypatch.setattr(md, "repo_env_raw_value", lambda _k: raw)
    assert md.matcher_dispatch_enabled() is expected


# ---------------------------------------------------------------------------
# marked 事件跳过 rage 与 direct runtime（E）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marked_event_skips_rage_and_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    import packages.blacklist.scrub_commands  # noqa: F401
    from pallas.core.platform.ingress import matcher_dispatch as md
    from pallas.core.platform.message_runtime.matcher_adapter import MatcherDispatchResult

    event = _group_event("/添加屏蔽词 secret")
    mark_scrub_command(event, "blacklist.scrub_add")
    bot = _bot()

    monkeypatch.setattr(md, "mark_activity", lambda: None)
    monkeypatch.setattr(md.nb_message, "_apply_event_preprocessors", AsyncMock(return_value=True))
    monkeypatch.setattr(md.nb_message, "_apply_event_postprocessors", AsyncMock(return_value=None))
    rage = AsyncMock(return_value=True)
    monkeypatch.setattr(md, "_apply_rage_gate", rage)
    direct = SimpleNamespace(execute_and_commit=AsyncMock())
    monkeypatch.setattr(md, "direct_runtime_for_group", lambda _gid: direct)
    monkeypatch.setattr(md, "resolve_route_for_event", lambda _e: None)
    monkeypatch.setattr(md, "event_command_traffic", lambda *a, **k: True)
    monkeypatch.setattr(
        md._matcher_adapter,
        "execute",
        AsyncMock(
            return_value=MatcherDispatchResult(
                selected_matcher_modules=(),
                acquired_matcher_modules=(),
                total_selected=0,
                total_considered=0,
                matchers_run=0,
                any_matcher_executed=False,
            )
        ),
    )

    await md.patched_handle_event_now(bot, event)

    rage.assert_not_called()
    direct.execute_and_commit.assert_not_called()
