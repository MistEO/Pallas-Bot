from __future__ import annotations

from .api_chain import build_review_providers, clear_remote_review_caches, run_review_chain
from .config import (
    MessageScrubConfig,
    clear_message_scrub_config_cache,
    get_message_scrub_config,
    is_message_scrub_enabled,
)
from .group_extra import (
    apply_bot_scrub_extra_local,
    apply_group_scrub_extra_local,
    bot_scrub_extra_hits,
    group_scrub_extra_hits,
    init_bot_scrub_snapshot,
    init_group_scrub_snapshot,
    normalize_group_scrub_extra,
    reset_bot_scrub_snapshot,
    reset_group_scrub_snapshot,
    start_group_scrub_refresh_loop,
    stop_group_scrub_refresh_loop,
)
from .local_lexicon import local_lexicon_hits, reload_local_lexicon_caches
from .startup_log import install_message_scrub_startup_log


def start_message_scrub_if_enabled() -> None:
    """在 ``nonebot.init()`` 之后调用；未启用时不注册 startup 日志钩子。"""
    if is_message_scrub_enabled():
        install_message_scrub_startup_log()


def reload_message_scrub_caches() -> None:
    """热重载本地词库与远程审查缓存"""
    clear_message_scrub_config_cache()
    reload_local_lexicon_caches()
    clear_remote_review_caches()


def is_message_scrub_blocked_sync(
    *,
    plain_text: str,
    raw_message: str,
    group_id: int | None = None,
    bot_id: int | None = None,
) -> bool:
    """全局本地词库 + 该 Bot 追加词 + 该群追加词（内存快照）。"""
    if not is_message_scrub_enabled():
        return False
    if local_lexicon_hits(plain_text=plain_text, raw_message=raw_message):
        return True
    if bot_scrub_extra_hits(bot_id=bot_id, plain_text=plain_text, raw_message=raw_message):
        return True
    return group_scrub_extra_hits(group_id=group_id, plain_text=plain_text, raw_message=raw_message)


async def is_message_scrub_blocked_async(
    *,
    plain_text: str,
    raw_message: str,
    group_id: int | None = None,
    bot_id: int | None = None,
) -> bool:
    """本地词库 + Bot / 群追加词优先；未命中后按审查链调用远程 API。"""
    if not is_message_scrub_enabled():
        return False
    if local_lexicon_hits(plain_text=plain_text, raw_message=raw_message):
        return True
    if bot_scrub_extra_hits(bot_id=bot_id, plain_text=plain_text, raw_message=raw_message):
        return True
    if group_scrub_extra_hits(group_id=group_id, plain_text=plain_text, raw_message=raw_message):
        return True
    return await run_review_chain(plain_text=plain_text, raw_message=raw_message)


__all__ = [
    "MessageScrubConfig",
    "apply_bot_scrub_extra_local",
    "apply_group_scrub_extra_local",
    "bot_scrub_extra_hits",
    "build_review_providers",
    "get_message_scrub_config",
    "group_scrub_extra_hits",
    "init_bot_scrub_snapshot",
    "init_group_scrub_snapshot",
    "is_message_scrub_blocked_async",
    "is_message_scrub_blocked_sync",
    "is_message_scrub_enabled",
    "normalize_group_scrub_extra",
    "reload_message_scrub_caches",
    "reset_bot_scrub_snapshot",
    "reset_group_scrub_snapshot",
    "start_group_scrub_refresh_loop",
    "start_message_scrub_if_enabled",
    "stop_group_scrub_refresh_loop",
]
