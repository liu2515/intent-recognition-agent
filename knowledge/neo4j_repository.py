"""已生效知识向 Neo4j 的可重建投影。"""

from __future__ import annotations

import json
from typing import Any

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeRelation,
    KnowledgeTemplate,
)
from intent_recognition_agent.domain.six_tuple import IntentSixTuple
from intent_recognition_agent.knowledge.graph_projection import display_label, entity_id


class Neo4jKnowledgeGraph:
    """Neo4j 不是事实来源；其内容可由 MongoDB 活动规则重新构建。"""

    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
    ) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("启用 Neo4j 前请安装 neo4j Python 驱动") from exc
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database
        self.driver.verify_connectivity()
        self.driver.execute_query(
            "CREATE CONSTRAINT knowledge_entity_id IF NOT EXISTS "
            "FOR (node:KnowledgeEntity) REQUIRE node.id IS UNIQUE",
            database_=self.database,
        )

    def close(self) -> None:
        self.driver.close()

    def upsert_template(self, template: KnowledgeTemplate) -> None:
        allowed = {item.value for item in KnowledgeRelation}
        action = template.six_tuple.action.name.value
        source_id = entity_id("action", action)
        for triple in template.triples:
            relation = triple.predicate.value
            if relation not in allowed:
                raise ValueError(f"不支持的知识关系: {relation}")
            target_kind = {
                KnowledgeRelation.PERFORMED_BY: "subject",
                KnowledgeRelation.ACTS_ON: "object",
                KnowledgeRelation.HAS_PARAMETER: "parameter",
                KnowledgeRelation.HAS_CONSTRAINT: "constraint",
                KnowledgeRelation.ACHIEVES: "goal",
            }[triple.predicate]
            target_id = entity_id(target_kind, triple.object)
            target_label = display_label(triple.object)
            query = f"""
                MERGE (source:KnowledgeEntity {{id: $source_id}})
                SET source.label = $source_label, source.kind = 'action'
                MERGE (target:KnowledgeEntity {{id: $target_id}})
                SET target.label = $target_label, target.kind = $target_kind
                MERGE (source)-[edge:{relation} {{template_id: $template_id}}]->(target)
                SET edge.status = $status,
                    edge.attributes_json = $attributes_json
            """
            self.driver.execute_query(
                query,
                source_id=source_id,
                source_label=action,
                target_id=target_id,
                target_label=target_label,
                target_kind=target_kind,
                template_id=template.template_id,
                status=template.status.value,
                attributes_json=json.dumps(triple.attributes, ensure_ascii=False),
                database_=self.database,
            )

    def upsert_runtime_intent(
        self,
        *,
        thread_id: str,
        user_id: str,
        six_tuple: IntentSixTuple,
    ) -> None:
        """保存一次已完成意图中的实名主体，但不把实名写入通用知识模板。"""

        subject = six_tuple.subject
        subject_key = subject.user_id or user_id
        subject_label = subject.username or subject_key or subject.role.value
        action_label = six_tuple.action.name.value
        six_tuple_payload = six_tuple.model_dump(mode="json", exclude_none=True)
        object_payload = six_tuple_payload.get("business_object") or {}
        instance_data = {
            "subject": six_tuple_payload.get("subject", {}),
            "action": six_tuple_payload.get("action", {}),
            "business_object": object_payload,
            "context_parameters": six_tuple_payload.get("context_parameters", {}),
            "constraints": six_tuple_payload.get("constraints", {}),
            "goal": six_tuple_payload.get("goal", {}),
        }
        self.driver.execute_query(
            """
            MERGE (run:IntentInstance {thread_id: $thread_id})
            SET run.id = $run_id,
                run.label = $run_label,
                run.kind = 'intent_instance',
                run.user_id = $user_id,
                run.subject_label = $subject_label,
                run.subject_role = $subject_role,
                run.action_label = $action_label,
                run.object_label = $object_label,
                run.instance_data_json = $instance_data_json,
                run.updated_at = datetime()
            """,
            run_id=f"intent:{thread_id}",
            run_label=f"{subject_label} · {action_label}",
            thread_id=thread_id,
            user_id=user_id,
            subject_label=subject_label,
            subject_role=subject.role.value,
            action_label=action_label,
            object_label=object_payload.get("name") or object_payload.get("type"),
            instance_data_json=json.dumps(instance_data, ensure_ascii=False),
            database_=self.database,
        )
        self._project_runtime_instance(
            thread_id=thread_id,
            user_id=user_id,
            subject_key=subject_key,
            subject_label=subject_label,
            subject_role=subject.role.value,
            action_label=action_label,
            object_label=object_payload.get("name") or object_payload.get("type"),
        )

    def _project_runtime_instance(
        self,
        *,
        thread_id: str,
        user_id: str,
        subject_key: str,
        subject_label: str,
        subject_role: str,
        action_label: str,
        object_label: str | None = None,
    ) -> None:
        action_id = entity_id("action", action_label)
        subject_id = entity_id("subject_instance", subject_key)
        role_id = entity_id("subject", f"subject:{subject_role}")
        # 即使未点击“同步 Neo4j”，本次写入也会顺手移除旧版本留下的
        # 动作-主体直连边，避免旧数据继续制造平行边。
        self.driver.execute_query(
            """
            MATCH (action:KnowledgeEntity {id: $action_id})
                  -[legacy:PERFORMED_BY_INSTANCE]->
                  (person:IntentSubject {id: $subject_id})
            DELETE legacy
            """,
            action_id=action_id,
            subject_id=subject_id,
            database_=self.database,
        )
        self.driver.execute_query(
            """
            MERGE (action:KnowledgeEntity {id: $action_id})
            SET action.label = $action_label, action.kind = 'action'
            MERGE (person:KnowledgeEntity:IntentSubject {id: $subject_id})
            SET person.label = $subject_label,
                person.kind = 'subject_instance',
                person.user_id = $user_id,
                person.role = $subject_role
            MERGE (role:KnowledgeEntity {id: $role_id})
            SET role.label = $subject_role, role.kind = 'subject'
            MERGE (run:IntentInstance {thread_id: $thread_id})
            SET run.id = coalesce(run.id, $run_id),
                run.label = coalesce(run.label, $subject_label + ' · ' + $action_label),
                run.kind = 'intent_instance'
            MERGE (run)-[execution:EXECUTES {thread_id: $thread_id}]->(action)
            SET execution.user_id = $user_id,
                execution.source = 'runtime_intent'
            MERGE (run)-[subject_link:HAS_SUBJECT {thread_id: $thread_id}]->(person)
            SET subject_link.user_id = $user_id,
                subject_link.source = 'runtime_intent'
            MERGE (person)-[instance:INSTANCE_OF]->(role)
            SET instance.role = $subject_role,
                instance.source = 'runtime_intent'
            """,
            action_id=action_id,
            action_label=action_label,
            run_id=f"intent:{thread_id}",
            subject_id=subject_id,
            subject_label=subject_label,
            user_id=user_id,
            subject_role=subject_role,
            role_id=role_id,
            thread_id=thread_id,
            database_=self.database,
        )

    def _restore_runtime_projection(self) -> None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (run:IntentInstance)
            RETURN run.thread_id AS thread_id, run.user_id AS user_id,
                   run.subject_label AS subject_label,
                   run.subject_role AS subject_role,
                   run.action_label AS action_label
            """,
            database_=self.database,
        )
        for record in records:
            if not all(record.get(key) for key in ("thread_id", "user_id", "subject_role", "action_label")):
                continue
            self._project_runtime_instance(
                thread_id=record["thread_id"],
                user_id=record["user_id"],
                subject_key=record["user_id"],
                subject_label=record["subject_label"] or record["user_id"],
                subject_role=record["subject_role"],
                action_label=record["action_label"],
            )

    def rebuild(self, templates: list[KnowledgeTemplate]) -> int:
        # 清理旧版本生成的动作-主体直连边。运行实例应通过
        # IntentInstance-[:EXECUTES|HAS_SUBJECT]->... 表达，避免参数变化后
        # 在同一动作和主体之间不断累积平行边。
        self.driver.execute_query(
            "MATCH ()-[edge:PERFORMED_BY_INSTANCE]->() DELETE edge",
            database_=self.database,
        )
        self.driver.execute_query(
            "MATCH (node:KnowledgeEntity) DETACH DELETE node",
            database_=self.database,
        )
        for template in templates:
            self.upsert_template(template)
        self._restore_runtime_projection()
        return len(templates)

    def _read_relationships(self, relationship_filter: str = "") -> dict[str, Any]:
        where_clause = f"WHERE {relationship_filter}" if relationship_filter else ""
        records, _, _ = self.driver.execute_query(
            f"""
            MATCH (source:KnowledgeEntity)-[edge]->(target:KnowledgeEntity)
            {where_clause}
            RETURN source.id AS source_id, source.label AS source_label,
                   source.kind AS source_kind, target.id AS target_id,
                   target.label AS target_label, target.kind AS target_kind,
                   type(edge) AS relation, edge.template_id AS template_id,
                   edge.status AS status, properties(edge) AS properties
            ORDER BY source.label, relation, target.label
            """,
            database_=self.database,
        )
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        for index, record in enumerate(records):
            nodes[record["source_id"]] = {
                "id": record["source_id"],
                "label": record["source_label"],
                "kind": record["source_kind"],
            }
            nodes[record["target_id"]] = {
                "id": record["target_id"],
                "label": record["target_label"],
                "kind": record["target_kind"],
            }
            edges.append(
                {
                    "id": f"neo4j:{record['relation']}:{index}",
                    "source": record["source_id"],
                    "target": record["target_id"],
                    "relation": record["relation"],
                    "template_id": record["template_id"],
                    "status": record["status"],
                    "properties": dict(record["properties"] or {}),
                }
            )
        return {"nodes": list(nodes.values()), "edges": edges}

    def read_runtime_graph(self) -> dict:
        """读取运行实例链路，供 MongoDB 模板投影合并展示。

        运行实例是独立节点；动作和主体之间不再写入运行时直连边。
        """
        records, _, _ = self.driver.execute_query(
            """
            MATCH (source)-[edge]->(target)
            WHERE (source:IntentInstance AND type(edge) IN ['EXECUTES', 'HAS_SUBJECT'])
               OR (source:IntentSubject AND type(edge) = 'INSTANCE_OF')
            RETURN coalesce(source.id, 'intent:' + source.thread_id) AS source_id,
                   coalesce(source.label, source.subject_label) AS source_label,
                   coalesce(source.kind, 'intent_instance') AS source_kind,
                   target.id AS target_id, target.label AS target_label,
                   target.kind AS target_kind, type(edge) AS relation,
                   edge.template_id AS template_id, edge.status AS status,
                   properties(edge) AS properties
            ORDER BY source_label, relation, target_label
            """,
            database_=self.database,
        )
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        for index, record in enumerate(records):
            source_id = record["source_id"]
            target_id = record["target_id"]
            nodes[source_id] = {
                "id": source_id,
                "label": record["source_label"],
                "kind": record["source_kind"],
            }
            nodes[target_id] = {
                "id": target_id,
                "label": record["target_label"],
                "kind": record["target_kind"],
            }
            edges.append(
                {
                    "id": f"runtime:{record['relation']}:{index}",
                    "source": source_id,
                    "target": target_id,
                    "relation": record["relation"],
                    "template_id": record["template_id"],
                    "status": record["status"],
                    "properties": dict(record["properties"] or {}),
                }
            )
        return {"nodes": list(nodes.values()), "edges": edges}

    def read_graph(self) -> dict:
        # 兼容尚未执行同步的旧库：历史版本的运行时直连边不再属于展示模型。
        graph = self._read_relationships("type(edge) <> 'PERFORMED_BY_INSTANCE'")
        nodes = graph["nodes"]
        edges = graph["edges"]
        return {
            "source": "neo4j",
            "summary": {
                "template_count": len(
                    {item["template_id"] for item in edges if item["template_id"]}
                ),
                "node_count": len(nodes),
                "edge_count": len(edges),
                "runtime_subject_count": len(
                    {item["id"] for item in nodes if item["kind"] == "subject_instance"}
                ),
            },
            "nodes": nodes,
            "edges": edges,
        }
