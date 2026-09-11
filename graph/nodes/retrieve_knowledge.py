"""查询与当前用户需求有关的业务意图知识。"""

from collections.abc import Callable

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.knowledge.matcher import match_knowledge
from intent_recognition_agent.knowledge.repository import KnowledgeRepository


def create_retrieve_knowledge_node(
    repository: KnowledgeRepository,
) -> Callable[[IntentAgentState], IntentAgentState]:
    def retrieve_knowledge(state: IntentAgentState) -> IntentAgentState:
        match = match_knowledge(state["normalized_input"], repository.list_active())
        return {
            "matched_template": match.model_dump(mode="json") if match else None,
            "knowledge_hits": [match.model_dump(mode="json")] if match else [],
        }

    return retrieve_knowledge
