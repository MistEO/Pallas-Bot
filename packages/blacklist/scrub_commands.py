"""群追加屏蔽词命令：添加 / 删除 / 查看（只改本群 message_scrub_extra）。"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from pallas.api.commands import bind_alias_handlers, group_command
from pallas.api.logging import format_plugin_event
from pallas.product.message_scrub import normalize_group_scrub_extra
from pallas.product.message_scrub.group_extra import (
    MAX_GROUP_SCRUB_EXTRA_WORD_LEN,
    MAX_GROUP_SCRUB_EXTRA_WORDS,
    apply_group_scrub_extra_local,
)
from pallas.product.message_scrub.scrub_command import match_scrub_command

if TYPE_CHECKING:
    from pallas.api.commands import PluginHandlerContext

ADD_SCRUB_PREFIX = "添加屏蔽词"
REMOVE_SCRUB_PREFIX = "删除屏蔽词"
LIST_SCRUB_PREFIX = "查看屏蔽词"
SCRUB_PAGE_SIZE = 20

_ADD_USAGE = f"用法：{ADD_SCRUB_PREFIX} + 要屏蔽的词（可含空格，最多 {MAX_GROUP_SCRUB_EXTRA_WORD_LEN} 个字符）。"
_REMOVE_USAGE = f"用法：{REMOVE_SCRUB_PREFIX} + 要移除的词。"
_LIST_USAGE = f"用法：{LIST_SCRUB_PREFIX} [页码]，页码为数字。"

_group_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def group_scrub_lock(group_id: int) -> asyncio.Lock:
    """同一群的读写序列化锁，避免并发 RMW 丢词（仅同进程）。"""
    return _group_locks[int(group_id)]


async def _load_group_words(group_id: int) -> list[str]:
    from pallas.core.foundation.db import make_group_config_repository

    repo = make_group_config_repository()
    row = await repo.get(int(group_id), ignore_cache=True)
    raw = getattr(row, "message_scrub_extra", None) if row is not None else None
    return list(raw or [])


async def _save_group_words(group_id: int, words: list[str]) -> None:
    from pallas.core.foundation.db import make_group_config_repository

    repo = make_group_config_repository()
    await repo.upsert_field(int(group_id), "message_scrub_extra", list(words))
    apply_group_scrub_extra_local(int(group_id), list(words))


async def list_group_scrub_words(group_id: int) -> list[str]:
    return normalize_group_scrub_extra(await _load_group_words(group_id))


async def add_group_scrub_word(group_id: int, word: str) -> tuple[bool, int]:
    """追加一个词；返回 (是否有变更, 变更后词数)。大小写不敏感去重。

    先规范单词再与 current 查重：满 200 词时重复添加为 no-op，真正新词才拒绝。
    """
    async with group_scrub_lock(group_id):
        current = normalize_group_scrub_extra(await _load_group_words(group_id))
        normalized = normalize_group_scrub_extra([word])
        if not normalized:
            return False, len(current)
        new_word = normalized[0]
        if new_word.lower() in {existing.lower() for existing in current}:
            return False, len(current)
        merged = [*current, new_word]
        if len(merged) > MAX_GROUP_SCRUB_EXTRA_WORDS:
            raise ValueError(f"message_scrub_extra 最多 {MAX_GROUP_SCRUB_EXTRA_WORDS} 个词")
        await _save_group_words(group_id, merged)
        return True, len(merged)


async def remove_group_scrub_word(group_id: int, word: str) -> tuple[bool, int]:
    """移除一个词；返回 (是否有变更, 变更后词数)。只删群追加词，按 lower 等价匹配。"""
    target = word.strip().lower()
    async with group_scrub_lock(group_id):
        current = normalize_group_scrub_extra(await _load_group_words(group_id))
        remaining = [w for w in current if w.lower() != target]
        if len(remaining) == len(current):
            return False, len(current)
        await _save_group_words(group_id, remaining)
        return True, len(remaining)


def _scrub_failure_log(operation: str, ctx: PluginHandlerContext, group_id: int, exc: Exception) -> None:
    logger.warning(
        format_plugin_event(
            operation,
            f"Bot [{ctx.bot.self_id}] failed a group scrub command in group [{group_id}]: [{type(exc).__name__}]",
        )
    )


async def handle_scrub_add(ctx: PluginHandlerContext) -> None:
    group_id = ctx.group_id
    if group_id is None:
        await ctx.finish("这个命令只能在群里用。")
        return
    match = match_scrub_command(ctx.bot, ctx.event)
    if match is None or match.action != "add":
        await ctx.finish(_ADD_USAGE)
        return
    try:
        changed, total = await add_group_scrub_word(group_id, match.word)
    except ValueError:
        await ctx.finish(f"本群追加屏蔽词已达上限（最多 {MAX_GROUP_SCRUB_EXTRA_WORDS} 个），请先删除一些。")
        return
    except Exception as exc:  # noqa: BLE001
        _scrub_failure_log("scrub_add_failed", ctx, group_id, exc)
        await ctx.finish("添加失败，请稍后再试。")
        return
    if not changed:
        await ctx.finish("本群已有这个屏蔽词（不区分大小写）。")
        return
    logger.info(
        format_plugin_event(
            "scrub_add",
            f"Bot [{ctx.bot.self_id}] added a group scrub word in group [{group_id}] at user [{ctx.user_id}]'s request",
        )
    )
    await ctx.finish(f"已添加该屏蔽词，本群现有 {total} 个。")


async def handle_scrub_remove(ctx: PluginHandlerContext) -> None:
    group_id = ctx.group_id
    if group_id is None:
        await ctx.finish("这个命令只能在群里用。")
        return
    match = match_scrub_command(ctx.bot, ctx.event)
    if match is None or match.action != "remove":
        await ctx.finish(_REMOVE_USAGE)
        return
    try:
        changed, total = await remove_group_scrub_word(group_id, match.word)
    except Exception as exc:  # noqa: BLE001
        _scrub_failure_log("scrub_remove_failed", ctx, group_id, exc)
        await ctx.finish("删除失败，请稍后再试。")
        return
    if not changed:
        await ctx.finish("本群没有这个屏蔽词（不区分大小写）。")
        return
    logger.info(
        format_plugin_event(
            "scrub_remove",
            f"Bot [{ctx.bot.self_id}] removed a group scrub word in group [{group_id}] "
            f"at user [{ctx.user_id}]'s request",
        )
    )
    if total == 0:
        await ctx.finish("已删除该屏蔽词，本群已无追加屏蔽词。")
    else:
        await ctx.finish(f"已删除该屏蔽词，本群还剩 {total} 个。")


async def handle_scrub_list(ctx: PluginHandlerContext) -> None:
    group_id = ctx.group_id
    if group_id is None:
        await ctx.finish("这个命令只能在群里用。")
        return
    match = match_scrub_command(ctx.bot, ctx.event)
    if match is None or match.action != "list":
        await ctx.finish(_LIST_USAGE)
        return
    page = match.page
    try:
        words = await list_group_scrub_words(group_id)
    except Exception as exc:  # noqa: BLE001
        _scrub_failure_log("scrub_list_failed", ctx, group_id, exc)
        await ctx.finish("查看失败，请稍后再试。")
        return
    total = len(words)
    total_pages = max(1, (total + SCRUB_PAGE_SIZE - 1) // SCRUB_PAGE_SIZE)
    if page > total_pages:
        await ctx.finish(f"页码超出范围，本群共 {total_pages} 页。")
        return
    if total == 0:
        await ctx.finish("本群还没有追加屏蔽词。")
        return
    start = (page - 1) * SCRUB_PAGE_SIZE
    chunk = words[start : start + SCRUB_PAGE_SIZE]
    lines = [f"本群追加屏蔽词（共 {total} 个，第 {page}/{total_pages} 页）："]
    lines.extend(f"{start + index + 1}. {word}" for index, word in enumerate(chunk))
    # 以纯文本段回复，避免词里的 CQ 字样被解析成消息段。
    await ctx.finish(Message(MessageSegment.text("\n".join(lines))))


add_scrub_cmd = group_command("blacklist.scrub_add", ADD_SCRUB_PREFIX, cd_sec=3)
remove_scrub_cmd = group_command("blacklist.scrub_remove", REMOVE_SCRUB_PREFIX, cd_sec=3)
list_scrub_cmd = group_command("blacklist.scrub_list", LIST_SCRUB_PREFIX, cd_sec=3)

bind_alias_handlers(add_scrub_cmd, handle_scrub_add)
bind_alias_handlers(remove_scrub_cmd, handle_scrub_remove)
bind_alias_handlers(list_scrub_cmd, handle_scrub_list)
