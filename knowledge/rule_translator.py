"""依据已审核知识模板确定性生成六元组。"""

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeCoverage,
    KnowledgeMatch,
)
from intent_recognition_agent.domain.six_tuple import (
    ConstraintStatus,
    CriterionStatus,
    GoalStatus,
    IntentSixTuple,
    Subject,
)
from intent_recognition_agent.knowledge.coverage import evaluate_coverage


def translate_by_rule(
    match: KnowledgeMatch,
    current_subject: Subject,
) -> IntentSixTuple:
    """从完全命中的模板创建本次请求六元组并重置运行时状态。"""

    if evaluate_coverage(match) != KnowledgeCoverage.COMPLETE:
        raise ValueError("只有精确或别名命中可以直接进行规则转译")

    result = match.template.six_tuple.model_copy(deep=True)
    result.subject = current_subject

    for item in [*result.constraints.hard, *result.constraints.soft]:
        item.actual = None
        item.status = ConstraintStatus.PENDING

    result.constraints.confirmation.confirmed = False
    result.constraints.confirmation.confirmed_at = None

    result.goal.status = GoalStatus.PENDING
    for criterion in result.goal.success_criteria:
        criterion.actual = None
        criterion.status = CriterionStatus.PENDING
        criterion.evidence = {}

    return result
