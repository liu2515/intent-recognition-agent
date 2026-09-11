"""计算知识覆盖情况并选择后续转译路径。"""

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.knowledge_models import KnowledgeMatch
from intent_recognition_agent.knowledge.coverage import evaluate_coverage


def evaluate_knowledge(state: IntentAgentState) -> IntentAgentState:
    raw = state.get("matched_template")
    match = KnowledgeMatch.model_validate(raw) if raw else None
    return {"knowledge_coverage": evaluate_coverage(match).value}
