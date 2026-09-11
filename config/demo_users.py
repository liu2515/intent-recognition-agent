"""独立意图识别工作台的本地演示用户档案。"""

from typing import Any


DEMO_USERS: dict[str, dict[str, str]] = {
    "zhangsan": {"user_id": "zhangsan", "username": "张三"},
    "lisi": {"user_id": "lisi", "username": "李四"},
    "laoxiao": {"user_id": "laoxiao", "username": "老肖"},
}


def get_demo_user(user_id: str | None) -> dict[str, Any] | None:
    """返回演示用户档案副本；生产环境可替换为账户中心查询。"""

    if not user_id:
        return None
    profile = DEMO_USERS.get(user_id)
    return dict(profile) if profile is not None else None
