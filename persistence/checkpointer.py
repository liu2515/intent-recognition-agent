"""意图识别图的 Checkpointer 工厂。"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient


def create_checkpointer(
    client: MongoClient | None = None,
    *,
    database_name: str = "intent_recognition_db",
) -> BaseCheckpointSaver:
    """创建独立于主聊天图的 Checkpointer。

    正式服务传入 MongoClient 后持久化到 MongoDB；测试不传 client 时使用内存。
    """

    if client is None:
        return InMemorySaver()
    return MongoDBSaver(
        client=client,
        db_name=database_name,
        checkpoint_collection_name="intent_checkpoints",
        writes_collection_name="intent_checkpoint_writes",
    )
