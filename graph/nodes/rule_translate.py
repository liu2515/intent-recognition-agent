"""完全命中知识时，通过确定性规则生成六元组。"""

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.knowledge_models import KnowledgeMatch
from intent_recognition_agent.domain.six_tuple import Subject
from intent_recognition_agent.knowledge.rule_translator import translate_by_rule


def rule_translate(state: IntentAgentState) -> IntentAgentState:
    match = KnowledgeMatch.model_validate(state["matched_template"])
    value = translate_by_rule(match, Subject.model_validate(state["subject"]))
    return {
        "translation_mode": "rule",
        "six_tuple": value.model_dump(mode="json"),
        "evidence": [{
            "field_path": "six_tuple.action.name",
            "source": "knowledge",
            "knowledge_id": match.template.template_id,
            "confidence": 1.0,
        }],
    }
