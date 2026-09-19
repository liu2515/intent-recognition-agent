"""依据已生效知识模板确定性生成六元组。"""

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeCoverage,
    KnowledgeMatch,
)
from intent_recognition_agent.domain.six_tuple import (
    BillingContext,
    ContactContext,
    ConstraintStatus,
    CriterionStatus,
    GoalStatus,
    IntentSixTuple,
    LocationContext,
    MobileActionCategory,
    NetworkContext,
    ProductContext,
    Subject,
    TimeContext,
)
from intent_recognition_agent.knowledge.coverage import evaluate_coverage
from intent_recognition_agent.knowledge.runtime_slots import extract_runtime_slots


def translate_by_rule(
    match: KnowledgeMatch,
    current_subject: Subject,
    utterance: str | None = None,
) -> IntentSixTuple:
    """从完全命中的模板创建六元组，并以本次请求参数覆盖模板示例值。"""

    if evaluate_coverage(match) != KnowledgeCoverage.COMPLETE:
        raise ValueError("只有精确、别名或参数化命中可以直接进行规则转译")

    result = match.template.six_tuple.model_copy(deep=True)
    result.subject = current_subject

    if utterance:
        _overlay_runtime_parameters(result, utterance)

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


def _overlay_runtime_parameters(result: IntentSixTuple, utterance: str) -> None:
    """用统一槽位抽取结果覆盖模板示例值，不包含具体业务的特例判断。"""

    slots = extract_runtime_slots(utterance)

    context = result.context_parameters
    context.user_request = utterance
    result.action.original_expression = utterance

    product_fields = {
        "product_id",
        "data_gb",
        "voice_minutes",
        "sms_count",
        "bandwidth_mbps",
        "contract_months",
        "quantity",
    }
    if product_fields.intersection(slots):
        if context.product is None:
            context.product = ProductContext()
        for field in product_fields:
            if field in slots:
                setattr(context.product, field, slots[field])

    if "amount_yuan" in slots:
        amount = slots["amount_yuan"]
        if result.action.category == MobileActionCategory.BILLING:
            if context.billing is None:
                context.billing = BillingContext()
            context.billing.amount_yuan = amount
        else:
            if context.product is None:
                context.product = ProductContext()
            context.product.price_yuan = amount
        result.constraints.maximum_charge_yuan = amount

    if "effective_time" in slots or "occurrence_time" in slots:
        if context.time is None:
            context.time = TimeContext()
        if "effective_time" in slots:
            context.time.effective_time = slots["effective_time"]
        if "occurrence_time" in slots:
            context.time.occurrence_time = slots["occurrence_time"]

    if "province" in slots or "city" in slots:
        if context.location is None:
            context.location = LocationContext()
        if "province" in slots:
            context.location.province = slots["province"]
        if "city" in slots:
            context.location.city = slots["city"]

    if "network_type" in slots:
        if context.network is None:
            context.network = NetworkContext()
        context.network.network_type = slots["network_type"]

    if "contact_mobile" in slots:
        if context.contact is None:
            context.contact = ContactContext()
        context.contact.contact_mobile = slots["contact_mobile"]

    for field in ("order_id", "work_order_id", "service_channel"):
        if field in slots:
            setattr(context, field, slots[field])
    if "mobile_number" in slots:
        result.subject.mobile_number = slots["mobile_number"]
    if "broadband_account" in slots:
        result.subject.broadband_account = slots["broadband_account"]

    # 目标必须描述本次请求，不能继续携带知识样例中的旧槽位值。
    result.goal.description = f"完成用户请求：{utterance}"
