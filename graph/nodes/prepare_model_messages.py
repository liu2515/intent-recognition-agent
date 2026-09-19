"""准备模型推理所需消息。"""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from intent_recognition_agent.domain.intent_state import IntentAgentState


MODEL_SYSTEM_PROMPT = """你是中国移动意图研判智能体。
你的任务是收集生成六元组所需的可靠信息，而不是直接办理业务。
你可以按需调用已提供的只读工具，工具选择必须遵守最小查询原则：
1. 动作、业务对象或已有模板不明确时，调用 search_active_intent_knowledge 或 query_business_objects。
2. 套餐名称、金额、流量、合约期等产品规格不明确时，调用 query_product_options。
3. 立即/下月/指定日期生效等时间诉求需要规则校验时，调用 query_effective_time_policy。
4. 实名、授权、确认、资格和前置条件不明确时，调用 query_service_requirements 或 query_business_constraints。
5. 不要为同一问题重复调用工具；用户已经明确给出的金额、流量、时间等内容不可被工具结果覆盖。
6. 工具用于查询公共业务知识，不能补齐用户私有信息；不要调用工具猜测手机号、地址或用户授权。
7. 是否需要用户补充由后续六元组校验决定。本节点只判断是否需要工具，不要自行要求用户补充。
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
