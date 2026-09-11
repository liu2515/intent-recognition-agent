"""根据待补充字段生成用户问题。"""

from intent_recognition_agent.domain.hitl_models import HITLKind, HITLPrompt
from intent_recognition_agent.domain.six_tuple import IntentSixTuple


FIELD_LABELS = {
    "action": "要办理或查询的具体业务",
    "subject.identifier": "需要处理的手机号码或宽带账号",
    "subject.mobile_number": "需要办理或查询的手机号码",
    "subject.broadband_account": "需要处理的宽带账号",
    "business_object": "具体业务对象或产品",
    "business_object.name": "需要办理的套餐或卡类型",
    "business_object.object_id": "套餐名称或产品编号",
    "business_object.attributes.data_gb": "每月流量额度（例如 10GB）",
    "business_object.attributes.contract_months": "是否有合约期及合约月数",
    "context_parameters.product": "流量包或套餐规格",
    "context_parameters.product.specification": "流量包价格、流量或产品名称",
    "context_parameters.product.data_gb": "每月流量额度（例如 10GB）",
    "context_parameters.product.product_name": "流量包或套餐名称",
    "context_parameters.product.product_id": "套餐产品编号",
    "context_parameters.location": "业务地点",
    "context_parameters.network.symptom": "网络制式和故障现象",
    "goal.description": "希望达到的结果",
}


SPECIAL_QUESTIONS = {
    "action": "请明确要办理的是实体手机卡，还是为现有号码办理流量包。",
    "subject.mobile_number": "请补充需要办理或查询的11位中国大陆手机号（以13至19开头）。",
    "context_parameters.product.specification": (
        "请补充希望办理的每月流量大小（例如 10GB），"
        "或直接提供流量包名称、产品编号。"
    ),
    "context_parameters.location": "请补充办理或故障发生的具体地址。",
    "context_parameters.network.symptom": "请补充网络制式和具体故障现象。",
}


def build_clarification_prompt(
    missing_fields: list[str],
    ambiguous_fields: list[str],
) -> HITLPrompt:
    fields = list(dict.fromkeys([*missing_fields, *ambiguous_fields]))
    special = [SPECIAL_QUESTIONS[field] for field in fields if field in SPECIAL_QUESTIONS]
    if len(fields) == 1 and special:
        return HITLPrompt(
            kind=HITLKind.CLARIFICATION,
            question=special[0],
            fields=fields,
        )

    labels = [FIELD_LABELS.get(field, "其他必要业务信息") for field in fields]
    detail = "、".join(dict.fromkeys(labels))
    return HITLPrompt(
        kind=HITLKind.CLARIFICATION,
        question=f"为了准确识别并继续处理，请补充或明确：{detail}。",
        fields=fields,
    )


def build_confirmation_prompt(value: IntentSixTuple) -> HITLPrompt:
    product = value.context_parameters.product
    details: list[str] = [value.action.name.value]
    if product is not None:
        if product.price_yuan is not None:
            details.append(f"费用{product.price_yuan:g}元")
        if product.data_gb is not None:
            details.append(f"流量{product.data_gb:g}GB")
    if value.context_parameters.time and value.context_parameters.time.effective_time:
        details.append(value.context_parameters.time.effective_time)
    return HITLPrompt(
        kind=HITLKind.CONFIRMATION,
        question=f"即将执行{'，'.join(details)}。请明确回复“确认”或“取消”。",
        fields=["constraints.confirmation.confirmed"],
        options=["确认", "取消"],
    )
