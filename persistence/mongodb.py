"""MongoDB 客户端创建和健康检查。"""

from pymongo import MongoClient


def create_mongodb_client(uri: str, timeout_ms: int = 3000) -> MongoClient:
    """创建已验证连接；连接失败时让服务明确启动失败。"""

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        tz_aware=True,
    )
    client.admin.command("ping")
    return client
