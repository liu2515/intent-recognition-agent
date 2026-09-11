"""通过 LangGraph interrupt 请求用户确认高风险字段。"""

from langgraph.types import interrupt

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.six_tuple import GoalStatus, IntentSixTuple
from intent_recognition_agent.hitl.answer_merger import parse_confirmation
from intent_recognition_agent.hitl.questions import build_confirmation_prompt


def confirm_with_user(state: IntentAgentState) -> IntentAgentState:
    value = IntentSixTuple.model_validate(state["six_tuple"])
    prompt = build_confirmation_prompt(value)
    answer = str(interrupt(prompt.model_dump(mode="json")))
    decision = parse_confirmation(answer)
    if decision is None:
        return {
            "status": "invalid",
            "validation_errors": ["未获得明确的确认或取消答复"],
            "user_feedback": answer,
            "hitl_question": prompt.question,
        }
    if not decision:
        value.goal.status = GoalStatus.CANCELLED
        return {
            "six_tuple": value.model_dump(mode="json"),
            "status": "cancelled",
            "confirmed": False,
            "confirmation_required": False,
            "user_feedback": answer,
            "hitl_question": prompt.question,
        }
    value.constraints.confirmation.confirmed = True
    value.constraints.confirmation.confirmation_text = answer
    return {
        "six_tuple": value.model_dump(mode="json"),
        "confirmed": True,
        "confirmation_required": False,
        "user_feedback": answer,
        "hitl_question": prompt.question,
        "status": "processing",
        "revision": int(state.get("revision", 0)) + 1,
    }
