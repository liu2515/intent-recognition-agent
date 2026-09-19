"""知识写回、激活、删除和匹配接口。"""

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
def get_knowledge_graph(
    include_candidates: bool = True,
    user_id: str | None = None,
    reconcile_deletions: bool = True,
) -> dict:
    return knowledge_graph_service.graph(
        include_candidates=include_candidates,
        user_id=user_id,
        reconcile_deletions=reconcile_deletions,
    )


@router.post("/graph/sync")
def sync_knowledge_graph() -> dict:
    return knowledge_graph_service.sync()


@router.post("/graph/sync-deletions")
def sync_knowledge_graph_deletions() -> dict:
    """将 Neo4j Browser 中的人工删除同步回知识事实库。"""

    return knowledge_graph_service.sync_deletions_from_neo4j()


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
        knowledge = writeback_service.activate_confirmed(
            utterance=request.utterance,
            six_tuple=request.six_tuple,
            confirmed_by=request.created_by,
            aliases=request.aliases,
            match_keywords=request.match_keywords,
            excluded_keywords=request.excluded_keywords,
        )
    except DuplicateKnowledgeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return knowledge.model_dump(mode="json")


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


@router.delete("/templates/{template_id}")
def delete_knowledge_template(template_id: str) -> dict:
    """删除知识模板，并同步移除它在 Neo4j 中的投影。"""

    try:
        deleted = writeback_service.delete(template_id)
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail="知识模板不存在") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"知识已删除，但 Neo4j 同步失败：{exc}",
        ) from exc
    return {
        "status": "deleted",
        "template_id": template_id,
        "deleted_status": deleted.status.value,
    }


@router.post("/match")
def match_active_rule(request: KnowledgeMatchRequest) -> dict:
    match = match_knowledge(request.text, repository.list_active())
    coverage = evaluate_coverage(match)
    result = None
    if match is not None and coverage.value == "complete":
        result = translate_by_rule(match, request.subject, request.text).model_dump(mode="json")

    return {
        "coverage": coverage.value,
        "match": match.model_dump(mode="json") if match else None,
        "six_tuple": result,
    }
