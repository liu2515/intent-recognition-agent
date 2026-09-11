"""基于JSON文件的业务意图知识仓库。

这是本地原型实现。活动规则和待审核候选分文件保存，并使用原子替换避免
写入中断造成JSON损坏。后续可以保持相同接口切换到Neo4j或MongoDB。
"""

import json
import os
from pathlib import Path
from threading import RLock

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeStatus,
    KnowledgeTemplate,
    utc_now,
)


DATA_DIR = Path(__file__).resolve().parent / "data"


class KnowledgeNotFoundError(LookupError):
    pass


class DuplicateKnowledgeError(ValueError):
    pass


class KnowledgeRepository:
    """管理待审核知识和已经激活的规则模板。"""

    def __init__(
        self,
        active_path: Path | None = None,
        candidate_path: Path | None = None,
    ) -> None:
        self.active_path = active_path or DATA_DIR / "intent_templates.json"
        self.candidate_path = candidate_path or DATA_DIR / "knowledge_candidates.json"
        self._lock = RLock()
        self._ensure_document(self.active_path, "intent_templates")
        self._ensure_document(self.candidate_path, "knowledge_candidates")

    @staticmethod
    def _ensure_document(path: Path, key: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(
                json.dumps(
                    {"schema_version": "1.0", key: []},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    @staticmethod
    def _read(path: Path, key: str) -> list[KnowledgeTemplate]:
        document = json.loads(path.read_text(encoding="utf-8"))
        return [KnowledgeTemplate.model_validate(item) for item in document.get(key, [])]

    @staticmethod
    def _write(path: Path, key: str, entries: list[KnowledgeTemplate]) -> None:
        document = {
            "schema_version": "1.0",
            key: [entry.model_dump(mode="json") for entry in entries],
        }
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_path, path)

    def list_active(self) -> list[KnowledgeTemplate]:
        with self._lock:
            return self._read(self.active_path, "intent_templates")

    def list_candidates(
        self,
        status: KnowledgeStatus | None = None,
    ) -> list[KnowledgeTemplate]:
        with self._lock:
            entries = self._read(self.candidate_path, "knowledge_candidates")
        if status is None:
            return entries
        return [entry for entry in entries if entry.status == status]

    def add_candidate(self, candidate: KnowledgeTemplate) -> KnowledgeTemplate:
        with self._lock:
            all_entries = [*self.list_active(), *self.list_candidates()]
            duplicate = next(
                (
                    entry
                    for entry in all_entries
                    if entry.normalized_utterance == candidate.normalized_utterance
                    and entry.six_tuple.action.name == candidate.six_tuple.action.name
                    and entry.status != KnowledgeStatus.REJECTED
                ),
                None,
            )
            if duplicate is not None:
                raise DuplicateKnowledgeError(
                    f"相同表达和动作已经存在: {duplicate.template_id}"
                )

            candidates = self.list_candidates()
            candidates.append(candidate)
            self._write(self.candidate_path, "knowledge_candidates", candidates)
        return candidate

    def approve(self, template_id: str, reviewer: str) -> KnowledgeTemplate:
        with self._lock:
            candidates = self.list_candidates()
            selected = next(
                (entry for entry in candidates if entry.template_id == template_id),
                None,
            )
            if selected is None:
                raise KnowledgeNotFoundError(template_id)
            if selected.status != KnowledgeStatus.PENDING:
                raise ValueError("只有待审核知识可以被批准")

            approved = selected.model_copy(
                update={
                    "status": KnowledgeStatus.ACTIVE,
                    "reviewed_by": reviewer,
                    "reviewed_at": utc_now(),
                    "rejection_reason": None,
                },
                deep=True,
            )
            candidates = [
                entry for entry in candidates if entry.template_id != template_id
            ]
            active = self.list_active()
            active.append(approved)
            self._write(self.candidate_path, "knowledge_candidates", candidates)
            self._write(self.active_path, "intent_templates", active)
        return approved

    def reject(
        self,
        template_id: str,
        reviewer: str,
        reason: str,
    ) -> KnowledgeTemplate:
        with self._lock:
            candidates = self.list_candidates()
            index = next(
                (
                    position
                    for position, entry in enumerate(candidates)
                    if entry.template_id == template_id
                ),
                None,
            )
            if index is None:
                raise KnowledgeNotFoundError(template_id)
            if candidates[index].status != KnowledgeStatus.PENDING:
                raise ValueError("只有待审核知识可以被拒绝")

            rejected = candidates[index].model_copy(
                update={
                    "status": KnowledgeStatus.REJECTED,
                    "reviewed_by": reviewer,
                    "reviewed_at": utc_now(),
                    "rejection_reason": reason,
                },
                deep=True,
            )
            candidates[index] = rejected
            self._write(self.candidate_path, "knowledge_candidates", candidates)
        return rejected
