"""生成最终标准化六元组。"""

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.six_tuple import IntentSixTuple


def finalize_tuple(state: IntentAgentState) -> IntentAgentState:
    value = IntentSixTuple.model_validate(state["six_tuple"])
    return {
        "six_tuple": value.model_dump(mode="json", exclude_none=True),
        "status": "completed",
        "missing_fields": [],
        "ambiguous_fields": [],
        "validation_errors": [],
    }
