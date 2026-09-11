"""通过 LangGraph interrupt 请求用户补充信息。"""

from langgraph.types import interrupt

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.hitl.answer_merger import merge_clarification_answer
from intent_recognition_agent.hitl.questions import build_clarification_prompt


def clarify_with_user(state: IntentAgentState) -> IntentAgentState:
    """只收集用户回答；回答重新进入模型消息准备与工具循环。"""

    prompt = build_clarification_prompt(
        state.get("missing_fields", []), state.get("ambiguous_fields", [])
    )
    answer = interrupt(prompt.model_dump(mode="json"))
    return {
        "user_feedback": str(answer),
        "subject": merge_clarification_answer(
            dict(state.get("subject") or {}),
            str(answer),
            prompt.fields,
        ),
        "hitl_question": prompt.question,
        "status": "processing",
        "revision": int(state.get("revision", 0)) + 1,
    }
