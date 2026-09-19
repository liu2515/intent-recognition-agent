"""六元组完整性和业务约束校验规则。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from intent_recognition_agent.domain.six_tuple import (
    BusinessObjectType,
    IntentSixTuple,
    MobileAction,
)


class TupleValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    ambiguous_fields: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    confirmation_required: bool = False


WRITE_ACTIONS = {
    action
    for action in MobileAction
    if not action.name.startswith("QUERY_")
    and not action.name.startswith("HANDLE_")
    and not action.name.startswith("RECOMMEND_")
    and action
    not in {
        MobileAction.RUN_BROADBAND_SPEED_TEST,
        MobileAction.TRANSFER_HUMAN_SERVICE,
    }
}

BILLABLE_ACTIONS = {
    MobileAction.APPLY_MOBILE_CARD,
    MobileAction.REPLACE_MOBILE_CARD,
    MobileAction.PORT_MOBILE_NUMBER,
    MobileAction.RECHARGE_BALANCE,
    MobileAction.ACTIVATE_DATA_PACKAGE,
    MobileAction.CHANGE_DATA_PACKAGE,
    MobileAction.ACTIVATE_ROAMING_DATA_PACKAGE,
    MobileAction.CHANGE_MOBILE_PLAN,
    MobileAction.APPLY_BROADBAND_INSTALLATION,
    MobileAction.APPLY_BROADBAND_RELOCATION,
    MobileAction.CHANGE_BROADBAND_PLAN,
    MobileAction.REDEEM_POINTS_ITEM,
}

# 这些业务必须明确作用在哪个移动号码上。登录 user_id 只能标识用户，
# 不能在用户拥有多个号码时替代具体的服务号码；演示环境也不会自动猜测号码。
MOBILE_TARGET_REQUIRED_ACTIONS = {
    MobileAction.QUERY_MOBILE_CARD_STATUS,
    MobileAction.QUERY_BALANCE,
    MobileAction.CANCEL_MOBILE_NUMBER,
    MobileAction.QUERY_DATA_BALANCE,
    MobileAction.ACTIVATE_DATA_PACKAGE,
    MobileAction.CANCEL_DATA_PACKAGE,
    MobileAction.QUERY_DATA_USAGE_DETAILS,
    MobileAction.QUERY_DATA_PACKAGE_STATUS,
    MobileAction.CHANGE_DATA_PACKAGE,
    MobileAction.ACTIVATE_ROAMING_DATA_PACKAGE,
    MobileAction.HANDLE_DATA_OVERAGE,
    MobileAction.QUERY_CURRENT_PLAN,
    MobileAction.QUERY_PLAN_DETAILS,
    MobileAction.CHANGE_MOBILE_PLAN,
    MobileAction.CANCEL_PLAN_ADDON,
    MobileAction.QUERY_PLAN_CONTRACT,
    MobileAction.RELEASE_PLAN_CONTRACT,
    MobileAction.QUERY_PLAN_EFFECTIVE_TIME,
    MobileAction.HANDLE_MOBILE_SIGNAL_FAULT,
    MobileAction.HANDLE_SLOW_INTERNET,
    MobileAction.HANDLE_NO_INTERNET,
    MobileAction.HANDLE_5G_NETWORK_PROBLEM,
    MobileAction.HANDLE_CALL_PROBLEM,
    MobileAction.HANDLE_SMS_PROBLEM,
    MobileAction.HANDLE_FREQUENT_DISCONNECTION,
}

OBJECT_REQUIRED_ACTIONS = WRITE_ACTIONS - {
    MobileAction.SUSPEND_SERVICE,
    MobileAction.RESUME_SERVICE,
    MobileAction.APPLY_EMERGENCY_RESUME,
    MobileAction.APPLY_REAL_NAME_VERIFICATION,
    MobileAction.MODIFY_REAL_NAME_INFORMATION,
    MobileAction.RESET_SERVICE_PASSWORD,
    MobileAction.MODIFY_ACCOUNT_INFORMATION,
    MobileAction.UNLOCK_ACCOUNT,
    MobileAction.SUBMIT_SERVICE_COMPLAINT,
    MobileAction.SUBMIT_BILLING_COMPLAINT,
    MobileAction.SUBMIT_NETWORK_COMPLAINT,
    MobileAction.SUPPLEMENT_COMPLAINT_MATERIALS,
    MobileAction.WITHDRAW_COMPLAINT,
    MobileAction.SUBMIT_SERVICE_EVALUATION,
}

# 大模型草稿中的 missing_fields 只是候选提示，不能直接透传给用户。
# 最终是否缺失必须由当前六元组和业务校验规则决定。
INHERITED_MISSING_ALLOWLIST = {
    "action",
    "business_object",
    "context_parameters.product.specification",
    "context_parameters.location",
    "context_parameters.network.symptom",
    "goal.description",
}

# 模型只负责提出歧义候选；非规范路径不能直接触发 HITL。
# 这可避免模型因措辞波动，把可选字段偶发地判定成必须让用户补充的内容。
INHERITED_AMBIGUOUS_ALLOWLIST = INHERITED_MISSING_ALLOWLIST


def validate_six_tuple(
    value: IntentSixTuple,
    *,
    inherited_missing: list[str] | None = None,
    inherited_ambiguous: list[str] | None = None,
) -> TupleValidationResult:
    """校验结构完整性；不把尚待业务工具核验的约束当作结构错误。"""

    missing = list(
        dict.fromkeys(
            field
            for field in (inherited_missing or [])
            if field in INHERITED_MISSING_ALLOWLIST
        )
    )
    ambiguous = list(
        dict.fromkeys(
            field
            for field in (inherited_ambiguous or [])
            if field in INHERITED_AMBIGUOUS_ALLOWLIST
        )
    )
    errors: list[str] = []
    action = value.action.name

    if not (value.subject.user_id or value.subject.mobile_number or value.subject.broadband_account):
        missing.append("subject.identifier")
    if action in MOBILE_TARGET_REQUIRED_ACTIONS and not value.subject.mobile_number:
        missing.append("subject.mobile_number")
    # 销号属于不可逆业务，不能只凭登录用户身份确认；必须明确要处理的号码。
    if action == MobileAction.CANCEL_MOBILE_NUMBER and not value.subject.mobile_number:
        missing.append("subject.mobile_number")
    if action in OBJECT_REQUIRED_ACTIONS and value.business_object is None:
        missing.append("business_object")
    if not value.goal.description.strip():
        missing.append("goal.description")

    if action == MobileAction.ACTIVATE_DATA_PACKAGE:
        product = value.context_parameters.product
        # 单独的价格不能唯一定位流量包，至少应有产品编号、产品名或流量额度。
        has_product_spec = product is not None and bool(
            product.product_id
            or product.product_name
            or product.data_gb is not None
        )
        has_object_spec = value.business_object is not None and bool(
            value.business_object.object_id
            or (
                value.business_object.name
                and value.business_object.name
                not in {"流量包", "办理流量包", "流量卡", "月流量卡", "每月流量卡"}
            )
        )
        if not has_product_spec and not has_object_spec:
            missing.append("context_parameters.product.specification")

    if action in {
        MobileAction.APPLY_BROADBAND_INSTALLATION,
        MobileAction.APPLY_BROADBAND_RELOCATION,
        MobileAction.APPLY_BROADBAND_REPAIR,
        MobileAction.QUERY_BROADBAND_COVERAGE,
    } and value.context_parameters.location is None:
        missing.append("context_parameters.location")

    if action in {
        MobileAction.HANDLE_MOBILE_SIGNAL_FAULT,
        MobileAction.HANDLE_SLOW_INTERNET,
        MobileAction.HANDLE_NO_INTERNET,
        MobileAction.HANDLE_5G_NETWORK_PROBLEM,
        MobileAction.HANDLE_FREQUENT_DISCONNECTION,
    }:
        if value.context_parameters.location is None:
            missing.append("context_parameters.location")
        network = value.context_parameters.network
        if network is None or not (network.symptom or "").strip():
            missing.append("context_parameters.network.symptom")

    required_confirmation = value.constraints.confirmation.required or action in WRITE_ACTIONS
    value.constraints.confirmation.required = required_confirmation
    confirmation_pending = required_confirmation and not value.constraints.confirmation.confirmed

    if value.business_object is not None:
        if (
            action == MobileAction.ACTIVATE_DATA_PACKAGE
            and value.business_object.type
            not in {BusinessObjectType.DATA_PACKAGE, BusinessObjectType.ROAMING_DATA_PACKAGE}
        ):
            errors.append("办理流量包动作的业务对象类型必须是流量包")

    return TupleValidationResult(
        valid=not missing and not ambiguous and not errors and not confirmation_pending,
        missing_fields=list(dict.fromkeys(missing)),
        ambiguous_fields=list(dict.fromkeys(ambiguous)),
        errors=errors,
        confirmation_required=confirmation_pending,
    )
