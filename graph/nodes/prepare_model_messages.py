"""准备模型推理所需消息。"""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from intent_recognition_agent.domain.intent_state import IntentAgentState


MODEL_SYSTEM_PROMPT = """你是中国移动意图研判智能体。
你的任务是收集生成六元组所需的可靠信息，而不是直接办理业务。
你可以按需调用已提供的只读工具查询业务对象、约束和已审核知识。
禁止编造工具结果，禁止产生写操作。信息充分后不要继续调用工具，明确表示可以进入结构化编译。
"""


def prepare_model_messages(state: IntentAgentState) -> IntentAgentState:
    context = {
        "用户请求": state["original_input"],
        "知识覆盖": state.get("knowledge_coverage", "missing"),
        "部分知识": state.get("matched_template"),
        "当前六元组": state.get("six_tuple"),
        "用户补充": state.get("user_feedback"),
        "缺失字段": state.get("missing_fields", []),
        "歧义字段": state.get("ambiguous_fields", []),
    }
    prompt = "请判断是否需要调用只读工具补充信息：\n" + json.dumps(
        context,
        ensure_ascii=False,
        default=str,
    )
    messages = [HumanMessage(content=prompt)]
    if not state.get("messages"):
        messages.insert(0, SystemMessage(content=MODEL_SYSTEM_PROMPT))
    return {"messages": messages, "model_tool_rounds": 0, "status": "processing"}
