"""群追加屏蔽词命令的固定识别，供入站免审与 matcher 隔离复用。

只识别三条固定命令（添加/删除/查看屏蔽词）与对应命令 ID，不依赖 blacklist 插件包。
识别以 NoneBot ``TrieRule`` 为准，与真实 matcher 注册保持一致。
"""

from __future__ import annotations

from dataclasses import dataclass

from nonebot.adapters.onebot.v11 import GroupMessageEvent
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

_MARKER_ATTR = "_pallas_scrub_command_id"


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


MAX_PAGE_DIGITS = 10


def _extract_command_arg(event: object, prefix: dict) -> tuple[str, bool]:
    """从事件真实明文取命令后参数（保留 &、[CQ:...] 等字面），返回 (arg, has_whitespace)。

    只群消息事件：``GroupTempPrivateMessageEvent`` 继承私聊事件但带 group_id，不得误豁免。
    """
    raw_command = prefix.get(RAW_CMD_KEY)
    if not raw_command:
        return "", False
    plain = str(event.get_message().extract_plain_text() or "").lstrip()
    if not plain.startswith(raw_command):
        return "", False
    arg = plain[len(raw_command) :].strip()
    return arg, bool(prefix.get(CMD_WHITESPACE_KEY))


def match_scrub_command(bot: object, event: object) -> ScrubCommand | None:
    """群事件 + 严格语法时返回匹配；任何不满足（含紧贴参数、伪前缀、混合 CQ）返回 None。"""
    if not isinstance(event, GroupMessageEvent):
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
    command_id = SCRUB_COMMAND_IDS.get(command_word)
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


def matcher_scrub_command_id(matcher: object) -> str | None:
    """按 matcher 的 CommandRule 命令字识别是否为本功能目标；与权限 meta 解耦。"""
    from pallas.core.platform.ingress.matcher_activation import iter_matcher_checker_calls

    for call in iter_matcher_checker_calls(matcher):
        cmds = getattr(call, "cmds", None)
        if not cmds:
            continue
        for cmd in cmds:
            if len(cmd) == 1:
                command_id = SCRUB_COMMAND_IDS.get(cmd[0])
                if command_id is not None:
                    return command_id
    return None
