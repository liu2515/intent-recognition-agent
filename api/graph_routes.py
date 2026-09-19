"""静态构建图和运行轨迹接口。"""

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from intent_recognition_agent.persistence.intent_repository import (
    IntentOwnershipError,
    IntentTaskNotFoundError,
)
from intent_recognition_agent.persistence.trace_repository import TraceOwnershipError
from intent_recognition_agent.services.container import graph_service, intent_service


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


@router.get("/traces/{thread_id}/events")
async def trace_events(thread_id: str, user_id: str) -> StreamingResponse:
    """Stream each newly completed node as a Server-Sent Event."""
    async def event_stream():
        sent: set[tuple[str, str, str, str]] = set()
        waiting_rounds = 0
        while True:
            try:
                # LangGraph/MongoDB 状态历史读取是同步 I/O，不能直接占用
                # FastAPI 事件循环，否则一次慢查询会让整个服务都无法响应。
                events = await asyncio.to_thread(
                    intent_service.live_trace,
                    thread_id=thread_id,
                    user_id=user_id,
                )
                waiting_rounds = 0
            except IntentTaskNotFoundError:
                waiting_rounds += 1
                if waiting_rounds > 40:
                    yield 'event: error\ndata: {"message":"recognition did not start"}\n\n'
                    return
                await asyncio.sleep(0.15)
                continue
            except (PermissionError, IntentOwnershipError, TraceOwnershipError):
                yield 'event: error\ndata: {"message":"trace access denied"}\n\n'
                return

            for event in events:
                event_id = (
                    str(event.get("task_id", "")),
                    str(event.get("node", "")),
                    str(event.get("step", "")),
                    str(event.get("created_at", "")),
                )
                if event_id in sent:
                    continue
                sent.add(event_id)
                yield f"event: trace\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

            if not intent_service.is_live_thread(thread_id):
                yield "event: complete\ndata: {}\n\n"
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
