"""让模型决定调用只读工具还是进入六元组编译。"""

from collections.abc import Callable

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.llm.client import IntentTranslator


def create_llm_decide_next_node(
    translator: IntentTranslator,
    tools: list[BaseTool],
) -> Callable[[IntentAgentState], IntentAgentState]:
    def llm_decide_next(state: IntentAgentState) -> IntentAgentState:
        decide = getattr(translator, "decide_next", None)
        if decide is None:
            message = AIMessage(content="现有信息足够，进入结构化六元组编译。")
        else:
            message = decide(state.get("messages", []), tools)
        return {
            "messages": [message],
            "model_tool_rounds": int(state.get("model_tool_rounds", 0)) + 1,
        }

    return llm_decide_next
