"""从LangGraph检查点构造可视化执行轨迹。"""

from datetime import datetime, timezone
from typing import Any


TOOL_LABELS = {
    "search_active_intent_knowledge": "检索已审核知识",
    "query_business_objects": "查询业务对象",
    "query_business_constraints": "查询业务约束",
    "query_product_options": "查询产品选项",
    "query_effective_time_policy": "查询生效规则",
    "query_service_requirements": "查询办理条件",
}

NODE_DETAILS = {
    "receive_request": ("接收用户请求", "读取原始文本、用户身份和当前会话信息。"),
    "normalize_input": ("输入规范化", "清理输入格式，保留需要识别的业务表达和参数。"),
    "retrieve_knowledge": ("检索知识图谱", "查找与当前动作、对象和参数相关的已生效知识。"),
    "evaluate_knowledge": ("判断知识覆盖", "判断现有知识是完全命中、部分命中还是未命中。"),
    "rule_translate": ("规则识别", "使用命中的规则，并用本次请求参数覆盖规则槽位。"),
    "prepare_model_messages": ("准备模型消息", "组织用户原文、知识结果、缺失项和补充信息。"),
    "llm_decide_next": ("LLM 决定下一步", "模型判断是否调用工具，或直接生成结构化六元组。"),
    "readonly_tools": ("执行查询工具", "执行模型选择的只读业务查询工具，并返回查询结果。"),
    "compile_six_tuple": ("生成结构化六元组", "生成主体、动作、业务对象、上下文参数、约束和目标。"),
    "validate_tuple": ("六元组校验", "校验必填项、歧义、业务约束以及是否需要用户确认。"),
    "clarify_with_user": ("用户补充", "暂停流程，等待用户补齐缺失或存在歧义的信息。"),
    "confirm_with_user": ("用户确认", "等待用户确认需要授权或具有业务影响的请求。"),
    "finalize_tuple": ("最终定稿", "固化完成校验和确认后的六元组识别结果。"),
    "propose_knowledge_writeback": ("生成知识", "将确认后的识别结果写入可复用的活动知识。"),
    "__end__": ("流程结束", "保存识别结果和执行轨迹，结束当前任务。"),
}


def _timestamp(value: Any) -> str | None:
    """Return a timezone-aware ISO 8601 timestamp."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _duration_ms(started_at: Any, completed_at: Any) -> int | None:
    started = _parse_timestamp(started_at)
    completed = _parse_timestamp(completed_at)
    if started is None or completed is None:
        return None
    return max(0, round((completed - started).total_seconds() * 1000))


def _recent_tool_calls(snapshot: Any) -> list[dict[str, Any]]:
    """只提取当前模型轮次最新 AI 消息的 tool_calls。

    不能继续向前查找更早的 AI 消息，否则本轮没有调用工具时，会把上一轮
    的 tool_calls 错误地重复显示在执行轨迹中。
    """
    values = getattr(snapshot, "values", {}) or {}
    for message in reversed(values.get("messages", [])):
        message_type = getattr(message, "type", None)
        if message_type != "ai" and message.__class__.__name__ != "AIMessage":
            continue
        calls = getattr(message, "tool_calls", None) or []
        return [
            {
                "id": call.get("id"),
                "name": call.get("name", "unknown"),
                "label": TOOL_LABELS.get(call.get("name"), call.get("name", "unknown")),
                "args": call.get("args", {}),
            }
            for call in calls
        ]
    return []


def _recent_tool_results(snapshot: Any) -> list[dict[str, str]]:
    """提取 ToolNode 本轮返回的摘要，不把完整工具结果塞入轨迹。"""
    values = getattr(snapshot, "values", {}) or {}
    results: list[dict[str, str]] = []
    for message in reversed(values.get("messages", [])):
        name = getattr(message, "name", None)
        tool_call_id = getattr(message, "tool_call_id", None)
        if not name or not tool_call_id:
            if results:
                break
            continue
        content = str(getattr(message, "content", "")).replace("\n", " ")
        results.append(
            {
                "tool_call_id": tool_call_id,
                "name": name,
                "label": TOOL_LABELS.get(name, name),
                "summary": content[:120] + ("…" if len(content) > 120 else ""),
            }
        )
    return list(reversed(results))


def build_execution_trace(graph: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        snapshots = list(reversed(list(graph.get_state_history(config))))
    except Exception:
        return events
    run_started_at = snapshots[0].created_at if snapshots else None
    for index in range(1, len(snapshots)):
        previous = snapshots[index - 1]
        snapshot = snapshots[index]
        metadata = dict(snapshot.metadata or {})
        nodes = [node for node in previous.next if node != "__start__"]
        for node in nodes:
            title, summary = NODE_DETAILS.get(node, (node, "执行当前工作流节点。"))
            started_at = _timestamp(previous.created_at)
            completed_at = _timestamp(snapshot.created_at)
            event = {
                "sequence": len(events) + 1,
                "node": node,
                "title": title,
                "summary": summary,
                "step": metadata.get("step"),
                "source": metadata.get("source"),
                "created_at": completed_at,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_ms": _duration_ms(previous.created_at, snapshot.created_at),
                "elapsed_ms": _duration_ms(run_started_at, snapshot.created_at),
                "next": list(snapshot.next),
            }
            if node == "llm_decide_next":
                tool_calls = _recent_tool_calls(snapshot)
                event["tool_calls"] = tool_calls
                event["summary"] = (
                    "模型决定调用：" + "、".join(call["label"] for call in tool_calls)
                    if tool_calls
                    else "模型决定：当前信息充分，进入六元组编译"
                )
            elif node == "readonly_tools":
                tool_results = _recent_tool_results(snapshot)
                event["tool_results"] = tool_results
                event["summary"] = (
                    "ToolNode 已执行：" + "、".join(result["label"] for result in tool_results)
                    if tool_results
                    else "ToolNode 执行只读查询"
                )
            events.append(event)
    return events
