"""知识覆盖与HITL条件分支。"""

from langchain_core.messages import AIMessage

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.validation import TupleValidationResult
from intent_recognition_agent.hitl.policy import next_human_action


def route_by_knowledge(state: IntentAgentState) -> str:
    return (
        "rule_translate"
        if state.get("knowledge_coverage") == "complete"
        else "prepare_model_messages"
    )


def route_after_model_decision(state: IntentAgentState) -> str:
    """最多执行三轮只读工具，避免模型无限循环。"""

    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    tool_calls = last_message.tool_calls if isinstance(last_message, AIMessage) else []
    if tool_calls and int(state.get("model_tool_rounds", 0)) <= 3:
        return "readonly_tools"
    return "compile_six_tuple"


def route_after_validation(state: IntentAgentState) -> str:
    if state.get("status") == "invalid":
        return "invalid"
    result = TupleValidationResult(
        valid=False,
        missing_fields=state.get("missing_fields", []),
        ambiguous_fields=state.get("ambiguous_fields", []),
        errors=state.get("validation_errors", []),
        confirmation_required=bool(state.get("confirmation_required")),
    )
    return next_human_action(result)


def route_after_confirmation(state: IntentAgentState) -> str:
    return "finalize" if state.get("confirmed") else "end"
