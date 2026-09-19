"""把经过确认的大模型六元组转成可复用知识。"""

import logging
from typing import Any
from uuid import uuid4

from intent_recognition_agent.domain.knowledge_models import KnowledgeTemplate
from intent_recognition_agent.domain.six_tuple import (
    AccountStatus,
    ConstraintStatus,
    CriterionStatus,
    GoalStatus,
    IntentSixTuple,
    Subject,
    VerificationStatus,
)
from intent_recognition_agent.knowledge.matcher import (
    normalize_utterance,
    redact_mobile_numbers,
)
from intent_recognition_agent.knowledge.repository import KnowledgeRepository
from intent_recognition_agent.knowledge.schema import six_tuple_to_triples


logger = logging.getLogger(__name__)


def _strip_runtime_annotations(value: str | None) -> str | None:
    """移除被模型拼进业务字段的补充会话和工具回显。"""

    if value is None:
        return None
    cleaned = value
    for marker in ("\n用户补充：", "\n只读工具返回：", "\n工具返回："):
        cleaned = cleaned.split(marker, 1)[0]
    return redact_mobile_numbers(cleaned.strip())


def generalize_six_tuple(six_tuple: IntentSixTuple) -> IntentSixTuple:
    """移除用户私有信息和单次运行结果，得到可复用模板。"""

    template = six_tuple.model_copy(deep=True)
    template.subject = Subject(
        role=six_tuple.subject.role,
        customer_type=six_tuple.subject.customer_type,
        verification_status=VerificationStatus.UNKNOWN,
        account_status=AccountStatus.UNKNOWN,
        description="当前用户及其业务账户",
    )
    if template.business_object is not None:
        template.business_object.object_id = None

    context = template.context_parameters
    context.user_request = None
    context.order_id = None
    context.work_order_id = None
    context.contact = None
    context.extra = {}
    if context.network is not None:
        context.network.symptom = _strip_runtime_annotations(context.network.symptom)
    if context.location is not None:
        context.location.address = None
        context.location.longitude = None
        context.location.latitude = None
    if context.billing is not None:
        context.billing.transaction_id = None
        context.billing.taxpayer_number = None
        context.billing.delivery_email = None

    for item in [*template.constraints.hard, *template.constraints.soft]:
        item.actual = None
        item.status = ConstraintStatus.PENDING

    template.constraints.confirmation.confirmed = False
    template.constraints.confirmation.confirmation_text = None
    template.constraints.confirmation.confirmed_at = None

    template.goal.status = GoalStatus.PENDING
    for criterion in template.goal.success_criteria:
        criterion.actual = None
        criterion.status = CriterionStatus.PENDING
        criterion.evidence = {}

    return template


class KnowledgeWritebackService:
    """提供知识生成、确认即激活以及删除操作。"""

    def __init__(
        self,
        repository: KnowledgeRepository,
        graph_store: Any | None = None,
    ) -> None:
        self.repository = repository
        self.graph_store = graph_store

    def propose(
        self,
        *,
        utterance: str,
        six_tuple: IntentSixTuple,
        created_by: str,
        aliases: list[str] | None = None,
        match_keywords: list[str] | None = None,
        excluded_keywords: list[str] | None = None,
    ) -> KnowledgeTemplate:
        generalized = generalize_six_tuple(six_tuple)
        safe_utterance = redact_mobile_numbers(utterance.strip())
        safe_aliases = [redact_mobile_numbers(item) for item in aliases or []]
        keywords = match_keywords or [generalized.action.name.value]

        candidate = KnowledgeTemplate(
            template_id=f"intent-{uuid4().hex}",
            canonical_utterance=safe_utterance,
            normalized_utterance=normalize_utterance(safe_utterance),
            aliases=safe_aliases,
            match_keywords=keywords,
            excluded_keywords=excluded_keywords or [],
            six_tuple=generalized,
            triples=six_tuple_to_triples(generalized),
            origin="llm",
            created_by=created_by,
        )
        return self.repository.add_candidate(candidate)

    def approve(self, template_id: str, reviewer: str) -> KnowledgeTemplate:
        approved = self.repository.approve(template_id, reviewer)
        if self.graph_store is not None:
            try:
                self.graph_store.upsert_template(approved)
            except Exception:
                logger.exception("知识已在 MongoDB 生效，但同步 Neo4j 失败")
        return approved

    def activate_confirmed(
        self,
        *,
        utterance: str,
        six_tuple: IntentSixTuple,
        confirmed_by: str,
        aliases: list[str] | None = None,
        match_keywords: list[str] | None = None,
        excluded_keywords: list[str] | None = None,
    ) -> KnowledgeTemplate:
        """生成知识并以当前用户确认作为审核依据，立即激活。"""

        candidate = self.propose(
            utterance=utterance,
            six_tuple=six_tuple,
            created_by=confirmed_by,
            aliases=aliases,
            match_keywords=match_keywords,
            excluded_keywords=excluded_keywords,
        )
        return self.approve(candidate.template_id, confirmed_by)

    def reject(
        self,
        template_id: str,
        reviewer: str,
        reason: str,
    ) -> KnowledgeTemplate:
        return self.repository.reject(template_id, reviewer, reason)

    def delete(self, template_id: str) -> KnowledgeTemplate:
        """删除事实来源中的模板，并立即删除对应 Neo4j 投影。"""

        deleted = self.repository.delete(template_id)
        if self.graph_store is not None:
            try:
                self.graph_store.delete_template(template_id)
            except Exception:
                logger.exception("知识已从事实来源删除，但 Neo4j 投影删除失败")
                # 全量重建仍以事实来源为准，可清除该模板遗留的图数据。
                try:
                    self.graph_store.rebuild(self.repository.list_active())
                except Exception:
                    logger.exception("Neo4j 知识图谱重建失败")
                    raise
        return deleted
