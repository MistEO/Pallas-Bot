"""群追加屏蔽词命令：解析、存储、分页、权限与并发。"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message

from pallas.product.message_scrub import (
    group_extra,
    is_message_scrub_blocked_sync,
    reload_message_scrub_caches,
)


def _group_event(text: str, *, group_id: int = 1, user_id: int = 7, self_id: int = 100) -> GroupMessageEvent:
    return GroupMessageEvent(
        time=1,
        self_id=self_id,
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


class _Ctx:
    def __init__(
        self, *, event: GroupMessageEvent | None = None, group_id: int = 1, user_id: str = "7", self_id: int = 100
    ):
        if event is None:
            event = _group_event("", group_id=group_id, user_id=int(user_id), self_id=self_id)
        self.event = event
        self.group_id = int(event.group_id) if getattr(event, "group_id", None) is not None else None
        self.user_id = user_id
        self.bot = SimpleNamespace(self_id=self_id)
        self.replies: list[object] = []

    @property
    def plain_text(self) -> str:
        return str(self.event.get_plaintext() or "")

    async def finish(self, message: object = None, **kwargs) -> None:  # noqa: ARG002
        self.replies.append(message)


def _ctx(plain_text: str, *, group_id: int = 1) -> _Ctx:
    return _Ctx(event=_group_event(plain_text, group_id=group_id))


def _install_repo(monkeypatch: pytest.MonkeyPatch, row, *, fail_write: bool = False) -> dict:
    saved: dict = {}

    class _Repo:
        async def get(self, gid, *, ignore_cache: bool = False):  # noqa: ARG002
            return row

        async def upsert_field(self, gid, field, value):  # noqa: ARG002
            if fail_write:
                raise RuntimeError("db down")
            saved[field] = list(value)
            setattr(row, field, list(value))

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())
    return saved


def _row(words: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(group_id=1, message_scrub_extra=list(words or []))


def _text(ctx: _Ctx) -> str:
    return "\n".join(str(m) for m in ctx.replies)


# ---------------------------------------------------------------------------
# 添加
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_parses_full_tail_with_spaces(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_add

    row = _row()
    saved = _install_repo(monkeypatch, row)
    ctx = _ctx("/添加屏蔽词 广告 推广")

    await handle_scrub_add(ctx)

    assert saved["message_scrub_extra"] == ["广告 推广"]
    assert group_extra.group_scrub_extra_hits(group_id=1, plain_text="广告 推广", raw_message="")
    assert "已添加" in _text(ctx)


@pytest.mark.asyncio
async def test_add_missing_argument_rejected(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_add

    row = _row()
    saved = _install_repo(monkeypatch, row)
    ctx = _ctx("/添加屏蔽词")

    await handle_scrub_add(ctx)

    assert saved == {}
    assert "用法" in _text(ctx)


@pytest.mark.asyncio
async def test_add_overlong_word_rejected(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_add

    row = _row()
    saved = _install_repo(monkeypatch, row)
    ctx = _ctx("/添加屏蔽词 " + "x" * 65)

    await handle_scrub_add(ctx)

    assert saved == {}
    assert "用法" in _text(ctx)


@pytest.mark.asyncio
async def test_add_over_limit_rejected(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_add

    row = _row([f"w{i}" for i in range(200)])
    saved = _install_repo(monkeypatch, row)
    ctx = _ctx("/添加屏蔽词 extra")

    await handle_scrub_add(ctx)

    assert saved == {}
    assert "上限" in _text(ctx) or "最多" in _text(ctx)


@pytest.mark.asyncio
async def test_add_case_insensitive_duplicate_is_noop(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_add

    row = _row(["Word"])
    saved = _install_repo(monkeypatch, row)
    ctx = _ctx("/添加屏蔽词 word")

    await handle_scrub_add(ctx)

    assert saved == {}
    assert "已有" in _text(ctx)


@pytest.mark.asyncio
async def test_add_reply_does_not_echo_word(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_add

    row = _row()
    _install_repo(monkeypatch, row)
    ctx = _ctx("/添加屏蔽词 敏感词甲")

    await handle_scrub_add(ctx)

    assert "敏感词甲" not in _text(ctx)


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_existing_then_last_clears(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_remove

    row = _row(["A", "B"])
    saved = _install_repo(monkeypatch, row)
    group_extra.apply_group_scrub_extra_local(1, ["A", "B"])

    await handle_scrub_remove(_ctx("/删除屏蔽词 a"))
    assert saved["message_scrub_extra"] == ["B"]
    assert not group_extra.group_scrub_extra_hits(group_id=1, plain_text="a", raw_message="")
    assert group_extra.group_scrub_extra_hits(group_id=1, plain_text="b", raw_message="")

    await handle_scrub_remove(_ctx("/删除屏蔽词 b"))
    assert saved["message_scrub_extra"] == []
    assert not group_extra.group_scrub_extra_hits(group_id=1, plain_text="b", raw_message="")


@pytest.mark.asyncio
async def test_remove_missing_keeps_others(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_remove

    row = _row(["A"])
    saved = _install_repo(monkeypatch, row)
    group_extra.apply_group_scrub_extra_local(1, ["A"])
    ctx = _ctx("/删除屏蔽词 zzz")

    await handle_scrub_remove(ctx)

    assert saved == {}
    assert group_extra.group_scrub_extra_hits(group_id=1, plain_text="a", raw_message="")
    assert "没有" in _text(ctx)


# ---------------------------------------------------------------------------
# 查看
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_paginates_20_per_page(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_list

    row = _row([f"word{i:02d}" for i in range(25)])
    _install_repo(monkeypatch, row)

    page1 = _ctx("/查看屏蔽词")
    await handle_scrub_list(page1)
    assert "25" in _text(page1)
    assert "word00" in _text(page1)
    assert "word19" in _text(page1)
    assert "word20" not in _text(page1)

    page2 = _ctx("/查看屏蔽词 2")
    await handle_scrub_list(page2)
    assert "word20" in _text(page2)
    assert "word24" in _text(page2)
    assert "word00" not in _text(page2)


@pytest.mark.asyncio
async def test_list_rejects_invalid_and_out_of_range_page(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_list

    row = _row(["only"])
    _install_repo(monkeypatch, row)

    bad = _ctx("/查看屏蔽词 abc")
    await handle_scrub_list(bad)
    assert "数字" in _text(bad)

    over = _ctx("/查看屏蔽词 9")
    await handle_scrub_list(over)
    assert "范围" in _text(over) or "页" in _text(over)


@pytest.mark.asyncio
async def test_list_empty_group(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_list

    _install_repo(monkeypatch, _row())
    ctx = _ctx("/查看屏蔽词")
    await handle_scrub_list(ctx)
    assert "还没有" in _text(ctx)


@pytest.mark.asyncio
async def test_list_reply_keeps_cq_like_words_as_plain_text(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from nonebot.adapters.onebot.v11 import Message

    from packages.blacklist.scrub_commands import handle_scrub_list

    _install_repo(monkeypatch, _row(["[CQ:image,file=x]", "normal"]))
    ctx = _ctx("/查看屏蔽词")

    await handle_scrub_list(ctx)

    reply = ctx.replies[0]
    assert isinstance(reply, Message)
    assert all(segment.type == "text" for segment in reply)
    assert "&#91;CQ:image,file=x&#93;" in str(reply)


# ---------------------------------------------------------------------------
# 存储与全局开关
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_failure_does_not_patch_or_claim_success(
    monkeypatch: pytest.MonkeyPatch, scrub_env: None
) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_add

    _install_repo(monkeypatch, _row(), fail_write=True)
    ctx = _ctx("/添加屏蔽词 secret")

    await handle_scrub_add(ctx)

    assert not group_extra.group_scrub_extra_hits(group_id=1, plain_text="secret", raw_message="")
    assert "失败" in _text(ctx)
    assert "已添加" not in _text(ctx)


@pytest.mark.asyncio
async def test_global_off_still_editable_but_dormant(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_add

    monkeypatch.setenv("PALLAS_MESSAGE_SCRUB_ENABLED", "false")
    reload_message_scrub_caches()
    row = _row()
    saved = _install_repo(monkeypatch, row)

    await handle_scrub_add(_ctx("/添加屏蔽词 hidden"))

    assert saved["message_scrub_extra"] == ["hidden"]
    assert not is_message_scrub_blocked_sync(plain_text="hidden", raw_message="", group_id=1)


@pytest.mark.asyncio
async def test_concurrent_adds_keep_both_words(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import add_group_scrub_word

    row = _row()

    class _Repo:
        async def get(self, gid, *, ignore_cache: bool = False):  # noqa: ARG002
            await asyncio.sleep(0)
            return row

        async def upsert_field(self, gid, field, value):  # noqa: ARG002
            await asyncio.sleep(0)
            setattr(row, field, list(value))

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())

    await asyncio.gather(add_group_scrub_word(1, "alpha"), add_group_scrub_word(1, "beta"))

    assert set(row.message_scrub_extra) == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# 命令定义与权限
# ---------------------------------------------------------------------------


def test_scrub_command_ids_match_metadata() -> None:
    from packages.blacklist import __plugin_meta__
    from packages.blacklist.scrub_commands import add_scrub_cmd, list_scrub_cmd, remove_scrub_cmd

    ids = {add_scrub_cmd.command_id, remove_scrub_cmd.command_id, list_scrub_cmd.command_id}
    assert ids == {"blacklist.scrub_add", "blacklist.scrub_remove", "blacklist.scrub_list"}

    perms = {row["id"] for row in __plugin_meta__.extra["command_permissions"]}
    assert ids <= perms
    menu_ids = {item.get("command_permission") for item in __plugin_meta__.extra["menu_data"]}
    assert ids <= menu_ids


@pytest.mark.asyncio
async def test_scrub_matchers_reject_private_scope() -> None:
    from nonebot.adapters.onebot.v11 import Message, PrivateMessageEvent

    from packages.blacklist.scrub_commands import add_scrub_cmd, list_scrub_cmd, remove_scrub_cmd

    private = PrivateMessageEvent(
        time=1,
        self_id=1,
        post_type="message",
        message_type="private",
        sub_type="friend",
        message_id=1,
        user_id=100,
        message=Message("x"),
        raw_message="x",
        font=0,
        sender={"user_id": 100},
    )
    bot = SimpleNamespace()
    with (
        patch("pallas.core.perm.check.SUPERUSER", new_callable=AsyncMock, return_value=True),
        patch("pallas.core.perm.check.user_is_bot_admin", new_callable=AsyncMock, return_value=True),
        patch("pallas.core.perm.check.user_is_admin_of_any_bot", new_callable=AsyncMock, return_value=True),
    ):
        for cmd in (add_scrub_cmd, remove_scrub_cmd, list_scrub_cmd):
            assert await cmd.matcher.permission(bot, private) is False


def test_metadata_declares_scrub_commands() -> None:
    from packages.blacklist import __plugin_meta__

    perms = {row["id"]: row for row in __plugin_meta__.extra["command_permissions"]}
    assert perms["blacklist.scrub_add"]["default"] == "group_moderator"
    assert perms["blacklist.scrub_remove"]["default"] == "group_moderator"
    assert perms["blacklist.scrub_list"]["default"] == "group_moderator"

    menu_ids = {item.get("command_permission") for item in __plugin_meta__.extra["menu_data"]}
    assert {"blacklist.scrub_add", "blacklist.scrub_remove", "blacklist.scrub_list"} <= menu_ids

    prefixes = set(__plugin_meta__.extra.get("command_prefixes") or [])
    assert {"添加屏蔽词", "删除屏蔽词", "查看屏蔽词"} <= prefixes

    for item in __plugin_meta__.extra["menu_data"]:
        condition = str(item.get("trigger_condition") or "")
        assert "群管" not in condition
        assert "群主" not in condition
        assert "管理员" not in condition


def test_scrub_command_default_level_and_override() -> None:
    from pallas.core.perm.registry import resolved_level

    assert resolved_level("blacklist.scrub_add", {}) == "group_moderator"
    assert resolved_level("blacklist.scrub_add", {"blacklist.scrub_add": "everyone"}) == "everyone"


@pytest.mark.asyncio
async def test_scrub_command_rejects_non_moderator_and_allows_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message

    from pallas.core.perm.check import satisfies_command_permission

    def _event(role: str) -> GroupMessageEvent:
        return GroupMessageEvent(
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
            sender={"user_id": 100, "nickname": "a", "card": "", "role": role},
            group_id=1,
        )

    bot = SimpleNamespace()
    with (
        patch("pallas.core.perm.check.SUPERUSER", new_callable=AsyncMock, return_value=False),
        patch("pallas.core.perm.check.user_is_bot_admin", new_callable=AsyncMock, return_value=False),
        patch("pallas.core.perm.check.user_is_admin_of_any_bot", new_callable=AsyncMock, return_value=False),
    ):
        assert await satisfies_command_permission(bot, _event("member"), "blacklist.scrub_add") is False
        assert await satisfies_command_permission(bot, _event("admin"), "blacklist.scrub_add") is True
