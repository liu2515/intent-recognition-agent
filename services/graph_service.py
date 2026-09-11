"""提供静态图结构和单次执行路径。"""

from intent_recognition_agent.graph.metadata import graph_metadata
from intent_recognition_agent.persistence.trace_repository import TraceRepository


class GraphService:
    def __init__(self, traces: TraceRepository) -> None:
        self.traces = traces

    def definition(self) -> dict:
        return graph_metadata()

    def trace(self, thread_id: str, user_id: str) -> dict:
        return {
            "thread_id": thread_id,
            "events": self.traces.get(thread_id, user_id=user_id),
        }
