"""将六元组投影为意图知识图谱三元组。"""

from typing import Any

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeRelation,
    KnowledgeTriple,
)
from intent_recognition_agent.domain.six_tuple import IntentSixTuple


def _non_empty_items(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, {}, [])
    }


def six_tuple_to_triples(six_tuple: IntentSixTuple) -> list[KnowledgeTriple]:
    """生成动作到对象、参数、约束和目标之间的图关系。"""

    action_node = f"action:{six_tuple.action.name.value}"
    triples: list[KnowledgeTriple] = []

    triples.append(
        KnowledgeTriple(
            subject=action_node,
            predicate=KnowledgeRelation.PERFORMED_BY,
            object=f"subject:{six_tuple.subject.role.value}",
            attributes={
                "customer_type": six_tuple.subject.customer_type,
                "description": six_tuple.subject.description,
            },
        )
    )

    if six_tuple.business_object is not None:
        object_node = f"object:{six_tuple.business_object.type.value}"
        triples.append(
            KnowledgeTriple(
                subject=action_node,
                predicate=KnowledgeRelation.ACTS_ON,
                object=object_node,
                attributes={
                    "name": six_tuple.business_object.name,
                    "object_id": six_tuple.business_object.object_id,
                },
            )
        )

    parameters = _non_empty_items(
        six_tuple.context_parameters.model_dump(mode="json", exclude_none=True)
    )
    for name, value in parameters.items():
        triples.append(
            KnowledgeTriple(
                subject=action_node,
                predicate=KnowledgeRelation.HAS_PARAMETER,
                object=f"parameter:{name}",
                attributes={"value": value},
            )
        )

    for item in [*six_tuple.constraints.hard, *six_tuple.constraints.soft]:
        triples.append(
            KnowledgeTriple(
                subject=action_node,
                predicate=KnowledgeRelation.HAS_CONSTRAINT,
                object=f"constraint:{item.code}",
                attributes={
                    "target": item.target,
                    "operator": item.operator.value,
                    "expected": item.expected,
                    "required": item.required,
                    "on_violation": item.on_violation.value,
                },
            )
        )

    constraint_flags = {
        "identity_verification_required": six_tuple.constraints.identity_verification_required,
        "authorization_required": six_tuple.constraints.authorization_required,
        "account_must_be_active": six_tuple.constraints.account_must_be_active,
        "no_arrears_required": six_tuple.constraints.no_arrears_required,
        "product_availability_required": six_tuple.constraints.product_availability_required,
        "network_coverage_required": six_tuple.constraints.network_coverage_required,
        "prevent_duplicate_operation": six_tuple.constraints.prevent_duplicate_operation,
        "confirmation_required": six_tuple.constraints.confirmation.required,
    }
    for name, required in constraint_flags.items():
        if required:
            triples.append(
                KnowledgeTriple(
                    subject=action_node,
                    predicate=KnowledgeRelation.HAS_CONSTRAINT,
                    object=f"constraint:{name}",
                    attributes={"required": True},
                )
            )
    if six_tuple.constraints.maximum_charge_yuan is not None:
        triples.append(
            KnowledgeTriple(
                subject=action_node,
                predicate=KnowledgeRelation.HAS_CONSTRAINT,
                object="constraint:maximum_charge_yuan",
                attributes={
                    "operator": "lte",
                    "expected": six_tuple.constraints.maximum_charge_yuan,
                    "required": True,
                },
            )
        )

    for item in six_tuple.goal.success_criteria:
        triples.append(
            KnowledgeTriple(
                subject=action_node,
                predicate=KnowledgeRelation.ACHIEVES,
                object=f"goal:{item.code}",
                attributes={
                    "target": item.target,
                    "operator": item.operator.value,
                    "expected": item.expected,
                    "required": item.required,
                },
            )
        )

    if not six_tuple.goal.success_criteria:
        triples.append(
            KnowledgeTriple(
                subject=action_node,
                predicate=KnowledgeRelation.ACHIEVES,
                object=f"goal:{six_tuple.goal.description}",
                attributes={
                    "desired_state": six_tuple.goal.desired_state,
                    "required_result_fields": six_tuple.goal.required_result_fields,
                },
            )
        )

    return triples
