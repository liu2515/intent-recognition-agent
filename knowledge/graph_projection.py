"""把知识模板投影为前端和图数据库共用的节点/边。"""

from __future__ import annotations

from hashlib import sha256

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeRelation,
    KnowledgeTemplate,
)


TARGET_KIND = {
    KnowledgeRelation.PERFORMED_BY: "subject",
    KnowledgeRelation.ACTS_ON: "object",
    KnowledgeRelation.HAS_PARAMETER: "parameter",
    KnowledgeRelation.HAS_CONSTRAINT: "constraint",
    KnowledgeRelation.ACHIEVES: "goal",
}


def display_label(value: str) -> str:
    return value.split(":", 1)[1] if ":" in value else value


def entity_id(kind: str, label: str) -> str:
    digest = sha256(f"{kind}:{label}".encode("utf-8")).hexdigest()[:16]
    return f"{kind}-{digest}"


def build_knowledge_graph(
    templates: list[KnowledgeTemplate],
    *,
    source: str = "mongodb",
) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for template in templates:
        action_label = template.six_tuple.action.name.value
        action_id = entity_id("action", action_label)
        nodes.setdefault(
            action_id,
            {"id": action_id, "label": action_label, "kind": "action"},
        )
        for index, triple in enumerate(template.triples):
            target_kind = TARGET_KIND[triple.predicate]
            target_label = display_label(triple.object)
            target_id = entity_id(target_kind, triple.object)
            nodes.setdefault(
                target_id,
                {"id": target_id, "label": target_label, "kind": target_kind},
            )
            edges.append(
                {
                    "id": f"{template.template_id}:{index}",
                    "source": action_id,
                    "target": target_id,
                    "relation": triple.predicate.value,
                    "template_id": template.template_id,
                    "status": template.status.value,
                }
            )

    return {
        "source": source,
        "summary": {
            "template_count": len(templates),
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }
