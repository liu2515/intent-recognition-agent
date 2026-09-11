"""接收用户原始请求并初始化状态。"""

from intent_recognition_agent.domain.intent_state import IntentAgentState


def receive_request(state: IntentAgentState) -> IntentAgentState:
    text = (state.get("original_input") or "").strip()
    if not text:
        return {"status": "invalid", "validation_errors": ["用户请求不能为空"]}
    subject = dict(state.get("subject") or {})
    subject.setdefault("user_id", state.get("user_id"))
    return {
        "original_input": text,
        "subject": subject,
        "status": "processing",
        "revision": int(state.get("revision", 0)),
        "missing_fields": [],
        "ambiguous_fields": [],
        "validation_errors": [],
        "evidence": [],
        "hypotheses": [],
        "confirmed": False,
    }
