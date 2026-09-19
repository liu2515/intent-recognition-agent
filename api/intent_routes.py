"""意图启动、恢复和结果查询接口。"""

from fastapi import APIRouter, HTTPException

from intent_recognition_agent.api.request_models import (
    IntentResumeRequest,
    IntentSixTupleExportRequest,
    IntentStartRequest,
)
from intent_recognition_agent.domain.six_tuple import IntentSixTuple
from intent_recognition_agent.llm.client import IntentTranslationError
from intent_recognition_agent.persistence.intent_repository import (
    IntentOwnershipError,
    IntentTaskNotFoundError,
)
from intent_recognition_agent.services.container import intent_service


router = APIRouter(prefix="/intents", tags=["意图识别"])


@router.post("/recognize")
def recognize(request: IntentStartRequest) -> dict:
    try:
        return intent_service.start(
            text=request.text,
            user_id=request.user_id,
            thread_id=request.thread_id,
            session_id=request.session_id,
            subject=request.subject,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IntentTranslationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{thread_id}/resume")
def resume(thread_id: str, request: IntentResumeRequest) -> dict:
    try:
        return intent_service.resume(
            thread_id=thread_id,
            user_id=request.user_id,
            answer=request.answer,
        )
    except IntentTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="意图任务不存在") from exc
    except IntentOwnershipError as exc:
        raise HTTPException(status_code=403, detail="无权访问其他用户的意图任务") from exc
    except IntentTranslationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{thread_id}")
def get_result(thread_id: str, user_id: str) -> dict:
    try:
        return intent_service.get(thread_id=thread_id, user_id=user_id)
    except IntentTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="意图任务不存在") from exc
    except IntentOwnershipError as exc:
        raise HTTPException(status_code=403, detail="无权访问其他用户的意图任务") from exc


@router.post("/{thread_id}/six-tuple", response_model=IntentSixTuple)
def export_six_tuple(thread_id: str, request: IntentSixTupleExportRequest) -> dict:
    """Return JSON containing only the requested six-tuple for a downstream consumer."""
    try:
        return intent_service.export_six_tuple(
            thread_id=thread_id,
            user_id=request.user_id,
            task_id=request.task_id,
        )
    except IntentTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="意图任务不存在") from exc
    except IntentOwnershipError as exc:
        raise HTTPException(status_code=403, detail="无权访问其他用户的意图任务") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
