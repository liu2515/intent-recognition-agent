"""检查六元组完整性、歧义和业务约束。"""

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.six_tuple import IntentSixTuple
from intent_recognition_agent.domain.validation import validate_six_tuple


def validate_tuple(state: IntentAgentState) -> IntentAgentState:
    try:
        value = IntentSixTuple.model_validate(state["six_tuple"])
    except Exception as exc:
        return {"status": "invalid", "validation_errors": [f"六元组结构无效: {exc}"]}
    result = validate_six_tuple(
        value,
        inherited_missing=state.get("missing_fields"),
        inherited_ambiguous=state.get("ambiguous_fields"),
    )
    return {
        "six_tuple": value.model_dump(mode="json"),
        "missing_fields": result.missing_fields,
        "ambiguous_fields": result.ambiguous_fields,
        "validation_errors": result.errors,
        "confirmation_required": result.confirmation_required,
        "confirmed": value.constraints.confirmation.confirmed,
    }
