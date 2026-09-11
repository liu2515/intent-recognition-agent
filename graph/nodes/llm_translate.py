"""未命中知识时，由大模型生成六元组草稿。"""

from collections.abc import Callable

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.six_tuple import Subject
from intent_recognition_agent.llm.client import IntentTranslator


def create_llm_translate_node(
    translator: IntentTranslator,
) -> Callable[[IntentAgentState], IntentAgentState]:
    def llm_translate(state: IntentAgentState) -> IntentAgentState:
        draft = translator.translate(
            state["normalized_input"], Subject.model_validate(state["subject"])
        )
        draft.six_tuple.subject = Subject.model_validate(state["subject"])
        return {
            "translation_mode": "llm",
            "six_tuple": draft.six_tuple.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in draft.evidence],
            "hypotheses": [item.model_dump(mode="json") for item in draft.hypotheses],
            "missing_fields": draft.missing_fields,
            "ambiguous_fields": draft.ambiguous_fields,
        }

    return llm_translate
