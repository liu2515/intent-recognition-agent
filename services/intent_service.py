"""启动、恢复和读取意图识别任务。"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import RLock
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
    IntentTaskDraft,
    IntentTaskResult,
    TaskStatus,
    TranslationMode,
)
from intent_recognition_agent.graph.builder import build_intent_graph
from intent_recognition_agent.hitl.interrupt_handler import extract_interrupt_payload
from intent_recognition_agent.knowledge.repository import KnowledgeRepository
from intent_recognition_agent.llm.client import IntentTranslator, ResilientIntentTranslator
from intent_recognition_agent.persistence.checkpointer import create_checkpointer
from intent_recognition_agent.persistence.intent_repository import (
    IntentRepository,
    IntentTaskNotFoundError,
)
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
        self._live_threads: dict[str, str] = {}
        self._live_child_threads: dict[str, dict[str, str]] = {}
        self._live_threads_lock = RLock()
        self.translator = translator or ResilientIntentTranslator()
        self.graph = build_intent_graph(
            repository=self.knowledge,
            translator=self.translator,
            checkpointer=checkpointer or create_checkpointer(),
            graph_store=self.graph_store,
        )

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def _register_live_thread(self, thread_id: str, user_id: str) -> None:
        with self._live_threads_lock:
            self._live_threads[thread_id] = user_id

    def _finish_live_thread(self, thread_id: str) -> None:
        with self._live_threads_lock:
            self._live_threads.pop(thread_id, None)
            self._live_child_threads.pop(thread_id, None)

    def is_live_thread(self, thread_id: str) -> bool:
        with self._live_threads_lock:
            return thread_id in self._live_threads

    def live_trace(self, *, thread_id: str, user_id: str) -> list[dict[str, Any]]:
        """Return checkpoints written so far, without exposing another user's run."""
        with self._live_threads_lock:
            owner = self._live_threads.get(thread_id)
        if owner is not None:
            if owner != user_id:
                raise PermissionError("Trace ownership mismatch")
            events = build_execution_trace(self.graph, self._config(thread_id))
            with self._live_threads_lock:
                child_threads = dict(self._live_child_threads.get(thread_id, {}))
            for child_thread_id, task_id in child_threads.items():
                events.extend(
                    {
                        **event,
                        "task_id": task_id,
                    }
                    for event in build_execution_trace(self.graph, self._config(child_thread_id))
                )
            events.sort(key=lambda item: item.get("created_at") or "")
            for sequence, event in enumerate(events, 1):
                event["sequence"] = sequence
            return events

        stored = self.intents.get(thread_id, user_id)
        return list(stored.get("trace") or self.traces.get(thread_id, user_id=user_id))

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

    @staticmethod
    def _looks_multi_intent(text: str) -> bool:
        """在明显的多动作请求上才增加一次计划识别，避免普通请求变慢。"""
        normalized = re.sub(r"\s+", "", text)
        separators = ("\u7136\u540E", "\u63A5\u7740", "\u4E4B\u540E", "\u540C\u65F6", "\u5E76\u4E14", "\u53E6\u5916", "\u987A\u4FBF", "\u4EE5\u53CA", "\uFF1B", ";")
        if any(token in normalized for token in separators):
            return True
        if re.search(r"\u5E76(?=(?:\u529E\u7406|\u5F00\u901A|\u67E5\u8BE2|\u6CE8\u9500|\u9500\u53F7|\u9500\u6237|\u6D88\u9664|\u53D6\u6D88|\u9000\u8BA2|\u66F4\u6362|\u4FEE\u6539|\u5145\u503C))", normalized):
            return True
        verbs = ("\u529E\u7406", "\u5F00\u901A", "\u67E5\u8BE2", "\u6CE8\u9500", "\u9500\u53F7", "\u9500\u6237", "\u6D88\u9664", "\u53D6\u6D88", "\u9000\u8BA2", "\u66F4\u6362", "\u4FEE\u6539", "\u5145\u503C")
        return sum(normalized.count(verb) for verb in verbs) >= 2

    def _run_task(
        self,
        parent_thread_id: str,
        task: IntentTaskDraft,
        user_id: str,
        subject: Subject,
    ) -> IntentTaskResult:
        """在隔离 checkpoint 线程中运行一个任务；多个任务可安全并发识别。"""
        child_thread_id = f"{parent_thread_id}:task:{task.task_id}"
        with self._live_threads_lock:
            self._live_child_threads.setdefault(parent_thread_id, {})[child_thread_id] = task.task_id
        raw = self.graph.invoke(
            {
                "user_id": user_id,
                "session_id": child_thread_id,
                "thread_id": child_thread_id,
                "original_input": task.text,
                "subject": subject.model_dump(mode="json"),
            },
            self._config(child_thread_id),
        )
        response = self._serialize(raw, thread_id=child_thread_id, user_id=user_id)
        task_trace = build_execution_trace(self.graph, self._config(child_thread_id))
        result = response["result"]
        return IntentTaskResult(
            task_id=task.task_id,
            sequence=task.sequence,
            text=task.text,
            action_hint=task.action_hint,
            depends_on=task.depends_on,
            status=TaskStatus(result["status"]),
            thread_id=child_thread_id,
            six_tuple=IntentSixTuple.model_validate(result["six_tuple"]) if result.get("six_tuple") else None,
            evidence=result.get("evidence", []),
            hypotheses=result.get("hypotheses", []),
            missing_fields=result.get("missing_fields", []),
            ambiguous_fields=result.get("ambiguous_fields", []),
            validation_errors=result.get("validation_errors", []),
            hitl_question=(response.get("interrupt") or {}).get("question") or result.get("hitl_question"),
            trace=task_trace,
        )

    def _serialize_multi(
        self,
        *,
        thread_id: str,
        user_id: str,
        original_input: str,
        subject: Subject,
        tasks: list[IntentTaskResult],
        revision: int = 0,
    ) -> dict[str, Any]:
        ordered = sorted(tasks, key=lambda item: item.sequence)
        active = next(
            (item for item in ordered if item.status in {TaskStatus.NEEDS_CLARIFICATION, TaskStatus.REQUIRES_CONFIRMATION}),
            ordered[0] if ordered else None,
        )
        if any(item.status == TaskStatus.NEEDS_CLARIFICATION for item in ordered):
            status = IntentStatus.NEEDS_CLARIFICATION
        elif any(item.status == TaskStatus.REQUIRES_CONFIRMATION for item in ordered):
            status = IntentStatus.REQUIRES_CONFIRMATION
        elif all(item.status == TaskStatus.COMPLETED for item in ordered):
            status = IntentStatus.COMPLETED
        elif any(item.status == TaskStatus.INVALID for item in ordered):
            status = IntentStatus.INVALID
        else:
            status = IntentStatus.PROCESSING
        result = IntentRecognitionResult(
            thread_id=thread_id,
            user_id=user_id,
            original_input=original_input,
            normalized_input=original_input,
            status=status,
            six_tuple=active.six_tuple if active else None,
            evidence=active.evidence if active else [],
            hypotheses=active.hypotheses if active else [],
            missing_fields=active.missing_fields if active else [],
            ambiguous_fields=active.ambiguous_fields if active else [],
            validation_errors=active.validation_errors if active else [],
            hitl_question=active.hitl_question if active else None,
            plan_id=thread_id,
            is_multi_intent=True,
            tasks=ordered,
            revision=revision,
        )
        interrupt = None
        if active and active.status in {TaskStatus.NEEDS_CLARIFICATION, TaskStatus.REQUIRES_CONFIRMATION}:
            interrupt = {
                "kind": "confirmation" if active.status == TaskStatus.REQUIRES_CONFIRMATION else "clarification",
                "question": active.hitl_question,
                "task_id": active.task_id,
                "fields": active.missing_fields + active.ambiguous_fields,
            }
        trace = []
        for item in ordered:
            trace.extend(
                [{**event, "task_id": item.task_id} for event in item.trace]
            )
        return {"result": result.model_dump(mode="json"), "interrupt": interrupt, "trace": trace}

    def _start_multi(
        self,
        *,
        thread_id: str,
        text: str,
        user_id: str,
        subject: Subject,
    ) -> dict[str, Any]:
        decompose = getattr(self.translator, "decompose", None)
        if decompose is None:
            return {}
        plan = decompose(text, subject)
        if len(plan.tasks) <= 1:
            return {}
        tasks: list[IntentTaskResult] = []
        max_workers = min(3, len(plan.tasks))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="intent-task") as executor:
            futures = {
                executor.submit(self._run_task, thread_id, task, user_id, subject): task
                for task in plan.tasks
            }
            for future in as_completed(futures):
                task = futures[future]
                try:
                    tasks.append(future.result())
                except Exception as exc:
                    logger.exception("多任务 %s 处理失败", task.task_id)
                    tasks.append(
                        IntentTaskResult(
                            task_id=task.task_id,
                            sequence=task.sequence,
                            text=task.text,
                            action_hint=task.action_hint,
                            depends_on=task.depends_on,
                            status=TaskStatus.INVALID,
                            validation_errors=[f"任务处理失败：{exc}"],
                        )
                    )
        if self.graph_store is not None:
            for task in tasks:
                if task.status != TaskStatus.COMPLETED or task.six_tuple is None:
                    continue
                try:
                    self.graph_store.upsert_runtime_intent(
                        thread_id=task.thread_id or f"{thread_id}:task:{task.task_id}",
                        user_id=user_id,
                        six_tuple=task.six_tuple,
                    )
                except Exception:
                    logger.exception("多任务实例 %s 同步到 Neo4j 失败", task.task_id)
        response = self._serialize_multi(
            thread_id=thread_id,
            user_id=user_id,
            original_input=text,
            subject=subject,
            tasks=tasks,
        )
        self.intents.save(thread_id, user_id, response)
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
        self._register_live_thread(thread_id, user_id)
        try:
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
            if self._looks_multi_intent(text):
                multi_response = self._start_multi(
                    thread_id=thread_id,
                    text=text,
                    user_id=user_id,
                    subject=current_subject,
                )
                if multi_response:
                    return multi_response
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
        finally:
            self._finish_live_thread(thread_id)

    def resume(self, *, thread_id: str, user_id: str, answer: str) -> dict[str, Any]:
        stored = self.intents.get(thread_id, user_id)
        stored_result = stored.get("result") or {}
        if stored_result.get("is_multi_intent") and stored_result.get("tasks"):
            tasks = [IntentTaskResult.model_validate(item) for item in stored_result["tasks"]]
            interrupt = stored.get("interrupt") or {}
            active_id = interrupt.get("task_id")
            active = next(
                (item for item in tasks if item.task_id == active_id),
                next((item for item in tasks if item.status in {TaskStatus.NEEDS_CLARIFICATION, TaskStatus.REQUIRES_CONFIRMATION}), None),
            )
            if active is None or not active.thread_id:
                return stored
            raw = self.graph.invoke(Command(resume=answer), self._config(active.thread_id))
            child_response = self._serialize(raw, thread_id=active.thread_id, user_id=user_id)
            updated = IntentTaskResult(
                **{
                    **active.model_dump(mode="json"),
                    "status": child_response["result"]["status"],
                    "six_tuple": child_response["result"].get("six_tuple"),
                    "evidence": child_response["result"].get("evidence", []),
                    "hypotheses": child_response["result"].get("hypotheses", []),
                    "missing_fields": child_response["result"].get("missing_fields", []),
                    "ambiguous_fields": child_response["result"].get("ambiguous_fields", []),
                    "validation_errors": child_response["result"].get("validation_errors", []),
                    "hitl_question": (child_response.get("interrupt") or {}).get("question"),
                    "trace": build_execution_trace(self.graph, self._config(active.thread_id)),
                }
            )
            tasks = [updated if item.task_id == active.task_id else item for item in tasks]
            subject_data = (updated.six_tuple.subject.model_dump(mode="json") if updated.six_tuple else {"user_id": user_id})
            response = self._serialize_multi(
                thread_id=thread_id,
                user_id=user_id,
                original_input=stored_result.get("original_input", ""),
                subject=Subject.model_validate(subject_data),
                tasks=tasks,
                revision=int(stored_result.get("revision", 0)) + 1,
            )
            self.intents.save(thread_id, user_id, response)
            return response

        raw = self.graph.invoke(Command(resume=answer), self._config(thread_id))
        return self._save_result(thread_id, user_id, raw)

    def get(self, *, thread_id: str, user_id: str) -> dict[str, Any]:
        return self.intents.get(thread_id, user_id)

    def export_six_tuple(
        self,
        *,
        thread_id: str,
        user_id: str,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Return only one JSON-compatible six-tuple, without trace metadata."""
        stored = self.intents.get(thread_id, user_id)
        result = stored.get("result") or {}
        six_tuple = result.get("six_tuple")

        if task_id is not None:
            task = next(
                (item for item in result.get("tasks", []) if item.get("task_id") == task_id),
                None,
            )
            if task is None:
                raise IntentTaskNotFoundError(task_id)
            six_tuple = task.get("six_tuple")

        if not six_tuple:
            raise ValueError("当前任务尚未生成六元组，无法输出 JSON")
        return IntentSixTuple.model_validate(six_tuple).model_dump(mode="json")
