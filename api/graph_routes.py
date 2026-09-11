"""静态构建图和运行轨迹接口。"""

from fastapi import APIRouter, HTTPException

from intent_recognition_agent.persistence.trace_repository import TraceOwnershipError
from intent_recognition_agent.services.container import graph_service


router = APIRouter(prefix="/intent-graph", tags=["意图识别运行图"])


@router.get("/definition")
def definition() -> dict:
    return graph_service.definition()


@router.get("/traces/{thread_id}")
def trace(thread_id: str, user_id: str) -> dict:
    try:
        return graph_service.trace(thread_id, user_id)
    except TraceOwnershipError as exc:
        raise HTTPException(status_code=403, detail="无权访问其他用户的运行轨迹") from exc
