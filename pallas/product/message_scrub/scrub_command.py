"""屏蔽词命令的固定识别，供入站免审与 matcher 隔离复用。

群事件识别三条固定命令（添加/删除/查看屏蔽词）；私聊识别同命令字的 Bot 级三条
（各自独立命令 ID）。识别以 NoneBot ``TrieRule`` 为准，与真实 matcher 注册保持一致。
"""

from __future__ import annotations

from dataclasses import dataclass

from nonebot.adapters import Bot, Event  # noqa: TC002
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.consts import CMD_KEY, CMD_WHITESPACE_KEY, RAW_CMD_KEY
from nonebot.rule import TrieRule

from pallas.product.message_scrub.group_extra import MAX_GROUP_SCRUB_EXTRA_WORD_LEN

ADD_COMMAND = "添加屏蔽词"
REMOVE_COMMAND = "删除屏蔽词"
LIST_COMMAND = "查看屏蔽词"

SCRUB_COMMAND_IDS: dict[str, str] = {
    ADD_COMMAND: "blacklist.scrub_add",
    REMOVE_COMMAND: "blacklist.scrub_remove",
    LIST_COMMAND: "blacklist.scrub_list",
}

BOT_SCRUB_COMMAND_IDS: dict[str, str] = {
    ADD_COMMAND: "blacklist.bot_scrub_add",
    REMOVE_COMMAND: "blacklist.bot_scrub_remove",
    LIST_COMMAND: "blacklist.bot_scrub_list",
}

_BOT_SCRUB_WORD_BY_ID: dict[str, str] = {cid: word for word, cid in BOT_SCRUB_COMMAND_IDS.items()}

# 私聊 Bot 级命令管理允许的私聊子类型；群临时会话（sub_type=group）一律拒绝。
_PRIVATE_MANAGE_SUBTYPES = frozenset({"friend", "other"})

_MARKER_ATTR = "_pallas_scrub_command_id"
_FIXED_TARGET_ATTR = "_pallas_scrub_fixed_command_id"


@dataclass(frozen=True)
class ScrubCommand:
    command_id: str
    action: str
    word: str = ""
    page: int = 1


def mark_scrub_command(event: object, command_id: str) -> None:
    setattr(event, _MARKER_ATTR, command_id)


def clear_scrub_command_marker(event: object) -> None:
    if hasattr(event, _MARKER_ATTR):
        try:
            delattr(event, _MARKER_ATTR)
        except AttributeError:
            setattr(event, _MARKER_ATTR, None)


def marked_scrub_command_id(event: object) -> str | None:
    value = getattr(event, _MARKER_ATTR, None)
    return str(value) if value else None


def mark_matcher_scrub_target(matcher: object, command_id: str) -> None:
    """给私聊 Bot 级命令 matcher 固定目标 ID，避免与群同命令字混淆。"""
    setattr(matcher, _FIXED_TARGET_ATTR, command_id)


def is_bot_scrub_command_id(command_id: str | None) -> bool:
    return bool(command_id) and command_id in _BOT_SCRUB_WORD_BY_ID


def _all_text_message(event: object) -> bool:
    """``original_message`` 与当前 ``message`` 必须全为文本段。

    适配器去掉 @/回复后当前 message 可能变纯文本，但 original_message 仍含 CQ 段，
    此时不得豁免。
    """
    seen = False
    for attr in ("original_message", "message"):
        message = getattr(event, attr, None)
        if message is None:
            continue
        try:
            segments = list(message)
        except TypeError:
            return False
        if not segments:
            return False
        seen = True
        for segment in segments:
            if not segment.is_text():
                return False
    return seen


def manageable_private_event(event: object) -> bool:
    """普通私聊（friend / other）可管理 Bot 级词；群临时会话（sub_type=group）拒绝。"""
    if isinstance(event, GroupMessageEvent):
        return False
    if not isinstance(event, PrivateMessageEvent):
        return False
    return str(getattr(event, "sub_type", "")) in _PRIVATE_MANAGE_SUBTYPES


def _event_scene(event: object) -> str | None:
    if isinstance(event, GroupMessageEvent):
        return "group"
    if manageable_private_event(event):
        return "private"
    return None


MAX_PAGE_DIGITS = 10


def _extract_command_arg(event: object, prefix: dict) -> tuple[str, bool]:
    """从事件真实明文取命令后参数（保留 &、[CQ:...] 等字面），返回 (arg, has_whitespace)。"""
    raw_command = prefix.get(RAW_CMD_KEY)
    if not raw_command:
        return "", False
    plain = str(event.get_message().extract_plain_text() or "").lstrip()
    if not plain.startswith(raw_command):
        return "", False
    arg = plain[len(raw_command) :].strip()
    return arg, bool(prefix.get(CMD_WHITESPACE_KEY))


def match_scrub_command(bot: object, event: object) -> ScrubCommand | None:
    """严格语法时返回匹配；任何不满足（含紧贴参数、伪前缀、混合 CQ）返回 None。

    群事件映射群三条命令 ID，普通私聊映射 Bot 级三条命令 ID。
    """
    scene = _event_scene(event)
    if scene is None:
        return None
    if not _all_text_message(event):
        return None
    try:
        prefix = TrieRule.get_value(bot, event, {})
    except Exception:  # noqa: BLE001
        return None
    command = prefix.get(CMD_KEY)
    if not command or len(command) != 1:
        return None
    command_word = command[0]
    command_ids = SCRUB_COMMAND_IDS if scene == "group" else BOT_SCRUB_COMMAND_IDS
    command_id = command_ids.get(command_word)
    if command_id is None:
        return None

    arg, has_whitespace = _extract_command_arg(event, prefix)

    if command_word == LIST_COMMAND:
        if not arg:
            return ScrubCommand(command_id=command_id, action="list", page=1)
        if not has_whitespace or len(arg) > MAX_PAGE_DIGITS or not arg.isdecimal():
            return None
        try:
            page = int(arg)
        except ValueError:
            return None
        if page < 1:
            return None
        return ScrubCommand(command_id=command_id, action="list", page=page)

    if not has_whitespace or not arg:
        return None
    if len(arg) > MAX_GROUP_SCRUB_EXTRA_WORD_LEN:
        return None
    action = "add" if command_word == ADD_COMMAND else "remove"
    return ScrubCommand(command_id=command_id, action=action, word=arg)


def _matcher_command_words(matcher: object) -> list[str]:
    from pallas.core.platform.ingress.matcher_activation import iter_matcher_checker_calls

    words: list[str] = []
    for call in iter_matcher_checker_calls(matcher):
        cmds = getattr(call, "cmds", None)
        if not cmds:
            continue
        words.extend(cmd[0] for cmd in cmds if len(cmd) == 1)
    return words


def matcher_scrub_command_id(matcher: object) -> str | None:
    """按 matcher 身份识别本功能目标命令 ID；与权限 meta 解耦。

    私聊 Bot 级 matcher 由注册时固定的目标 ID 决定：固定属性非法或与 CommandRule
    命令字不一致时返回 ``None``，不回退成群命令，避免群/私同命令字串号。
    """
    fixed = getattr(matcher, _FIXED_TARGET_ATTR, None)
    if fixed:
        expected_word = _BOT_SCRUB_WORD_BY_ID.get(str(fixed))
        if expected_word is None:
            return None
        if expected_word in _matcher_command_words(matcher):
            return str(fixed)
        return None

    for word in _matcher_command_words(matcher):
        command_id = SCRUB_COMMAND_IDS.get(word)
        if command_id is not None:
            return command_id
    return None


async def bot_scrub_manage_authorized(bot: object, event: object, command_id: str) -> bool:
    """私聊 Bot 级词管理硬条件：仅当前 Bot 号主 + 命令权限，fail-closed。

    未绑定超管、其它 Bot 号主、群管、ACL allow/admin bypass、cmd_perm everyone
    都不能越过「当前 Bot 号主」这一硬条件。
    """
    if not manageable_private_event(event):
        return False
    try:
        user_id = int(event.get_user_id())
        self_id = int(bot.self_id)
    except Exception:  # noqa: BLE001
        return False
    try:
        from pallas.core.foundation.config import user_is_bot_admin

        if not await user_is_bot_admin(self_id, user_id):
            return False
    except Exception:  # noqa: BLE001
        return False
    try:
        from pallas.core.perm.check import satisfies_command_permission

        return await satisfies_command_permission(bot, event, command_id)
    except Exception:  # noqa: BLE001
        return False


def bot_scrub_owner_rule(command_id: str):
    """matcher 级硬条件 Rule：与 hook / handler 复用同一 checker。"""

    async def _rule(bot: Bot, event: Event) -> bool:
        return await bot_scrub_manage_authorized(bot, event, command_id)

    return _rule
