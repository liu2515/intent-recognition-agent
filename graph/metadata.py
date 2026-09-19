"""运行图节点名称、说明和可视化元数据。"""

NODE_METADATA = [
    {"id": "receive_request", "label": "接收用户请求", "kind": "input"},
    {"id": "normalize_input", "label": "输入规范化", "kind": "processing"},
    {"id": "retrieve_knowledge", "label": "检索知识图谱", "kind": "knowledge"},
    {"id": "evaluate_knowledge", "label": "判断知识覆盖", "kind": "decision"},
    {"id": "rule_translate", "label": "规则识别", "kind": "rule"},
    {"id": "prepare_model_messages", "label": "准备模型消息", "kind": "model"},
    {"id": "llm_decide_next", "label": "LLM 决定下一步", "kind": "decision"},
    {"id": "readonly_tools", "label": "ToolNode 执行只读工具", "kind": "tool"},
    {"id": "compile_six_tuple", "label": "结构化编译六元组", "kind": "model"},
    {"id": "validate_tuple", "label": "六元组校验", "kind": "validation"},
    {"id": "clarify_with_user", "label": "用户补充", "kind": "human"},
    {"id": "confirm_with_user", "label": "用户确认", "kind": "human"},
    {"id": "finalize_tuple", "label": "最终定稿", "kind": "output"},
    {"id": "propose_knowledge_writeback", "label": "确认并激活知识", "kind": "knowledge"},
    {"id": "__end__", "label": "END", "kind": "end"},
]

EDGE_METADATA = [
    {"source": "receive_request", "target": "normalize_input"},
    {"source": "normalize_input", "target": "retrieve_knowledge"},
    {"source": "retrieve_knowledge", "target": "evaluate_knowledge"},
    {"source": "evaluate_knowledge", "target": "rule_translate", "label": "完全命中"},
    {"source": "evaluate_knowledge", "target": "prepare_model_messages", "label": "部分或未命中"},
    {"source": "rule_translate", "target": "validate_tuple"},
    {"source": "prepare_model_messages", "target": "llm_decide_next"},
    {"source": "llm_decide_next", "target": "readonly_tools", "label": "产生 tool_calls"},
    {"source": "readonly_tools", "target": "llm_decide_next", "label": "工具结果"},
    {"source": "llm_decide_next", "target": "compile_six_tuple", "label": "不再调用工具"},
    {"source": "compile_six_tuple", "target": "validate_tuple"},
    {"source": "validate_tuple", "target": "clarify_with_user", "label": "缺失或歧义"},
    {"source": "clarify_with_user", "target": "prepare_model_messages", "label": "用户补充"},
    {"source": "validate_tuple", "target": "confirm_with_user", "label": "需要确认"},
    {"source": "validate_tuple", "target": "finalize_tuple", "label": "通过"},
    {"source": "validate_tuple", "target": "__end__", "label": "无效"},
    {"source": "confirm_with_user", "target": "finalize_tuple", "label": "确认"},
    {"source": "confirm_with_user", "target": "__end__", "label": "取消"},
    {"source": "finalize_tuple", "target": "propose_knowledge_writeback"},
    {"source": "propose_knowledge_writeback", "target": "__end__"},
]


def graph_metadata() -> dict[str, list[dict[str, str]]]:
    return {"nodes": NODE_METADATA, "edges": EDGE_METADATA}
