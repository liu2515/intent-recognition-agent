"""显式注册节点、边并编译意图识别 StateGraph。"""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.graph.nodes.clarify_with_user import clarify_with_user
from intent_recognition_agent.graph.nodes.compile_six_tuple import create_compile_six_tuple_node
from intent_recognition_agent.graph.nodes.confirm_with_user import confirm_with_user
from intent_recognition_agent.graph.nodes.evaluate_knowledge import evaluate_knowledge
from intent_recognition_agent.graph.nodes.finalize_tuple import finalize_tuple
from intent_recognition_agent.graph.nodes.llm_decide_next import create_llm_decide_next_node
from intent_recognition_agent.graph.nodes.normalize_input import normalize_input
from intent_recognition_agent.graph.nodes.prepare_model_messages import prepare_model_messages
from intent_recognition_agent.graph.nodes.propose_knowledge_writeback import create_propose_knowledge_writeback_node
from intent_recognition_agent.graph.nodes.receive_request import receive_request
from intent_recognition_agent.graph.nodes.retrieve_knowledge import create_retrieve_knowledge_node
from intent_recognition_agent.graph.nodes.rule_translate import rule_translate
from intent_recognition_agent.graph.nodes.validate_tuple import validate_tuple
from intent_recognition_agent.graph.routing import (
    route_after_confirmation,
    route_after_model_decision,
    route_after_validation,
    route_by_knowledge,
)
from intent_recognition_agent.knowledge.repository import KnowledgeRepository
from intent_recognition_agent.knowledge.writeback import KnowledgeWritebackService
from intent_recognition_agent.llm.client import IntentTranslator, ResilientIntentTranslator
from intent_recognition_agent.tools.read_only_tools import create_read_only_tools


def build_intent_graph(
    *,
    repository: KnowledgeRepository | None = None,
    translator: IntentTranslator | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    graph_store: Any | None = None,
):
    """构建可注入知识库、模型和Checkpointer的意图识别图。"""

    repository = repository or KnowledgeRepository()
    translator = translator or ResilientIntentTranslator()
    read_only_tools = create_read_only_tools(repository)
    workflow = StateGraph(IntentAgentState)

    workflow.add_node("receive_request", receive_request)
    workflow.add_node("normalize_input", normalize_input)
    workflow.add_node(
        "retrieve_knowledge",
        create_retrieve_knowledge_node(repository, translator),
    )
    workflow.add_node("evaluate_knowledge", evaluate_knowledge)
    workflow.add_node("rule_translate", rule_translate)
    workflow.add_node("prepare_model_messages", prepare_model_messages)
    workflow.add_node(
        "llm_decide_next",
        create_llm_decide_next_node(translator, read_only_tools),
    )
    workflow.add_node(
        "readonly_tools",
        ToolNode(read_only_tools, name="readonly_tools", handle_tool_errors=True),
    )
    workflow.add_node(
        "compile_six_tuple",
        create_compile_six_tuple_node(translator),
    )
    workflow.add_node("validate_tuple", validate_tuple)
    workflow.add_node("clarify_with_user", clarify_with_user)
    workflow.add_node("confirm_with_user", confirm_with_user)
    workflow.add_node("finalize_tuple", finalize_tuple)
    workflow.add_node(
        "propose_knowledge_writeback",
        create_propose_knowledge_writeback_node(
            KnowledgeWritebackService(repository, graph_store=graph_store)
        ),
    )

    workflow.add_edge(START, "receive_request")
    workflow.add_edge("receive_request", "normalize_input")
    workflow.add_edge("normalize_input", "retrieve_knowledge")
    workflow.add_edge("retrieve_knowledge", "evaluate_knowledge")
    workflow.add_conditional_edges(
        "evaluate_knowledge",
        route_by_knowledge,
        {
            "rule_translate": "rule_translate",
            "prepare_model_messages": "prepare_model_messages",
        },
    )
    workflow.add_edge("rule_translate", "validate_tuple")
    workflow.add_edge("prepare_model_messages", "llm_decide_next")
    workflow.add_conditional_edges(
        "llm_decide_next",
        route_after_model_decision,
        {
            "readonly_tools": "readonly_tools",
            "compile_six_tuple": "compile_six_tuple",
        },
    )
    workflow.add_edge("readonly_tools", "llm_decide_next")
    workflow.add_edge("compile_six_tuple", "validate_tuple")
    workflow.add_conditional_edges(
        "validate_tuple",
        route_after_validation,
        {
            "clarify": "clarify_with_user",
            "confirm": "confirm_with_user",
            "complete": "finalize_tuple",
            "invalid": END,
        },
    )
    workflow.add_edge("clarify_with_user", "prepare_model_messages")
    workflow.add_conditional_edges(
        "confirm_with_user",
        route_after_confirmation,
        {"finalize": "finalize_tuple", "end": END},
    )
    workflow.add_edge("finalize_tuple", "propose_knowledge_writeback")
    workflow.add_edge("propose_knowledge_writeback", END)
    return workflow.compile(checkpointer=checkpointer)
