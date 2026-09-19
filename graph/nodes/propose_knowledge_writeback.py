"""将完成且经过确认的大模型转译结果直接激活为知识。"""

from collections.abc import Callable

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.six_tuple import IntentSixTuple
from intent_recognition_agent.knowledge.repository import DuplicateKnowledgeError
from intent_recognition_agent.knowledge.writeback import KnowledgeWritebackService


def create_propose_knowledge_writeback_node(
    service: KnowledgeWritebackService,
) -> Callable[[IntentAgentState], IntentAgentState]:
    def propose_knowledge_writeback(state: IntentAgentState) -> IntentAgentState:
        if state.get("translation_mode") not in {"llm", "hybrid"}:
            return {"knowledge_writeback_status": "skipped_rule_translation"}
        if state.get("status") != "completed":
            return {"knowledge_writeback_status": "skipped_not_completed"}
        if state.get("confirmation_required") and not state.get("confirmed"):
            return {"knowledge_writeback_status": "skipped_not_confirmed"}

        try:
            knowledge = service.activate_confirmed(
                utterance=state["original_input"],
                six_tuple=IntentSixTuple.model_validate(state["six_tuple"]),
                confirmed_by=state["user_id"],
            )
        except DuplicateKnowledgeError:
            return {"knowledge_writeback_status": "duplicate"}

        return {
            "knowledge_candidate_id": knowledge.template_id,
            "knowledge_writeback_status": "active",
        }

    return propose_knowledge_writeback
