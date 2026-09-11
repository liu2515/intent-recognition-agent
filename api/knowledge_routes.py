"""知识候选写回、审核、激活和匹配接口。"""

from fastapi import APIRouter, HTTPException, status

from intent_recognition_agent.api.request_models import (
    KnowledgeCandidateRequest,
    KnowledgeMatchRequest,
    KnowledgeReviewRequest,
)
from intent_recognition_agent.domain.knowledge_models import KnowledgeStatus
from intent_recognition_agent.knowledge.coverage import evaluate_coverage
from intent_recognition_agent.knowledge.matcher import match_knowledge
from intent_recognition_agent.knowledge.repository import (
    DuplicateKnowledgeError,
    KnowledgeNotFoundError,
)
from intent_recognition_agent.knowledge.rule_translator import translate_by_rule
from intent_recognition_agent.services.container import (
    knowledge_graph_service,
    knowledge_repository as repository,
    writeback_service,
)


router = APIRouter(prefix="/knowledge", tags=["意图知识学习"])


@router.get("/rules")
def list_active_rules() -> dict:
    return {
        "items": [item.model_dump(mode="json") for item in repository.list_active()]
    }


@router.get("/graph")
def get_knowledge_graph(include_candidates: bool = True) -> dict:
    return knowledge_graph_service.graph(include_candidates=include_candidates)


@router.post("/graph/sync")
def sync_knowledge_graph() -> dict:
    return knowledge_graph_service.sync()


@router.get("/candidates")
def list_candidates(status_value: KnowledgeStatus | None = None) -> dict:
    return {
        "items": [
            item.model_dump(mode="json")
            for item in repository.list_candidates(status_value)
        ]
    }


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
def create_candidate(request: KnowledgeCandidateRequest) -> dict:
    try:
        candidate = writeback_service.propose(
            utterance=request.utterance,
            six_tuple=request.six_tuple,
            created_by=request.created_by,
            aliases=request.aliases,
            match_keywords=request.match_keywords,
            excluded_keywords=request.excluded_keywords,
        )
    except DuplicateKnowledgeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return candidate.model_dump(mode="json")


@router.post("/candidates/{template_id}/approve")
def approve_candidate(template_id: str, request: KnowledgeReviewRequest) -> dict:
    try:
        approved = writeback_service.approve(template_id, request.reviewer)
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail="知识候选不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return approved.model_dump(mode="json")


@router.post("/candidates/{template_id}/reject")
def reject_candidate(template_id: str, request: KnowledgeReviewRequest) -> dict:
    if not request.reason:
        raise HTTPException(status_code=422, detail="拒绝知识时必须填写原因")
    try:
        rejected = writeback_service.reject(
            template_id,
            request.reviewer,
            request.reason,
        )
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail="知识候选不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return rejected.model_dump(mode="json")


@router.post("/match")
def match_active_rule(request: KnowledgeMatchRequest) -> dict:
    match = match_knowledge(request.text, repository.list_active())
    coverage = evaluate_coverage(match)
    result = None
    if match is not None and coverage.value == "complete":
        result = translate_by_rule(match, request.subject).model_dump(mode="json")

    return {
        "coverage": coverage.value,
        "match": match.model_dump(mode="json") if match else None,
        "six_tuple": result,
    }
