"""知识关系图读取与 Neo4j 同步服务。"""

from typing import Any

from intent_recognition_agent.domain.knowledge_models import KnowledgeStatus
from intent_recognition_agent.knowledge.graph_projection import build_knowledge_graph


class KnowledgeGraphService:
    def __init__(
        self,
        repository: Any,
        graph_store: Any | None = None,
        graph_error: str | None = None,
    ) -> None:
        self.repository = repository
        self.graph_store = graph_store
        self.graph_error = graph_error

    def graph(self, *, include_candidates: bool = True) -> dict:
        if self.graph_store is not None and not include_candidates:
            try:
                result = self.graph_store.read_graph()
                result["neo4j"] = {
                    "enabled": True,
                    "connected": True,
                    "error": None,
                }
                return result
            except Exception as exc:
                self.graph_error = str(exc)

        templates = list(self.repository.list_active())
        if include_candidates:
            templates.extend(
                self.repository.list_candidates(KnowledgeStatus.PENDING)
            )
        result = build_knowledge_graph(templates, source="mongodb-projection")
        if self.graph_store is not None:
            try:
                runtime = self.graph_store.read_runtime_graph()
                nodes = {item["id"]: item for item in result["nodes"]}
                nodes.update({item["id"]: item for item in runtime["nodes"]})
                edges = {item["id"]: item for item in result["edges"]}
                edges.update({item["id"]: item for item in runtime["edges"]})
                result["nodes"] = list(nodes.values())
                result["edges"] = list(edges.values())
                result["summary"]["node_count"] = len(nodes)
                result["summary"]["edge_count"] = len(edges)
                result["summary"]["runtime_subject_count"] = len(
                    {
                        item["id"]
                        for item in nodes.values()
                        if item.get("kind") == "subject_instance"
                    }
                )
                result["source"] = "mongodb-projection + neo4j-runtime"
            except Exception as exc:
                self.graph_error = str(exc)
        result["neo4j"] = {
            "enabled": self.graph_store is not None or self.graph_error is not None,
            "connected": self.graph_store is not None and self.graph_error is None,
            "error": self.graph_error,
        }
        return result

    def sync(self) -> dict:
        if self.graph_store is None:
            return {
                "status": "disabled" if self.graph_error is None else "unavailable",
                "error": self.graph_error,
                "synced_templates": 0,
            }
        try:
            count = self.graph_store.rebuild(self.repository.list_active())
            self.graph_error = None
            return {"status": "completed", "error": None, "synced_templates": count}
        except Exception as exc:
            self.graph_error = str(exc)
            return {
                "status": "unavailable",
                "error": self.graph_error,
                "synced_templates": 0,
            }
