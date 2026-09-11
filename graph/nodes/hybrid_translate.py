"""部分命中知识时，在知识约束下由大模型补全六元组。"""

from collections.abc import Callable

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.knowledge_models import KnowledgeMatch
from intent_recognition_agent.domain.six_tuple import Subject
from intent_recognition_agent.llm.client import IntentTranslator


def create_hybrid_translate_node(
    translator: IntentTranslator,
) -> Callable[[IntentAgentState], IntentAgentState]:
    def hybrid_translate(state: IntentAgentState) -> IntentAgentState:
        match = KnowledgeMatch.model_validate(state["matched_template"])
        draft = translator.translate(
            state["normalized_input"], Subject.model_validate(state["subject"]), match
        )
        draft.six_tuple.subject = Subject.model_validate(state["subject"])
        evidence = [item.model_dump(mode="json") for item in draft.evidence]
        evidence.append({
            "field_path": "six_tuple.action.name",
            "source": "knowledge",
            "knowledge_id": match.template.template_id,
            "confidence": 0.75,
        })
        return {
            "translation_mode": "hybrid",
            "six_tuple": draft.six_tuple.model_dump(mode="json"),
            "evidence": evidence,
            "hypotheses": [item.model_dump(mode="json") for item in draft.hypotheses],
            "missing_fields": draft.missing_fields,
            "ambiguous_fields": draft.ambiguous_fields,
        }

    return hybrid_translate
