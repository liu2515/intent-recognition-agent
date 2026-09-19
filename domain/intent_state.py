"""LangGraph意图识别运行状态模型。"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class IntentAgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    session_id: str
    thread_id: str
    original_input: str
    normalized_input: str
    user_feedback: str
    subject: dict[str, Any]
    knowledge_hits: list[dict[str, Any]]
    matched_template: dict[str, Any] | None
    knowledge_normalization: dict[str, Any] | None
    knowledge_coverage_decision: dict[str, Any] | None
    knowledge_coverage: str
    translation_mode: str
    six_tuple: dict[str, Any]
    evidence: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    missing_fields: list[str]
    ambiguous_fields: list[str]
    validation_errors: list[str]
    hitl_question: str
    confirmation_required: bool
    confirmed: bool
    status: str
    revision: int
    knowledge_candidate_id: str
    knowledge_writeback_status: str
    model_tool_rounds: int
