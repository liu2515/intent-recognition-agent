"""MongoDB 版知识模板仓库。"""

from __future__ import annotations

from collections.abc import Iterable

from pymongo import ASCENDING, MongoClient, ReturnDocument

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeStatus,
    KnowledgeTemplate,
    utc_now,
)
from intent_recognition_agent.knowledge.repository import (
    DuplicateKnowledgeError,
    KnowledgeNotFoundError,
    KnowledgeRepository,
)


class MongoKnowledgeRepository:
    """以单集合保存活动规则、待审核候选和驳回记录。"""

    def __init__(
        self,
        client: MongoClient,
        database_name: str,
        collection_name: str = "intent_knowledge",
    ) -> None:
        self.collection = client[database_name][collection_name]
        self.collection.create_index(
            [("template_id", ASCENDING)], unique=True, name="uq_knowledge_template"
        )
        self.collection.create_index(
            [("status", ASCENDING), ("normalized_utterance", ASCENDING)],
            name="ix_knowledge_status_expression",
        )
        self.collection.create_index(
            [("status", ASCENDING), ("six_tuple.action.name", ASCENDING)],
            name="ix_knowledge_status_action",
        )

    @staticmethod
    def _to_model(document: dict) -> KnowledgeTemplate:
        clean = dict(document)
        clean.pop("_id", None)
        return KnowledgeTemplate.model_validate(clean)

    @staticmethod
    def _to_document(template: KnowledgeTemplate) -> dict:
        return template.model_dump(mode="json")

    def list_active(self) -> list[KnowledgeTemplate]:
        cursor = self.collection.find({"status": KnowledgeStatus.ACTIVE.value}).sort(
            [("reviewed_at", ASCENDING), ("created_at", ASCENDING)]
        )
        return [self._to_model(item) for item in cursor]

    def list_candidates(
        self,
        status: KnowledgeStatus | None = None,
    ) -> list[KnowledgeTemplate]:
        query = (
            {"status": status.value}
            if status is not None
            else {"status": {"$ne": KnowledgeStatus.ACTIVE.value}}
        )
        cursor = self.collection.find(query).sort("created_at", ASCENDING)
        return [self._to_model(item) for item in cursor]

    def list_all(self) -> list[KnowledgeTemplate]:
        return [self._to_model(item) for item in self.collection.find({})]

    def add_candidate(self, candidate: KnowledgeTemplate) -> KnowledgeTemplate:
        duplicate = self.collection.find_one(
            {
                "normalized_utterance": candidate.normalized_utterance,
                "six_tuple.action.name": candidate.six_tuple.action.name.value,
                "status": {"$ne": KnowledgeStatus.REJECTED.value},
            }
        )
        if duplicate is not None:
            raise DuplicateKnowledgeError(
                f"相同表达和动作已经存在: {duplicate['template_id']}"
            )
        self.collection.insert_one(self._to_document(candidate))
        return candidate

    def approve(self, template_id: str, reviewer: str) -> KnowledgeTemplate:
        selected = self.collection.find_one({"template_id": template_id})
        if selected is None:
            raise KnowledgeNotFoundError(template_id)
        if selected["status"] != KnowledgeStatus.PENDING.value:
            raise ValueError("只有待审核知识可以被批准")
        updated = self.collection.find_one_and_update(
            {
                "template_id": template_id,
                "status": KnowledgeStatus.PENDING.value,
            },
            {
                "$set": {
                    "status": KnowledgeStatus.ACTIVE.value,
                    "reviewed_by": reviewer,
                    "reviewed_at": utc_now(),
                    "rejection_reason": None,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise ValueError("知识状态已发生变化，请刷新后重试")
        return self._to_model(updated)

    def reject(
        self,
        template_id: str,
        reviewer: str,
        reason: str,
    ) -> KnowledgeTemplate:
        selected = self.collection.find_one({"template_id": template_id})
        if selected is None:
            raise KnowledgeNotFoundError(template_id)
        if selected["status"] != KnowledgeStatus.PENDING.value:
            raise ValueError("只有待审核知识可以被拒绝")
        updated = self.collection.find_one_and_update(
            {
                "template_id": template_id,
                "status": KnowledgeStatus.PENDING.value,
            },
            {
                "$set": {
                    "status": KnowledgeStatus.REJECTED.value,
                    "reviewed_by": reviewer,
                    "reviewed_at": utc_now(),
                    "rejection_reason": reason,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise ValueError("知识状态已发生变化，请刷新后重试")
        return self._to_model(updated)

    def delete(self, template_id: str) -> KnowledgeTemplate:
        """永久删除一个知识模板，无论它是活动规则还是候选记录。"""

        deleted = self.collection.find_one_and_delete({"template_id": template_id})
        if deleted is None:
            raise KnowledgeNotFoundError(template_id)
        return self._to_model(deleted)

    def migrate_from_json(self, legacy: KnowledgeRepository) -> int:
        """幂等迁移原 JSON 中的规则和候选。"""

        from intent_recognition_agent.knowledge.schema import six_tuple_to_triples
        from intent_recognition_agent.knowledge.writeback import generalize_six_tuple

        entries: Iterable[KnowledgeTemplate] = (
            *legacy.list_active(),
            *legacy.list_candidates(),
        )
        migrated = 0
        for entry in entries:
            generalized = generalize_six_tuple(entry.six_tuple)
            sanitized = entry.model_copy(
                update={
                    "six_tuple": generalized,
                    "triples": six_tuple_to_triples(generalized),
                },
                deep=True,
            )
            result = self.collection.update_one(
                {"template_id": entry.template_id},
                {"$setOnInsert": self._to_document(sanitized)},
                upsert=True,
            )
            migrated += int(result.upserted_id is not None)
        return migrated
