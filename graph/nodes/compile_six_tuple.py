"""结合用户原文、补充回答和只读工具结果编译六元组。"""

from collections.abc import Callable

from langchain_core.messages import ToolMessage

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.domain.knowledge_models import KnowledgeMatch
from intent_recognition_agent.domain.six_tuple import IntentSixTuple, Subject
from intent_recognition_agent.llm.client import IntentTranslator


def _tool_context(state: IntentAgentState) -> str:
    values = [
        str(message.content)
        for message in state.get("messages", [])
        if isinstance(message, ToolMessage)
    ]
    return "\n".join(values[-6:])


def create_compile_six_tuple_node(
    translator: IntentTranslator,
) -> Callable[[IntentAgentState], IntentAgentState]:
    def compile_six_tuple(state: IntentAgentState) -> IntentAgentState:
        raw_match = state.get("matched_template")
        match = KnowledgeMatch.model_validate(raw_match) if raw_match else None
        subject = Subject.model_validate(state["subject"])
        tool_context = _tool_context(state)
        feedback = state.get("user_feedback")

        if feedback and state.get("six_tuple"):
            combined_feedback = feedback
            if tool_context:
                combined_feedback += f"\n只读工具返回：{tool_context}"
            draft = translator.refine(
                state["original_input"],
                subject,
                IntentSixTuple.model_validate(state["six_tuple"]),
                combined_feedback,
                match,
            )
        else:
            translate_with_context = getattr(translator, "translate_with_context", None)
            if translate_with_context is not None:
                draft = translate_with_context(
                    state["original_input"], subject, tool_context, match
                )
            else:
                draft = translator.translate(state["original_input"], subject, match)

        # 主体来自登录用户/请求上下文，是运行时事实，不能由模型的结构化输出覆盖。
        # 模型只负责识别动作、对象、参数、约束和目标。
        draft.six_tuple.subject = subject

        evidence = [item.model_dump(mode="json") for item in draft.evidence]
        if match is not None:
            evidence.append(
                {
                    "field_path": "six_tuple.action.name",
                    "source": "knowledge",
                    "knowledge_id": match.template.template_id,
                    "confidence": 0.75,
                }
            )
        return {
            "translation_mode": (
                "hybrid" if state.get("knowledge_coverage") == "partial" else "llm"
            ),
            "six_tuple": draft.six_tuple.model_dump(mode="json"),
            "evidence": evidence,
            "hypotheses": [item.model_dump(mode="json") for item in draft.hypotheses],
            "missing_fields": draft.missing_fields,
            "ambiguous_fields": draft.ambiguous_fields,
            "status": "processing",
        }

    return compile_six_tuple
