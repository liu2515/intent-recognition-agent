"""启动、恢复和读取意图识别任务。"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from intent_recognition_agent.config.demo_users import get_demo_user
from intent_recognition_agent.domain.six_tuple import IntentSixTuple, Subject
from intent_recognition_agent.domain.translation_models import (
    EvidenceItem,
    IntentHypothesis,
    IntentRecognitionResult,
    IntentStatus,
    TranslationMode,
)
from intent_recognition_agent.graph.builder import build_intent_graph
from intent_recognition_agent.hitl.interrupt_handler import extract_interrupt_payload
from intent_recognition_agent.knowledge.repository import KnowledgeRepository
from intent_recognition_agent.llm.client import IntentTranslator
from intent_recognition_agent.persistence.checkpointer import create_checkpointer
from intent_recognition_agent.persistence.intent_repository import IntentRepository
from intent_recognition_agent.persistence.trace_repository import TraceRepository
from intent_recognition_agent.services.build_trace_service import build_execution_trace


logger = logging.getLogger(__name__)


class IntentService:
    """封装LangGraph调用，确保thread_id与user_id所有权隔离。"""

    def __init__(
        self,
        *,
        repository: KnowledgeRepository | None = None,
        translator: IntentTranslator | None = None,
        intents: IntentRepository | None = None,
        traces: TraceRepository | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
        graph_store: Any | None = None,
    ) -> None:
        self.knowledge = repository or KnowledgeRepository()
        self.intents = intents or IntentRepository()
        self.traces = traces or TraceRepository()
        self.graph_store = graph_store
        self.graph = build_intent_graph(
            repository=self.knowledge,
            translator=translator,
            checkpointer=checkpointer or create_checkpointer(),
        )

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def _serialize(
        self,
        state: dict[str, Any],
        *,
        thread_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        interrupt_payload = extract_interrupt_payload(state)
        status_value = state.get("status", "processing")
        if interrupt_payload:
            kind = interrupt_payload.get("kind")
            status_value = (
                IntentStatus.REQUIRES_CONFIRMATION.value
                if kind == "confirmation"
                else IntentStatus.NEEDS_CLARIFICATION.value
            )
        status = IntentStatus(status_value)
        match = state.get("matched_template") or {}
        template = match.get("template") or {}
        result = IntentRecognitionResult(
            thread_id=thread_id,
            user_id=user_id,
            original_input=state.get("original_input", ""),
            normalized_input=state.get("normalized_input", state.get("original_input", "")),
            status=status,
            translation_mode=TranslationMode(state["translation_mode"]) if state.get("translation_mode") else None,
            six_tuple=IntentSixTuple.model_validate(state["six_tuple"]) if state.get("six_tuple") else None,
            evidence=[EvidenceItem.model_validate(item) for item in state.get("evidence", [])],
            hypotheses=[IntentHypothesis.model_validate(item) for item in state.get("hypotheses", [])],
            missing_fields=state.get("missing_fields", []),
            ambiguous_fields=state.get("ambiguous_fields", []),
            validation_errors=state.get("validation_errors", []),
            hitl_question=(interrupt_payload or {}).get("question") or state.get("hitl_question"),
            knowledge_coverage=state.get("knowledge_coverage"),
            matched_template_id=template.get("template_id"),
            revision=int(state.get("revision", 0)),
            knowledge_candidate_id=state.get("knowledge_candidate_id"),
            knowledge_writeback_status=state.get("knowledge_writeback_status"),
        )
        return {
            "result": result.model_dump(mode="json"),
            "interrupt": interrupt_payload,
        }

    def _save_result(self, thread_id: str, user_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        response = self._serialize(raw, thread_id=thread_id, user_id=user_id)
        config = self._config(thread_id)
        self.traces.replace(
            thread_id,
            build_execution_trace(self.graph, config),
            user_id=user_id,
        )
        response["trace"] = self.traces.get(thread_id)
        self.intents.save(thread_id, user_id, response)
        result = response.get("result") or {}
        if (
            self.graph_store is not None
            and result.get("status") == IntentStatus.COMPLETED.value
            and result.get("six_tuple")
        ):
            try:
                self.graph_store.upsert_runtime_intent(
                    thread_id=thread_id,
                    user_id=user_id,
                    six_tuple=IntentSixTuple.model_validate(result["six_tuple"]),
                )
            except Exception:
                logger.exception("意图结果已保存，但实名主体实例同步到 Neo4j 失败")
        return response

    def start(
        self,
        *,
        text: str,
        user_id: str,
        thread_id: str | None = None,
        session_id: str | None = None,
        subject: Subject | None = None,
    ) -> dict[str, Any]:
        thread_id = thread_id or f"intent-{uuid4().hex}"
        profile = get_demo_user(user_id)
        current_subject = subject or Subject(
            user_id=user_id,
            username=(profile or {}).get("username"),
        )
        if current_subject.user_id and current_subject.user_id != user_id:
            raise PermissionError("请求主体与当前用户不一致")
        current_subject.user_id = user_id
        if not current_subject.username and profile is not None:
            current_subject.username = profile["username"]
        raw = self.graph.invoke(
            {
                "user_id": user_id,
                "session_id": session_id or thread_id,
                "thread_id": thread_id,
                "original_input": text,
                "subject": current_subject.model_dump(mode="json"),
            },
            self._config(thread_id),
        )
        return self._save_result(thread_id, user_id, raw)

    def resume(self, *, thread_id: str, user_id: str, answer: str) -> dict[str, Any]:
        self.intents.get(thread_id, user_id)
        raw = self.graph.invoke(Command(resume=answer), self._config(thread_id))
        return self._save_result(thread_id, user_id, raw)

    def get(self, *, thread_id: str, user_id: str) -> dict[str, Any]:
        return self.intents.get(thread_id, user_id)
