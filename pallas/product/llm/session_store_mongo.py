from __future__ import annotations

import time
from typing import TYPE_CHECKING

from beanie import PydanticObjectId, SortDirection
from nonebot import logger

from pallas.core.foundation.db.modules import LlmChatMessage
from pallas.core.foundation.logging import log_rate_limited
from pallas.product.llm.session_models import (
    ALLOWED_ROLES,
    LlmChatRole,
    LlmChatTurn,
    LlmHistorySessionSummary,
    LlmSessionSnapshotTurn,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def _parse_mongo_message_ids(raw_ids: Sequence[str]) -> list[PydanticObjectId] | None:
    ids: list[PydanticObjectId] = []
    for raw in raw_ids:
        text = str(raw)
        if not text:
            return None
        try:
            ids.append(PydanticObjectId(text))
        except Exception:
            return None
    if not ids or len({str(item) for item in ids}) != len(ids):
        return None
    return ids


class MongoLlmSessionMessageBackend:
    async def append_message(
        self,
        bot_id: int,
        group_id: int,
        user_id: int,
        role: LlmChatRole,
        content: str,
        *,
        ttl_sec: int,
        window: int,
    ) -> bool:
        now = int(time.time())
        doc = LlmChatMessage(
            bot_id=int(bot_id),
            group_id=int(group_id),
            user_id=int(user_id),
            role=role,
            content=content,
            created_at=now,
        )
        await doc.insert()
        await self._purge_user_ttl(
            bot_id=int(bot_id),
            group_id=int(group_id),
            user_id=int(user_id),
            ttl_sec=ttl_sec,
            now=now,
        )
        await self._trim_user_window(
            bot_id=int(bot_id),
            group_id=int(group_id),
            user_id=int(user_id),
            window=window,
        )
        if group_id != 0:
            await self._purge_group_ttl(
                bot_id=int(bot_id),
                group_id=int(group_id),
                ttl_sec=ttl_sec,
                now=now,
            )
        return True

    async def list_user_messages(
        self,
        bot_id: int,
        group_id: int,
        user_id: int,
        *,
        limit: int,
        ttl_sec: int,
    ) -> list[LlmChatTurn]:
        query = {
            "bot_id": int(bot_id),
            "group_id": int(group_id),
            "user_id": int(user_id),
        }
        if ttl_sec > 0:
            query["created_at"] = {"$gte": int(time.time()) - ttl_sec}
        rows = (
            await LlmChatMessage
            .find(query)
            .sort(
                [("created_at", SortDirection.DESCENDING), ("_id", SortDirection.DESCENDING)],
            )
            .limit(limit)
            .to_list()
        )
        return [
            LlmChatTurn(
                role=row.role if row.role in ALLOWED_ROLES else "user",
                content=row.content,
                user_id=int(row.user_id),
                created_at=int(row.created_at),
            )
            for row in reversed(rows)
        ]

    async def read_user_compaction_snapshot(
        self,
        bot_id: int,
        group_id: int,
        user_id: int,
        *,
        limit: int,
        ttl_sec: int,
    ) -> list[LlmSessionSnapshotTurn] | None:
        max_items = max(1, int(limit))
        query: dict = {
            "bot_id": int(bot_id),
            "group_id": int(group_id),
            "user_id": int(user_id),
        }
        if ttl_sec > 0:
            query["created_at"] = {"$gte": int(time.time()) - ttl_sec}
        rows = (
            await LlmChatMessage
            .find(query)
            .sort(
                [("created_at", SortDirection.DESCENDING), ("_id", SortDirection.DESCENDING)],
            )
            .limit(max_items + 1)
            .to_list()
        )
        if len(rows) > max_items:
            return None
        return [
            LlmSessionSnapshotTurn(
                role=row.role if row.role in ALLOWED_ROLES else "user",
                content=row.content,
                user_id=int(row.user_id),
                created_at=int(row.created_at),
                message_id=str(row.id),
            )
            for row in reversed(rows)
        ]

    async def list_group_ambient(
        self,
        bot_id: int,
        group_id: int,
        *,
        limit: int,
        ttl_sec: int,
    ) -> list[LlmChatTurn]:
        query: dict = {
            "bot_id": int(bot_id),
            "group_id": int(group_id),
        }
        if ttl_sec > 0:
            query["created_at"] = {"$gte": int(time.time()) - ttl_sec}
        rows = (
            await LlmChatMessage
            .find(query)
            .sort(
                [("created_at", SortDirection.DESCENDING), ("_id", SortDirection.DESCENDING)],
            )
            .limit(limit)
            .to_list()
        )
        return [
            LlmChatTurn(
                role=row.role if row.role in ALLOWED_ROLES else "user",
                content=row.content,
                user_id=int(row.user_id),
                created_at=int(row.created_at),
            )
            for row in reversed(rows)
        ]

    async def list_history_sessions(
        self,
        *,
        bot_id: int | None,
        group_id: int | None,
        user_id: int | None,
        limit: int,
    ) -> list[LlmHistorySessionSummary]:
        match: dict = {}
        if bot_id is not None:
            match["bot_id"] = int(bot_id)
        if group_id is not None:
            match["group_id"] = int(group_id)
        if user_id is not None:
            match["user_id"] = int(user_id)

        pipeline: list[dict] = []
        if match:
            pipeline.append({"$match": match})
        pipeline.extend([
            {
                "$group": {
                    "_id": {
                        "bot_id": "$bot_id",
                        "group_id": "$group_id",
                        "user_id": "$user_id",
                    },
                    "turn_count": {"$sum": 1},
                    "first_created_at": {"$min": "$created_at"},
                    "last_created_at": {"$max": "$created_at"},
                }
            },
            {"$sort": {"last_created_at": -1}},
            {"$limit": int(limit)},
        ])
        coll = LlmChatMessage.get_pymongo_collection()
        rows = await coll.aggregate(pipeline).to_list(length=limit)

        out: list[LlmHistorySessionSummary] = []
        for row in rows:
            key = row.get("_id") or {}
            bid = int(key.get("bot_id") or 0)
            gid = int(key.get("group_id") or 0)
            uid = int(key.get("user_id") or 0)
            latest = (
                await LlmChatMessage
                .find({
                    "bot_id": bid,
                    "group_id": gid,
                    "user_id": uid,
                })
                .sort(
                    [("created_at", SortDirection.DESCENDING), ("_id", SortDirection.DESCENDING)],
                )
                .limit(1)
                .to_list()
            )
            if not latest:
                continue
            item = latest[0]
            role = item.role if item.role in ALLOWED_ROLES else "user"
            out.append(
                LlmHistorySessionSummary(
                    session_key=f"{bid}:{gid}:{uid}",
                    bot_id=bid,
                    group_id=gid,
                    user_id=uid,
                    turn_count=int(row.get("turn_count") or 0),
                    first_created_at=int(row.get("first_created_at") or 0),
                    last_created_at=int(row.get("last_created_at") or 0),
                    last_role=role,
                    last_content=str(item.content or ""),
                )
            )
        return out

    async def clear_group(self, bot_id: int, group_id: int) -> int:
        query = {"bot_id": int(bot_id), "group_id": int(group_id)}
        count = await LlmChatMessage.find(query).count()
        await LlmChatMessage.find(query).delete()
        return int(count)

    async def clear_user(self, bot_id: int, group_id: int, user_id: int) -> int:
        query = {
            "bot_id": int(bot_id),
            "group_id": int(group_id),
            "user_id": int(user_id),
        }
        count = await LlmChatMessage.find(query).count()
        await LlmChatMessage.find(query).delete()
        return int(count)

    async def compact_user_with_summary(
        self,
        bot_id: int,
        group_id: int,
        user_id: int,
        summary_content: str,
        *,
        keep_messages: int,
        source_message_ids: Sequence[str] | None = None,
        summary_created_at: int | None = None,
    ) -> bool:
        if source_message_ids is not None:
            if summary_created_at is None:
                return False
            message_ids = _parse_mongo_message_ids(source_message_ids)
            if message_ids is None:
                return False
            return await self._compact_user_with_summary_ids(
                bot_id,
                group_id,
                user_id,
                summary_content,
                message_ids=message_ids,
                summary_created_at=int(summary_created_at),
            )
        keep = max(2, int(keep_messages))
        now = int(time.time())
        query = {
            "bot_id": int(bot_id),
            "group_id": int(group_id),
            "user_id": int(user_id),
        }
        rows = (
            await LlmChatMessage
            .find(query)
            .sort(
                [("created_at", SortDirection.ASCENDING), ("_id", SortDirection.ASCENDING)],
            )
            .to_list()
        )
        if len(rows) <= keep:
            return False
        keep_rows = rows[-keep:]
        keep_ids = {row.id for row in keep_rows}
        stale = [row for row in rows if row.id not in keep_ids]
        for row in stale:
            await row.delete()
        anchor_time = int(keep_rows[0].created_at) - 1 if keep_rows else now - 1
        await LlmChatMessage(
            bot_id=int(bot_id),
            group_id=int(group_id),
            user_id=int(user_id),
            role="user",
            content=summary_content,
            created_at=anchor_time,
        ).insert()
        return True

    async def _compact_user_with_summary_ids(
        self,
        bot_id: int,
        group_id: int,
        user_id: int,
        summary_content: str,
        *,
        message_ids: list[PydanticObjectId],
        summary_created_at: int,
    ) -> bool:
        scope_query = {
            "bot_id": int(bot_id),
            "group_id": int(group_id),
            "user_id": int(user_id),
        }
        delete_query = {**scope_query, "_id": {"$in": message_ids}}
        # Mongo 无事务：先有界校验来源，插入摘要后再按 scope + 精确 _id 删除；失败不补偿。
        present = await LlmChatMessage.find(delete_query).limit(len(message_ids)).to_list()
        if {str(row.id) for row in present} != {str(item) for item in message_ids}:
            return False
        try:
            await LlmChatMessage(
                bot_id=int(bot_id),
                group_id=int(group_id),
                user_id=int(user_id),
                role="user",
                content=summary_content,
                created_at=int(summary_created_at),
            ).insert()
        except Exception as exc:
            log_rate_limited(
                logger,
                "warning",
                "llm.session_store.mongo_compaction_insert_failed",
                "Mongo session summary insert failed for bot [{}], group [{}], user [{}]: [{}]",
                int(bot_id),
                int(group_id),
                int(user_id),
                type(exc).__name__,
            )
            return False
        try:
            result = await LlmChatMessage.find(delete_query).delete()
        except Exception as exc:
            log_rate_limited(
                logger,
                "warning",
                "llm.session_store.mongo_compaction_delete_failed",
                "Mongo session compaction delete failed for bot [{}], group [{}], user [{}]: [{}]",
                int(bot_id),
                int(group_id),
                int(user_id),
                type(exc).__name__,
            )
            return False
        return int(getattr(result, "deleted_count", 0) or 0) == len(message_ids)

    async def _purge_user_ttl(
        self,
        *,
        bot_id: int,
        group_id: int,
        user_id: int,
        ttl_sec: int,
        now: int,
    ) -> None:
        if ttl_sec <= 0:
            return
        await LlmChatMessage.find({
            "bot_id": bot_id,
            "group_id": group_id,
            "user_id": user_id,
            "created_at": {"$lt": now - ttl_sec},
        }).delete()

    async def _purge_group_ttl(
        self,
        *,
        bot_id: int,
        group_id: int,
        ttl_sec: int,
        now: int,
    ) -> None:
        if ttl_sec <= 0 or group_id == 0:
            return
        await LlmChatMessage.find({
            "bot_id": bot_id,
            "group_id": group_id,
            "created_at": {"$lt": now - ttl_sec},
        }).delete()

    async def _trim_user_window(
        self,
        *,
        bot_id: int,
        group_id: int,
        user_id: int,
        window: int,
    ) -> None:
        if window <= 0:
            return
        query = {
            "bot_id": bot_id,
            "group_id": group_id,
            "user_id": user_id,
        }
        count = await LlmChatMessage.find(query).count()
        overflow = int(count) - window
        if overflow <= 0:
            return
        stale = (
            await LlmChatMessage
            .find(query)
            .sort(
                [("created_at", SortDirection.ASCENDING), ("_id", SortDirection.ASCENDING)],
            )
            .limit(overflow)
            .to_list()
        )
        for row in stale:
            await row.delete()
