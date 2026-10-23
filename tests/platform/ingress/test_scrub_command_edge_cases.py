"""群屏蔽词命令：边界与缺陷回归。

覆盖 parser 字面/页码安全、群临时会话私聊不误豁免、200 词边界、remove lower 等价等。
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment, PrivateMessageEvent

import packages.blacklist.scrub_commands  # noqa: F401  注册 TrieRule 前缀
from pallas.product.message_scrub import group_extra, reload_message_scrub_caches
from pallas.product.message_scrub.scrub_command import match_scrub_command


def _group_event(text: str = "", *, message: Message | None = None, group_id: int = 1) -> GroupMessageEvent:
    raw = message if message is not None else Message(text)
    return GroupMessageEvent(
        time=1,
        self_id=100,
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


class _Ctx:
    def __init__(self, event: GroupMessageEvent) -> None:
        self.event = event
        self.group_id = int(event.group_id)
        self.user_id = "7"
        self.bot = SimpleNamespace(self_id="100", type="onebot.v11")
        self.replies: list[object] = []

    @property
    def plain_text(self) -> str:
        return str(self.event.get_plaintext() or "")

    async def finish(self, message: object = None, **kwargs) -> None:  # noqa: ARG002
        self.replies.append(message)


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


def _install_repo(monkeypatch: pytest.MonkeyPatch, row) -> dict:
    saved: dict = {}

    class _Repo:
        async def get(self, gid, *, ignore_cache: bool = False):  # noqa: ARG002
            return row

        async def upsert_field(self, gid, field, value):  # noqa: ARG002
            saved[field] = list(value)
            setattr(row, field, list(value))

    monkeypatch.setattr("pallas.core.foundation.db.make_group_config_repository", lambda: _Repo())
    return saved


# ---------------------------------------------------------------------------
# 1) parser 参数应用 message.extract_plain_text 真实字面，而非 str() 转义
# ---------------------------------------------------------------------------


def test_parser_add_word_keeps_real_literal_not_escaped() -> None:
    event = _group_event("/添加屏蔽词 A&B<C>")
    match = match_scrub_command(None, event)
    assert match is not None
    assert match.word == "A&B<C>"  # 现状：'A&amp;B&lt;C&gt;'


def test_parser_add_cq_like_word_keeps_literal_brackets() -> None:
    event = _group_event(message=Message([MessageSegment.text("/添加屏蔽词 [CQ:image,file=x]")]))
    match = match_scrub_command(None, event)
    assert match is not None
    assert match.word == "[CQ:image,file=x]"


@pytest.mark.asyncio
async def test_handler_add_special_char_word_matches_immediately(
    monkeypatch: pytest.MonkeyPatch, scrub_env: None
) -> None:
    from packages.blacklist.scrub_commands import handle_scrub_add

    row = SimpleNamespace(group_id=1, message_scrub_extra=[])
    saved = _install_repo(monkeypatch, row)
    ctx = _Ctx(_group_event("/添加屏蔽词 A&B<C>"))

    await handle_scrub_add(ctx)

    assert saved["message_scrub_extra"] == ["A&B<C>"]
    assert group_extra.group_scrub_extra_hits(group_id=1, plain_text="A&B<C>", raw_message="")


# ---------------------------------------------------------------------------
# 2) 200 词时重复添加应 no-op；201st 真正新词必须拒绝
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_duplicate_at_limit_is_noop(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import add_group_scrub_word

    row = SimpleNamespace(group_id=1, message_scrub_extra=[f"w{i}" for i in range(200)])
    _install_repo(monkeypatch, row)

    changed, total = await add_group_scrub_word(1, "w5")

    assert changed is False
    assert total == 200


@pytest.mark.asyncio
async def test_add_new_word_at_limit_is_rejected(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import add_group_scrub_word

    row = SimpleNamespace(group_id=1, message_scrub_extra=[f"w{i}" for i in range(200)])
    _install_repo(monkeypatch, row)

    with pytest.raises(ValueError, match="最多"):
        await add_group_scrub_word(1, "brandnew")


# ---------------------------------------------------------------------------
# 3) remove 应按 lower 等价删除，不能用 casefold 一删两个
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_uses_lower_equivalence(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from packages.blacklist.scrub_commands import remove_group_scrub_word

    row = SimpleNamespace(group_id=1, message_scrub_extra=["straße", "strasse"])
    saved = _install_repo(monkeypatch, row)

    changed, total = await remove_group_scrub_word(1, "straße")

    assert changed is True
    assert saved["message_scrub_extra"] == ["strasse"]
    assert total == 1


# ---------------------------------------------------------------------------
# 4) 超长纯数字页码不得抛异常 / 绕过过滤（parser 位于 capture，不可冒出 ValueError）
# ---------------------------------------------------------------------------


_HUGE_PAGE = "9" * 5000


def test_parser_overlong_digit_page_returns_none() -> None:
    event = _group_event("/查看屏蔽词 " + _HUGE_PAGE)
    assert match_scrub_command(None, event) is None


def test_recorder_overlong_digit_page_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.core.platform.ingress import message_recorder as mr

    monkeypatch.setattr(mr, "make_message_repository", lambda: SimpleNamespace(bulk_insert=AsyncMock()))
    rec = mr.MessageRecorder()

    # 非法语法不是合法命令：不入「命令免记录」分支，按普通消息记录，且不得抛异常。
    rec.capture(_group_event("/查看屏蔽词 " + _HUGE_PAGE), SimpleNamespace(self_id="100", type="onebot.v11"))
    assert rec._queue.qsize() == 1


@pytest.mark.asyncio
async def test_hook_overlong_digit_page_does_not_raise(monkeypatch: pytest.MonkeyPatch, scrub_env: None) -> None:
    from pallas.core.platform.ingress import gate

    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_sync", lambda **k: False)

    event = _group_event("/查看屏蔽词 " + _HUGE_PAGE)
    await gate.message_scrub_global_hook(SimpleNamespace(self_id="100", type="onebot.v11"), event)
    assert True


# ---------------------------------------------------------------------------
# 5) 短数字 '²'：isdigit True 但 int 抛 ValueError
# ---------------------------------------------------------------------------


def test_parser_superscript_page_returns_none() -> None:
    event = _group_event("/查看屏蔽词 ²")
    assert match_scrub_command(None, event) is None


def test_recorder_superscript_page_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    from pallas.core.platform.ingress import message_recorder as mr

    monkeypatch.setattr(mr, "make_message_repository", lambda: SimpleNamespace(bulk_insert=AsyncMock()))
    rec = mr.MessageRecorder()

    rec.capture(_group_event("/查看屏蔽词 ²"), SimpleNamespace(self_id="100", type="onebot.v11"))
    assert rec._queue.qsize() == 1


# ---------------------------------------------------------------------------
# 6) 群临时会话私聊：继承 PrivateMessageEvent 但带 group_id，不得误豁免
# ---------------------------------------------------------------------------


def _group_temp_private_event(text: str, *, group_id: int = 123) -> PrivateMessageEvent:
    from pallas.core.shared.adapters.onebot_v11_custom_events import GroupTempPrivateMessageEvent

    return GroupTempPrivateMessageEvent(
        time=1,
        self_id=100,
        post_type="message",
        message_type="private",
        sub_type="group",
        message_id=1,
        user_id=7,
        message=Message(text),
        raw_message=text,
        font=0,
        sender={"user_id": 7},
        group_id=group_id,
    )


@pytest.mark.parametrize("group_id", [123, 0])
def test_parser_rejects_group_temp_private_event(group_id: int) -> None:
    event = _group_temp_private_event("/添加屏蔽词 secret", group_id=group_id)
    assert match_scrub_command(None, event) is None


@pytest.mark.asyncio
async def test_hook_does_not_mark_and_scrubs_group_temp_private(
    monkeypatch: pytest.MonkeyPatch, scrub_env: None
) -> None:
    from nonebot.exception import IgnoredException

    from pallas.core.platform.ingress import gate
    from pallas.product.message_scrub.scrub_command import marked_scrub_command_id

    monkeypatch.setattr("pallas.core.perm.check.satisfies_command_permission", AsyncMock(return_value=True))
    monkeypatch.setattr("pallas.product.message_scrub.is_message_scrub_blocked_sync", lambda **k: True)

    event = _group_temp_private_event("/添加屏蔽词 secret")
    with pytest.raises(IgnoredException):
        await gate.message_scrub_global_hook(SimpleNamespace(self_id="100", type="onebot.v11"), event)
    assert marked_scrub_command_id(event) is None
