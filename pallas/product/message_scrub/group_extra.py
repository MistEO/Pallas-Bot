"""群级 message_scrub 追加屏蔽词：进程内快照 + 周期刷新。

仅「追加」全局词库；全局总开关 ``PALLAS_MESSAGE_SCRUB_ENABLED`` 关闭时群词同样失效。
消息路径只读内存快照，不查 DB、不发远程请求。
"""

from __future__ import annotations

import asyncio
from threading import Lock
from typing import Any

from nonebot import logger

from pallas.core.foundation.logging import log_rate_limited

MAX_GROUP_SCRUB_EXTRA_WORDS = 200
MAX_GROUP_SCRUB_EXTRA_WORD_LEN = 64
GROUP_SCRUB_REFRESH_INTERVAL_SEC = 30.0

_lock = Lock()
_snapshot: dict[int, tuple[str, ...]] = {}
_version = 0
_refresh_task: asyncio.Task | None = None


def normalize_group_scrub_extra(raw: object) -> list[str]:
    """校验并归一化群追加词：strip、去空、大小写不敏感去重；非法即抛 ``ValueError``。"""
    if not isinstance(raw, list):
        raise ValueError("message_scrub_extra 必须是字符串列表")
    if len(raw) > MAX_GROUP_SCRUB_EXTRA_WORDS:
        raise ValueError(f"message_scrub_extra 最多 {MAX_GROUP_SCRUB_EXTRA_WORDS} 个词")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("message_scrub_extra 仅接受字符串")
        word = item.strip()
        if not word:
            continue
        if len(word) > MAX_GROUP_SCRUB_EXTRA_WORD_LEN:
            raise ValueError(f"message_scrub_extra 每个词最长 {MAX_GROUP_SCRUB_EXTRA_WORD_LEN} 个字符")
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(word)
    return out


def _safe_words(raw: Any) -> tuple[str, ...]:
    """存量脏数据兜底：跳过非字符串 / 超长项，去空去重后转小写。"""
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        word = item.strip()
        if not word or len(word) > MAX_GROUP_SCRUB_EXTRA_WORD_LEN:
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) >= MAX_GROUP_SCRUB_EXTRA_WORDS:
            break
    return tuple(out)


def _build_snapshot(rows: Any) -> dict[int, tuple[str, ...]]:
    out: dict[int, tuple[str, ...]] = {}
    for row in rows or []:
        try:
            group_id = int(getattr(row, "group_id", 0) or 0)
        except (TypeError, ValueError):
            continue
        words = _safe_words(getattr(row, "message_scrub_extra", None))
        if group_id and words:
            out[group_id] = words
    return out


def reset_group_scrub_snapshot() -> None:
    """清空快照与版本号（供测试与重载使用）。"""
    global _snapshot, _version
    with _lock:
        _snapshot = {}
        _version = 0


def apply_group_scrub_extra_local(group_id: int, words: list[str]) -> None:
    """本进程保存成功后立即 patch 内存；递增版本号以挡住进行中的旧 load。"""
    global _version
    normalized = normalize_group_scrub_extra(list(words))
    lowered = tuple(w.lower() for w in normalized)
    with _lock:
        _version += 1
        if lowered:
            _snapshot[int(group_id)] = lowered
        else:
            _snapshot.pop(int(group_id), None)


def group_scrub_extra_hits(*, group_id: int | None, plain_text: str, raw_message: str) -> bool:
    """仅查内存快照；未传 group_id（私聊 / 未知群）时恒 False。"""
    if group_id is None:
        return False
    with _lock:
        words = _snapshot.get(int(group_id))
    if not words:
        return False
    plain = (plain_text or "").lower()
    raw = (raw_message or "").lower()
    return any(word in plain or word in raw for word in words)


async def _load_rows() -> list[Any]:
    from pallas.core.foundation.db import make_group_config_repository

    return await make_group_config_repository().list_all()


async def init_group_scrub_snapshot() -> None:
    """启动首载：与周期刷新同路径，失败保留旧（启动时为空白）快照，不阻断启动。"""
    await refresh_group_scrub_snapshot_once()


async def refresh_group_scrub_snapshot_once() -> None:
    """周期刷新：加载期间若发生本地 patch（版本变化）则丢弃本次结果。"""
    global _snapshot
    with _lock:
        start_version = _version
    try:
        rows = await _load_rows()
    except Exception as exc:  # noqa: BLE001
        log_rate_limited(
            logger,
            "warning",
            "message_scrub.group_extra.refresh",
            "Message scrub group extras refresh failed, kept current snapshot: [{}]",
            exc,
        )
        return
    with _lock:
        if _version != start_version:
            return
        _snapshot = _build_snapshot(rows)


async def _refresh_loop() -> None:
    while True:
        await asyncio.sleep(GROUP_SCRUB_REFRESH_INTERVAL_SEC)
        try:
            await refresh_group_scrub_snapshot_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log_rate_limited(
                logger,
                "warning",
                "message_scrub.group_extra.loop",
                "Message scrub group extras refresh loop error: [{}]",
                exc,
            )


def start_group_scrub_refresh_loop() -> None:
    global _refresh_task
    if _refresh_task is not None and not _refresh_task.done():
        return
    _refresh_task = asyncio.create_task(_refresh_loop(), name="message_scrub_group_extra_refresh")


async def stop_group_scrub_refresh_loop() -> None:
    global _refresh_task
    task = _refresh_task
    _refresh_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
