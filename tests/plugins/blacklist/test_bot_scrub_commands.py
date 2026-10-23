"""私聊 Bot 级追加屏蔽词命令：权限硬条件、存储、分页、隔离与并发。"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, PrivateMessageEvent

from pallas.product.message_scrub import group_extra


def _private_event(text: str, *, self_id: int = 100, user_id: int = 7, sub_type: str = "friend") -> PrivateMessageEvent:
    return PrivateMessageEvent(
        time=1,
        self_id=self_id,
        post_type="message",
        message_type="private",
        sub_type=sub_type,
        message_id=1,
        user_id=user_id,
        message=Message(text),
        raw_message=text,
        font=0,
        sender={"user_id": user_id},
    )


def _group_temp_event(text: str, *, self_id: int = 100, user_id: int = 7, group_id: int = 0) -> PrivateMessageEvent:
    from pallas.core.shared.adapters.onebot_v11_custom_events import GroupTempPrivateMessageEvent

    return GroupTempPrivateMessageEvent(
        time=1,
        self_id=self_id,
        post_type="message",
        message_type="private",
        sub_type="group",
        message_id=1,
        user_id=user_id,
        message=Message(text),
        raw_message=text,
        font=0,
        sender={"user_id": user_id},
        group_id=group_id,
    )


class _Ctx:
    def __init__(self, event: PrivateMessageEvent, *, command_id: str = "blacklist.bot_scrub_add", self_id: int = 100):
        self.event = event
        self.command_id = command_id
        self.user_id = str(event.user_id)
        self.bot = SimpleNamespace(self_id=self_id)
        self.replies: list[object] = []

    @property
    def group_id(self) -> int | None:
        return getattr(self.event, "group_id", None) or None

    @property
    def is_private(self) -> bool:
        return True

    @property
    def plain_text(self) -> str:
        return str(self.event.get_plaintext() or "")

    async def finish(self, message: object = None, **kwargs) -> None:  # noqa: ARG002
        self.replies.append(message)


def _text(ctx: _Ctx) -> str:
    return "\n".join(str(m) for m in ctx.replies)


def _ctx(text: str, *, command_id: str = "blacklist.bot_scrub_add", sub_type: str = "friend") -> _Ctx:
    return _Ctx(_private_event(text, sub_type=sub_type), command_id=command_id)


def _install_bot_repo(monkeypatch: pytest.MonkeyPatch, row, *, fail_write: bool = False) -> dict:
    saved: dict = {}

    class _Repo:
        async def get(self, account, *, ignore_cache: bool = False):  # noqa: ARG002
            return row

        async def upsert_field(self, account, field, value):  # noqa: ARG002
            if fail_write:
                raise RuntimeError("db down")
            saved[field] = list(value)
            setattr(row, field, list(value))

    monkeypatch.setattr("pallas.core.foundation.db.make_bot_config_repository", lambda: _Repo())
    return saved


def _row(words: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(account=100, message_scrub_extra=list(words or []))


def _owner_ok(monkeypatch: pytest.MonkeyPatch, *, owner: bool = True, perm: bool = True) -> None:
    monkeypatch.setattr(
        "pallas.core.foundation.config.user_is_bot_admin", AsyncMock(return_value=owner)
    )
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=perm))


@pytest.fixture(autouse=True)
def _reset_bot_snapshot():
    group_extra.reset_bot_scrub_snapshot()
    yield
    group_extra.reset_bot_scrub_snapshot()


# ---------------------------------------------------------------------------
# 权限硬条件：仅当前 Bot 号主
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_can_add(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_add

    row = _row()
    saved = _install_bot_repo(monkeypatch, row)
    _owner_ok(monkeypatch)
    ctx = _ctx("/添加屏蔽词 广告")

    await handle_bot_scrub_add(ctx)

    assert saved["message_scrub_extra"] == ["广告"]
    assert group_extra.bot_scrub_extra_hits(bot_id=100, plain_text="广告", raw_message="")
    assert "已添加" in _text(ctx)


@pytest.mark.asyncio
async def test_non_owner_refused_even_with_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_add

    row = _row()
    saved = _install_bot_repo(monkeypatch, row)
    _owner_ok(monkeypatch, owner=False, perm=True)  # 例如 everyone / ACL allow / 其它 Bot 号主
    ctx = _ctx("/添加屏蔽词 广告")

    await handle_bot_scrub_add(ctx)

    assert saved == {}
    assert not group_extra.bot_scrub_extra_hits(bot_id=100, plain_text="广告", raw_message="")
    assert "已添加" not in _text(ctx)


@pytest.mark.asyncio
async def test_owner_but_permission_denied_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_add

    row = _row()
    saved = _install_bot_repo(monkeypatch, row)
    _owner_ok(monkeypatch, owner=True, perm=False)
    ctx = _ctx("/添加屏蔽词 广告")

    await handle_bot_scrub_add(ctx)

    assert saved == {}


@pytest.mark.asyncio
async def test_group_temp_private_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_add

    row = _row()
    saved = _install_bot_repo(monkeypatch, row)
    _owner_ok(monkeypatch)
    ctx = _Ctx(_group_temp_event("/添加屏蔽词 广告"))

    await handle_bot_scrub_add(ctx)

    assert saved == {}
    assert "已添加" not in _text(ctx)


@pytest.mark.asyncio
async def test_owner_check_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_add

    row = _row()
    saved = _install_bot_repo(monkeypatch, row)
    monkeypatch.setattr(
        "pallas.core.foundation.config.user_is_bot_admin",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    ctx = _ctx("/添加屏蔽词 广告")

    await handle_bot_scrub_add(ctx)

    assert saved == {}


# ---------------------------------------------------------------------------
# 增删查
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_case_insensitive_duplicate_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_add

    row = _row(["Word"])
    saved = _install_bot_repo(monkeypatch, row)
    _owner_ok(monkeypatch)
    ctx = _ctx("/添加屏蔽词 word")

    await handle_bot_scrub_add(ctx)

    assert saved == {}
    assert "已有" in _text(ctx)


@pytest.mark.asyncio
async def test_add_over_limit_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_add

    row = _row([f"w{i}" for i in range(200)])
    saved = _install_bot_repo(monkeypatch, row)
    _owner_ok(monkeypatch)
    ctx = _ctx("/添加屏蔽词 extra")

    await handle_bot_scrub_add(ctx)

    assert saved == {}
    assert "上限" in _text(ctx) or "最多" in _text(ctx)


@pytest.mark.asyncio
async def test_add_duplicate_at_limit_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import add_bot_scrub_word

    row = _row([f"w{i}" for i in range(200)])
    _install_bot_repo(monkeypatch, row)

    changed, total = await add_bot_scrub_word(100, "w5")
    assert changed is False
    assert total == 200


@pytest.mark.asyncio
async def test_add_new_word_at_limit_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import add_bot_scrub_word

    row = _row([f"w{i}" for i in range(200)])
    _install_bot_repo(monkeypatch, row)

    with pytest.raises(ValueError, match="最多"):
        await add_bot_scrub_word(100, "brandnew")


@pytest.mark.asyncio
async def test_remove_existing_then_last_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_remove

    row = _row(["A", "B"])
    saved = _install_bot_repo(monkeypatch, row)
    _owner_ok(monkeypatch)
    group_extra.apply_bot_scrub_extra_local(100, ["A", "B"])

    await handle_bot_scrub_remove(_ctx("/删除屏蔽词 a", command_id="blacklist.bot_scrub_remove"))
    assert saved["message_scrub_extra"] == ["B"]
    assert not group_extra.bot_scrub_extra_hits(bot_id=100, plain_text="a", raw_message="")
    assert group_extra.bot_scrub_extra_hits(bot_id=100, plain_text="b", raw_message="")

    await handle_bot_scrub_remove(_ctx("/删除屏蔽词 b", command_id="blacklist.bot_scrub_remove"))
    assert saved["message_scrub_extra"] == []
    assert not group_extra.bot_scrub_extra_hits(bot_id=100, plain_text="b", raw_message="")


@pytest.mark.asyncio
async def test_list_paginates_20_per_page(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_list

    row = _row([f"word{i:02d}" for i in range(25)])
    _install_bot_repo(monkeypatch, row)
    _owner_ok(monkeypatch)

    page1 = _ctx("/查看屏蔽词", command_id="blacklist.bot_scrub_list")
    await handle_bot_scrub_list(page1)
    assert "25" in _text(page1)
    assert "word00" in _text(page1)
    assert "word20" not in _text(page1)

    page2 = _ctx("/查看屏蔽词 2", command_id="blacklist.bot_scrub_list")
    await handle_bot_scrub_list(page2)
    assert "word20" in _text(page2)
    assert "word00" not in _text(page2)


@pytest.mark.asyncio
async def test_list_empty_and_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_list

    _install_bot_repo(monkeypatch, _row())
    _owner_ok(monkeypatch)

    empty = _ctx("/查看屏蔽词", command_id="blacklist.bot_scrub_list")
    await handle_bot_scrub_list(empty)
    assert "还没有" in _text(empty)


@pytest.mark.asyncio
async def test_list_reply_plain_text_keeps_cq_like_words(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_list

    _install_bot_repo(monkeypatch, _row(["[CQ:image,file=x]", "normal"]))
    _owner_ok(monkeypatch)
    ctx = _ctx("/查看屏蔽词", command_id="blacklist.bot_scrub_list")

    await handle_bot_scrub_list(ctx)

    reply = ctx.replies[0]
    assert isinstance(reply, Message)
    assert all(segment.type == "text" for segment in reply)


@pytest.mark.asyncio
async def test_global_off_still_editable_but_dormant(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_add
    from pallas.product.message_scrub import is_message_scrub_blocked_sync, reload_message_scrub_caches

    monkeypatch.setenv("PALLAS_MESSAGE_SCRUB_ENABLED", "false")
    reload_message_scrub_caches()
    try:
        row = _row()
        saved = _install_bot_repo(monkeypatch, row)
        _owner_ok(monkeypatch)

        await handle_bot_scrub_add(_ctx("/添加屏蔽词 hidden"))

        assert saved["message_scrub_extra"] == ["hidden"]
        assert not is_message_scrub_blocked_sync(plain_text="hidden", raw_message="", group_id=1, bot_id=100)
    finally:
        os.environ.pop("PALLAS_MESSAGE_SCRUB_ENABLED", None)
        reload_message_scrub_caches()


# ---------------------------------------------------------------------------
# 失败与并发
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_failure_does_not_patch_or_claim_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import handle_bot_scrub_add

    _install_bot_repo(monkeypatch, _row(), fail_write=True)
    _owner_ok(monkeypatch)
    ctx = _ctx("/添加屏蔽词 secret")

    await handle_bot_scrub_add(ctx)

    assert not group_extra.bot_scrub_extra_hits(bot_id=100, plain_text="secret", raw_message="")
    assert "失败" in _text(ctx)
    assert "已添加" not in _text(ctx)


@pytest.mark.asyncio
async def test_concurrent_adds_keep_both_words(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.blacklist.scrub_commands import add_bot_scrub_word

    row = _row()

    class _Repo:
        async def get(self, account, *, ignore_cache: bool = False):  # noqa: ARG002
            await asyncio.sleep(0)
            return row

        async def upsert_field(self, account, field, value):  # noqa: ARG002
            await asyncio.sleep(0)
            setattr(row, field, list(value))

    monkeypatch.setattr("pallas.core.foundation.db.make_bot_config_repository", lambda: _Repo())

    await asyncio.gather(add_bot_scrub_word(100, "alpha"), add_bot_scrub_word(100, "beta"))

    assert set(row.message_scrub_extra) == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# 命令定义与权限
# ---------------------------------------------------------------------------


def test_bot_command_ids_match_metadata() -> None:
    from packages.blacklist import __plugin_meta__
    from packages.blacklist.scrub_commands import bot_add_scrub_cmd, bot_list_scrub_cmd, bot_remove_scrub_cmd

    ids = {bot_add_scrub_cmd.command_id, bot_remove_scrub_cmd.command_id, bot_list_scrub_cmd.command_id}
    assert ids == {"blacklist.bot_scrub_add", "blacklist.bot_scrub_remove", "blacklist.bot_scrub_list"}

    perms = {row["id"]: row for row in __plugin_meta__.extra["command_permissions"]}
    assert ids <= set(perms)
    for cid in ids:
        assert perms[cid]["default"] == "bot_moderator"

    limits = {row["id"] for row in __plugin_meta__.extra["command_limits"]}
    assert ids <= limits

    menu_ids = {item.get("command_permission") for item in __plugin_meta__.extra["menu_data"]}
    assert ids <= menu_ids


@pytest.mark.asyncio
async def test_bot_matchers_reject_group_scope() -> None:
    from packages.blacklist.scrub_commands import bot_add_scrub_cmd, bot_list_scrub_cmd, bot_remove_scrub_cmd

    group = GroupMessageEvent(
        time=1,
        self_id=1,
        post_type="message",
        message_type="group",
        sub_type="normal",
        message_id=1,
        user_id=100,
        message=Message("x"),
        raw_message="x",
        font=0,
        sender={"user_id": 100, "nickname": "a", "card": "", "role": "member"},
        group_id=1,
    )
    bot = SimpleNamespace()
    with (
        patch("pallas.core.perm.check.SUPERUSER", new_callable=AsyncMock, return_value=True),
        patch("pallas.core.perm.check.user_is_bot_admin", new_callable=AsyncMock, return_value=True),
        patch("pallas.core.perm.check.user_is_admin_of_any_bot", new_callable=AsyncMock, return_value=True),
    ):
        for cmd in (bot_add_scrub_cmd, bot_remove_scrub_cmd, bot_list_scrub_cmd):
            assert await cmd.matcher.permission(bot, group) is False


def test_bot_menu_trigger_condition_has_no_hardcoded_roles() -> None:
    from packages.blacklist import __plugin_meta__

    for item in __plugin_meta__.extra["menu_data"]:
        condition = str(item.get("trigger_condition") or "")
        assert "群管" not in condition
        assert "群主" not in condition
        assert "管理员" not in condition
        assert "号主" not in condition
