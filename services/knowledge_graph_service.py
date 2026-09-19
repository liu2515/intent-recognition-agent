"""知识关系图读取与 Neo4j 同步服务。"""

from typing import Any

from intent_recognition_agent.config.demo_users import get_demo_user
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

    @staticmethod
    def _scope_to_user(result: dict, user_id: str | None) -> dict:
        """保留公共知识，并只展示当前用户的运行主体和运行实例。"""

        if not user_id:
            return result

        runtime_kinds = {"subject_instance", "intent_instance"}
        nodes = [
            item
            for item in result.get("nodes", [])
            if item.get("kind") not in runtime_kinds or item.get("user_id") == user_id
        ]
        node_ids = {item.get("id") for item in nodes}
        edges = [
            item
            for item in result.get("edges", [])
            if item.get("source") in node_ids and item.get("target") in node_ids
        ]

        profile = get_demo_user(user_id) or {"user_id": user_id, "username": user_id}
        if not any(
            item.get("kind") == "subject_instance" and item.get("user_id") == user_id
            for item in nodes
        ):
            subject_id = f"current-subject:{user_id}"
            nodes.append(
                {
                    "id": subject_id,
                    "label": profile.get("username") or user_id,
                    "kind": "subject_instance",
                    "user_id": user_id,
                    "current": True,
                }
            )
            role = next(
                (
                    item
                    for item in nodes
                    if item.get("kind") == "subject" and item.get("label") == "本人"
                ),
                None,
            )
            if role is not None:
                edges.append(
                    {
                        "id": f"current-subject:{user_id}:INSTANCE_OF",
                        "source": subject_id,
                        "target": role["id"],
                        "relation": "INSTANCE_OF",
                        "template_id": None,
                        "status": "current",
                        "properties": {"user_id": user_id, "current": True},
                    }
                )

        result["nodes"] = nodes
        result["edges"] = edges
        summary = result.setdefault("summary", {})
        summary["node_count"] = len(nodes)
        summary["edge_count"] = len(edges)
        summary["runtime_subject_count"] = len(
            {item["id"] for item in nodes if item.get("kind") == "subject_instance"}
        )
        result["selected_subject"] = {
            "user_id": user_id,
            "username": profile.get("username") or user_id,
        }
        return result

    def graph(
        self,
        *,
        include_candidates: bool = True,
        user_id: str | None = None,
        reconcile_deletions: bool = True,
    ) -> dict:
        if self.graph_store is not None and not include_candidates:
            try:
                # Neo4j Browser 可能绕过本服务直接删除节点或关系；每次读取前
                # 自动对账，使知识事实库与当前 Neo4j 图保持一致。
                if reconcile_deletions:
                    self.sync_deletions_from_neo4j()
                result = self.graph_store.read_graph()
                result["neo4j"] = {
                    "enabled": True,
                    "connected": True,
                    "error": None,
                }
                return self._scope_to_user(result, user_id)
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
        return self._scope_to_user(result, user_id)

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

    def sync_deletions_from_neo4j(self) -> dict:
        """把 Neo4j Browser 中的模板删除同步回事实来源。

        若某模板的任意投影关系被删除，则视为整个模板已被人工删除，避免
        MongoDB 在下一次正向同步时又把残缺图数据补回来。
        """

        if self.graph_store is None:
            return {
                "status": "disabled" if self.graph_error is None else "unavailable",
                "error": self.graph_error,
                "deleted_templates": [],
                "synced_templates": 0,
            }
        try:
            edge_counts = self.graph_store.template_edge_counts()
            active_templates = list(self.repository.list_active())
            deleted_template_ids = [
                template.template_id
                for template in active_templates
                if edge_counts.get(template.template_id, 0) < len(template.triples)
            ]
            for template_id in deleted_template_ids:
                self.repository.delete(template_id)

            remaining = list(self.repository.list_active())
            count = len(remaining)
            if deleted_template_ids:
                count = self.graph_store.rebuild(remaining)
            self.graph_error = None
            return {
                "status": "completed",
                "error": None,
                "deleted_templates": deleted_template_ids,
                "synced_templates": count,
            }
        except Exception as exc:
            self.graph_error = str(exc)
            return {
                "status": "unavailable",
                "error": self.graph_error,
                "deleted_templates": [],
                "synced_templates": 0,
            }
