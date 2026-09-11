"""构建过程和运行轨迹存取接口。"""

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from pymongo import ASCENDING, MongoClient


class TraceNotFoundError(LookupError):
    pass


class TraceOwnershipError(PermissionError):
    pass


class TraceRepository:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def replace(
        self,
        thread_id: str,
        events: list[dict[str, Any]],
        *,
        user_id: str | None = None,
    ) -> None:
        with self._lock:
            self._items[thread_id] = {
                "user_id": user_id,
                "events": deepcopy(events),
            }

    def get(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            item = self._items.get(thread_id)
            if item is None:
                return []
            if user_id is not None and item["user_id"] not in {None, user_id}:
                raise TraceOwnershipError(thread_id)
            return deepcopy(item["events"])


class MongoTraceRepository:
    """把 LangGraph 执行轨迹持久化到 MongoDB。"""

    def __init__(
        self,
        client: MongoClient,
        database_name: str,
        collection_name: str = "intent_traces",
    ) -> None:
        self.collection = client[database_name][collection_name]
        self.collection.create_index(
            [("thread_id", ASCENDING)], unique=True, name="uq_trace_thread"
        )
        self.collection.create_index(
            [("user_id", ASCENDING), ("updated_at", ASCENDING)],
            name="ix_trace_user_updated",
        )

    def replace(
        self,
        thread_id: str,
        events: list[dict[str, Any]],
        *,
        user_id: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"thread_id": thread_id},
            {
                "$set": {
                    "user_id": user_id,
                    "events": deepcopy(events),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def get(
        self,
        thread_id: str,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        item = self.collection.find_one({"thread_id": thread_id})
        if item is None:
            return []
        if user_id is not None and item.get("user_id") not in {None, user_id}:
            raise TraceOwnershipError(thread_id)
        return deepcopy(item.get("events", []))
