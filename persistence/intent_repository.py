"""意图任务结果的线程安全存取接口。"""

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from pymongo import ASCENDING, MongoClient


class IntentTaskNotFoundError(LookupError):
    pass


class IntentOwnershipError(PermissionError):
    pass


class IntentRepository:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def save(self, thread_id: str, user_id: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._items[thread_id] = {"user_id": user_id, "value": deepcopy(value)}

    def get(self, thread_id: str, user_id: str) -> dict[str, Any]:
        with self._lock:
            item = self._items.get(thread_id)
            if item is None:
                raise IntentTaskNotFoundError(thread_id)
            if item["user_id"] != user_id:
                raise IntentOwnershipError(thread_id)
            return deepcopy(item["value"])

    def list_completed(self) -> list[dict[str, Any]]:
        """返回可用于图投影的已完成意图，不改变任务事实数据。"""

        with self._lock:
            return [
                {
                    "thread_id": thread_id,
                    "user_id": item["user_id"],
                    "six_tuple": deepcopy(result["six_tuple"]),
                }
                for thread_id, item in self._items.items()
                if (result := item["value"].get("result"))
                and result.get("status") == "completed"
                and result.get("six_tuple")
            ]


class MongoIntentRepository:
    """把最终意图结果持久化到 MongoDB。"""

    def __init__(
        self,
        client: MongoClient,
        database_name: str,
        collection_name: str = "intent_tasks",
    ) -> None:
        self.collection = client[database_name][collection_name]
        self.collection.create_index(
            [("thread_id", ASCENDING)], unique=True, name="uq_intent_thread"
        )
        self.collection.create_index(
            [("user_id", ASCENDING), ("updated_at", ASCENDING)],
            name="ix_intent_user_updated",
        )

    def save(self, thread_id: str, user_id: str, value: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"thread_id": thread_id},
            {
                "$set": {
                    "user_id": user_id,
                    "value": deepcopy(value),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    def get(self, thread_id: str, user_id: str) -> dict[str, Any]:
        item = self.collection.find_one({"thread_id": thread_id})
        if item is None:
            raise IntentTaskNotFoundError(thread_id)
        if item["user_id"] != user_id:
            raise IntentOwnershipError(thread_id)
        return deepcopy(item["value"])

    def list_completed(self) -> list[dict[str, Any]]:
        """读取已完成任务中的主体和六元组，供 Neo4j 重建实名实例。"""

        cursor = self.collection.find(
            {
                "value.result.status": "completed",
                "value.result.six_tuple": {"$ne": None},
            },
            {
                "_id": 0,
                "thread_id": 1,
                "user_id": 1,
                "value.result.six_tuple": 1,
            },
        )
        return [
            {
                "thread_id": item["thread_id"],
                "user_id": item["user_id"],
                "six_tuple": deepcopy(item["value"]["result"]["six_tuple"]),
            }
            for item in cursor
        ]
