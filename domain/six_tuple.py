"""中国移动业务意图六元组数据模型。

六个顶层字段固定为：主体、动作、业务对象、上下文参数、约束和目标。
动作采用受控枚举，其余字段采用“公共结构 + 可扩展属性”的方式，既保证
结构化输出稳定，也允许后续加入新的移动业务场景。
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MobileActionCategory(str, Enum):
    """移动业务动作所属业务类别，仅用于知识组织和展示。"""

    CARD_AND_NUMBER = "号码与手机卡"
    BILLING = "话费与账单"
    DATA_SERVICE = "流量业务"
    MOBILE_PLAN = "手机套餐"
    SUSPEND_AND_RESUME = "停机与复机"
    BROADBAND = "宽带业务"
    NETWORK_AND_SIGNAL = "网络与信号"
    POINTS_AND_BENEFITS = "积分与权益"
    ACCOUNT_AND_SECURITY = "账户与安全"
    COMPLAINT_AND_SERVICE = "投诉与人工服务"


class MobileAction(str, Enum):
    """当前支持的移动业务动作，即六元组中的第二元组。"""

    # 号码与手机卡
    APPLY_MOBILE_CARD = "办理手机卡"
    SELECT_MOBILE_NUMBER = "选择手机号码"
    ACTIVATE_MOBILE_CARD = "激活手机卡"
    REPLACE_MOBILE_CARD = "补换手机卡"
    REPORT_SIM_LOSS = "办理SIM卡挂失"
    RELEASE_SIM_LOSS = "解除SIM卡挂失"
    TRANSFER_NUMBER_OWNERSHIP = "办理号码过户"
    PORT_MOBILE_NUMBER = "办理携号转网"
    CANCEL_MOBILE_NUMBER = "注销手机号码"
    QUERY_MOBILE_CARD_STATUS = "查询手机卡状态"
    QUERY_PUK_CODE = "查询PUK码"

    # 话费与账单
    QUERY_BALANCE = "查询话费余额"
    QUERY_BILL_DETAILS = "查询账单明细"
    QUERY_REALTIME_CHARGES = "查询实时话费"
    QUERY_HISTORICAL_BILLS = "查询历史账单"
    EXPLAIN_CHARGE = "解释扣费原因"
    HANDLE_BILL_ANOMALY = "处理账单异常"
    QUERY_ARREARS = "查询欠费金额"
    RECHARGE_BALANCE = "办理话费充值"
    APPLY_REFUND = "申请费用退款"
    ISSUE_ELECTRONIC_INVOICE = "开具电子发票"
    QUERY_RECHARGE_RECORDS = "查询充值记录"

    # 流量业务
    QUERY_DATA_BALANCE = "查询流量余量"
    ACTIVATE_DATA_PACKAGE = "办理流量包"
    CANCEL_DATA_PACKAGE = "取消流量包"
    QUERY_DATA_USAGE_DETAILS = "查询流量使用明细"
    QUERY_DATA_PACKAGE_STATUS = "查询流量包状态"
    CHANGE_DATA_PACKAGE = "变更流量包"
    ACTIVATE_ROAMING_DATA_PACKAGE = "办理国际漫游流量包"
    HANDLE_DATA_OVERAGE = "处理流量超额问题"

    # 手机套餐
    QUERY_CURRENT_PLAN = "查询当前套餐"
    QUERY_PLAN_DETAILS = "查询套餐详情"
    CHANGE_MOBILE_PLAN = "变更手机套餐"
    CANCEL_PLAN_ADDON = "取消套餐附加业务"
    RECOMMEND_MOBILE_PLAN = "推荐手机套餐"
    QUERY_PLAN_CONTRACT = "查询套餐合约"
    RELEASE_PLAN_CONTRACT = "解除套餐合约"
    QUERY_PLAN_EFFECTIVE_TIME = "查询套餐生效时间"

    # 停机与复机
    SUSPEND_SERVICE = "办理停机"
    RESUME_SERVICE = "办理复机"
    QUERY_SUSPENSION_REASON = "查询停机原因"
    HANDLE_ARREARS_SUSPENSION = "处理欠费停机"
    APPLY_EMERGENCY_RESUME = "办理紧急开机"
    QUERY_SUSPEND_RESUME_STATUS = "查询停复机状态"

    # 宽带业务
    APPLY_BROADBAND_INSTALLATION = "办理宽带报装"
    QUERY_BROADBAND_COVERAGE = "查询宽带覆盖"
    APPLY_BROADBAND_RELOCATION = "办理宽带移机"
    APPLY_BROADBAND_REPAIR = "办理宽带报修"
    RUN_BROADBAND_SPEED_TEST = "进行宽带测速"
    QUERY_BROADBAND_PLAN = "查询宽带套餐"
    CHANGE_BROADBAND_PLAN = "变更宽带套餐"
    CANCEL_BROADBAND_SERVICE = "取消宽带业务"
    QUERY_BROADBAND_WORK_ORDER = "查询宽带工单"

    # 网络与信号
    HANDLE_MOBILE_SIGNAL_FAULT = "处理移动信号故障"
    HANDLE_SLOW_INTERNET = "处理上网速度慢"
    HANDLE_NO_INTERNET = "处理无法上网"
    HANDLE_5G_NETWORK_PROBLEM = "处理5G网络问题"
    HANDLE_CALL_PROBLEM = "处理通话异常"
    HANDLE_SMS_PROBLEM = "处理短信异常"
    HANDLE_FREQUENT_DISCONNECTION = "处理网络频繁掉线"
    QUERY_REGIONAL_NETWORK_STATUS = "查询区域网络状态"

    # 积分与权益
    QUERY_POINTS_BALANCE = "查询积分余额"
    REDEEM_POINTS_ITEM = "兑换积分商品"
    QUERY_POINTS_DETAILS = "查询积分明细"
    CLAIM_PLAN_BENEFIT = "领取套餐权益"
    QUERY_AVAILABLE_BENEFITS = "查询可用权益"
    RECOMMEND_PROMOTION = "推荐优惠活动"
    QUERY_PROMOTION = "查询优惠活动"
    CANCEL_MARKETING_SUBSCRIPTION = "取消营销订阅"

    # 账户与安全
    HANDLE_LOGIN_PROBLEM = "处理账号登录问题"
    APPLY_REAL_NAME_VERIFICATION = "办理实名认证"
    MODIFY_REAL_NAME_INFORMATION = "修改实名信息"
    RESET_SERVICE_PASSWORD = "重置服务密码"
    MODIFY_ACCOUNT_INFORMATION = "修改账户信息"
    HANDLE_ACCOUNT_ANOMALY = "处理账户异常"
    UNLOCK_ACCOUNT = "解除账户锁定"
    QUERY_REAL_NAME_STATUS = "查询实名认证状态"

    # 投诉与人工服务
    SUBMIT_SERVICE_COMPLAINT = "提交业务投诉"
    SUBMIT_BILLING_COMPLAINT = "提交费用投诉"
    SUBMIT_NETWORK_COMPLAINT = "提交网络投诉"
    QUERY_COMPLAINT_PROGRESS = "查询投诉进度"
    SUPPLEMENT_COMPLAINT_MATERIALS = "补充投诉材料"
    WITHDRAW_COMPLAINT = "撤销投诉"
    TRANSFER_HUMAN_SERVICE = "转接人工客服"
    SUBMIT_SERVICE_EVALUATION = "提交服务评价"


ACTIONS_BY_CATEGORY: dict[MobileActionCategory, tuple[MobileAction, ...]] = {
    MobileActionCategory.CARD_AND_NUMBER: (
        MobileAction.APPLY_MOBILE_CARD,
        MobileAction.SELECT_MOBILE_NUMBER,
        MobileAction.ACTIVATE_MOBILE_CARD,
        MobileAction.REPLACE_MOBILE_CARD,
        MobileAction.REPORT_SIM_LOSS,
        MobileAction.RELEASE_SIM_LOSS,
        MobileAction.TRANSFER_NUMBER_OWNERSHIP,
        MobileAction.PORT_MOBILE_NUMBER,
        MobileAction.CANCEL_MOBILE_NUMBER,
        MobileAction.QUERY_MOBILE_CARD_STATUS,
        MobileAction.QUERY_PUK_CODE,
    ),
    MobileActionCategory.BILLING: (
        MobileAction.QUERY_BALANCE,
        MobileAction.QUERY_BILL_DETAILS,
        MobileAction.QUERY_REALTIME_CHARGES,
        MobileAction.QUERY_HISTORICAL_BILLS,
        MobileAction.EXPLAIN_CHARGE,
        MobileAction.HANDLE_BILL_ANOMALY,
        MobileAction.QUERY_ARREARS,
        MobileAction.RECHARGE_BALANCE,
        MobileAction.APPLY_REFUND,
        MobileAction.ISSUE_ELECTRONIC_INVOICE,
        MobileAction.QUERY_RECHARGE_RECORDS,
    ),
    MobileActionCategory.DATA_SERVICE: (
        MobileAction.QUERY_DATA_BALANCE,
        MobileAction.ACTIVATE_DATA_PACKAGE,
        MobileAction.CANCEL_DATA_PACKAGE,
        MobileAction.QUERY_DATA_USAGE_DETAILS,
        MobileAction.QUERY_DATA_PACKAGE_STATUS,
        MobileAction.CHANGE_DATA_PACKAGE,
        MobileAction.ACTIVATE_ROAMING_DATA_PACKAGE,
        MobileAction.HANDLE_DATA_OVERAGE,
    ),
    MobileActionCategory.MOBILE_PLAN: (
        MobileAction.QUERY_CURRENT_PLAN,
        MobileAction.QUERY_PLAN_DETAILS,
        MobileAction.CHANGE_MOBILE_PLAN,
        MobileAction.CANCEL_PLAN_ADDON,
        MobileAction.RECOMMEND_MOBILE_PLAN,
        MobileAction.QUERY_PLAN_CONTRACT,
        MobileAction.RELEASE_PLAN_CONTRACT,
        MobileAction.QUERY_PLAN_EFFECTIVE_TIME,
    ),
    MobileActionCategory.SUSPEND_AND_RESUME: (
        MobileAction.SUSPEND_SERVICE,
        MobileAction.RESUME_SERVICE,
        MobileAction.QUERY_SUSPENSION_REASON,
        MobileAction.HANDLE_ARREARS_SUSPENSION,
        MobileAction.APPLY_EMERGENCY_RESUME,
        MobileAction.QUERY_SUSPEND_RESUME_STATUS,
    ),
    MobileActionCategory.BROADBAND: (
        MobileAction.APPLY_BROADBAND_INSTALLATION,
        MobileAction.QUERY_BROADBAND_COVERAGE,
        MobileAction.APPLY_BROADBAND_RELOCATION,
        MobileAction.APPLY_BROADBAND_REPAIR,
        MobileAction.RUN_BROADBAND_SPEED_TEST,
        MobileAction.QUERY_BROADBAND_PLAN,
        MobileAction.CHANGE_BROADBAND_PLAN,
        MobileAction.CANCEL_BROADBAND_SERVICE,
        MobileAction.QUERY_BROADBAND_WORK_ORDER,
    ),
    MobileActionCategory.NETWORK_AND_SIGNAL: (
        MobileAction.HANDLE_MOBILE_SIGNAL_FAULT,
        MobileAction.HANDLE_SLOW_INTERNET,
        MobileAction.HANDLE_NO_INTERNET,
        MobileAction.HANDLE_5G_NETWORK_PROBLEM,
        MobileAction.HANDLE_CALL_PROBLEM,
        MobileAction.HANDLE_SMS_PROBLEM,
        MobileAction.HANDLE_FREQUENT_DISCONNECTION,
        MobileAction.QUERY_REGIONAL_NETWORK_STATUS,
    ),
    MobileActionCategory.POINTS_AND_BENEFITS: (
        MobileAction.QUERY_POINTS_BALANCE,
        MobileAction.REDEEM_POINTS_ITEM,
        MobileAction.QUERY_POINTS_DETAILS,
        MobileAction.CLAIM_PLAN_BENEFIT,
        MobileAction.QUERY_AVAILABLE_BENEFITS,
        MobileAction.RECOMMEND_PROMOTION,
        MobileAction.QUERY_PROMOTION,
        MobileAction.CANCEL_MARKETING_SUBSCRIPTION,
    ),
    MobileActionCategory.ACCOUNT_AND_SECURITY: (
        MobileAction.HANDLE_LOGIN_PROBLEM,
        MobileAction.APPLY_REAL_NAME_VERIFICATION,
        MobileAction.MODIFY_REAL_NAME_INFORMATION,
        MobileAction.RESET_SERVICE_PASSWORD,
        MobileAction.MODIFY_ACCOUNT_INFORMATION,
        MobileAction.HANDLE_ACCOUNT_ANOMALY,
        MobileAction.UNLOCK_ACCOUNT,
        MobileAction.QUERY_REAL_NAME_STATUS,
    ),
    MobileActionCategory.COMPLAINT_AND_SERVICE: (
        MobileAction.SUBMIT_SERVICE_COMPLAINT,
        MobileAction.SUBMIT_BILLING_COMPLAINT,
        MobileAction.SUBMIT_NETWORK_COMPLAINT,
        MobileAction.QUERY_COMPLAINT_PROGRESS,
        MobileAction.SUPPLEMENT_COMPLAINT_MATERIALS,
        MobileAction.WITHDRAW_COMPLAINT,
        MobileAction.TRANSFER_HUMAN_SERVICE,
        MobileAction.SUBMIT_SERVICE_EVALUATION,
    ),
}

ACTION_CATEGORY_INDEX = {
    action: category
    for category, actions in ACTIONS_BY_CATEGORY.items()
    for action in actions
}


class SubjectRole(str, Enum):
    SELF = "本人"
    AUTHORIZED_AGENT = "授权代办人"
    THIRD_PARTY = "第三方"
    ORGANIZATION = "政企客户"
    UNKNOWN = "待确认"


class VerificationStatus(str, Enum):
    UNKNOWN = "未知"
    PENDING = "待核验"
    VERIFIED = "已核验"
    FAILED = "核验失败"


class AccountStatus(str, Enum):
    UNKNOWN = "未知"
    ACTIVE = "正常"
    SUSPENDED = "停机"
    ARREARS = "欠费"
    LOCKED = "锁定"
    CANCELLED = "已注销"


class Subject(BaseModel):
    """第一元组：发起请求并承担业务结果的主体。"""

    model_config = ConfigDict(extra="forbid")

    user_id: str | None = None
    username: str | None = None
    role: SubjectRole = SubjectRole.SELF
    mobile_number: str | None = None
    broadband_account: str | None = None
    customer_type: str | None = None
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    account_status: AccountStatus = AccountStatus.UNKNOWN
    description: str | None = None


class Action(BaseModel):
    """第二元组：标准化移动业务动作。"""

    model_config = ConfigDict(extra="forbid")

    name: MobileAction
    category: MobileActionCategory | None = None
    original_expression: str | None = None

    @model_validator(mode="after")
    def infer_and_check_category(self) -> "Action":
        expected = ACTION_CATEGORY_INDEX[self.name]
        if self.category is None:
            self.category = expected
        elif self.category != expected:
            raise ValueError(
                f"动作“{self.name.value}”应属于“{expected.value}”，"
                f"不能设置为“{self.category.value}”"
            )
        return self


class BusinessObjectType(str, Enum):
    """常用移动业务对象类型。"""

    MOBILE_CARD = "手机卡"
    MOBILE_NUMBER = "手机号码"
    SIM_CARD = "SIM卡"
    MOBILE_ACCOUNT = "手机账户"
    PUK_CODE = "PUK码"
    BILL = "通信账单"
    CHARGE_ITEM = "扣费项目"
    RECHARGE_ORDER = "充值订单"
    REFUND_ORDER = "退款申请"
    INVOICE = "电子发票"
    DATA_QUOTA = "流量额度"
    DATA_PACKAGE = "流量包"
    ROAMING_DATA_PACKAGE = "国际漫游流量包"
    MOBILE_PLAN = "手机套餐"
    PLAN_ADDON = "套餐附加业务"
    PLAN_CONTRACT = "套餐合约"
    SUSPEND_RESUME_SERVICE = "停复机服务"
    BROADBAND_ACCOUNT = "宽带账户"
    BROADBAND_LINE = "宽带线路"
    BROADBAND_PLAN = "宽带套餐"
    BROADBAND_WORK_ORDER = "宽带工单"
    MOBILE_NETWORK = "移动网络"
    CALL_SERVICE = "通话服务"
    SMS_SERVICE = "短信服务"
    REGIONAL_NETWORK = "区域网络"
    POINTS_ACCOUNT = "积分账户"
    POINTS_ITEM = "积分商品"
    CUSTOMER_BENEFIT = "客户权益"
    PROMOTION = "优惠活动"
    IDENTITY_PROFILE = "实名信息"
    SERVICE_PASSWORD = "服务密码"
    USER_ACCOUNT = "用户账户"
    COMPLAINT_WORK_ORDER = "投诉工单"
    HUMAN_SERVICE = "人工客服"
    SERVICE_EVALUATION = "服务评价"
    OTHER = "其他业务对象"


class BusinessObject(BaseModel):
    """第三元组：动作所作用的产品、账户、资源或工单。"""

    model_config = ConfigDict(extra="forbid")

    type: BusinessObjectType
    object_id: str | None = None
    name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class TimeContext(BaseModel):
    """自然语言时间和标准化时间信息。"""

    model_config = ConfigDict(extra="forbid")

    billing_cycle: str | None = None
    effective_time: str | None = None
    occurrence_time: str | None = None
    appointment_time: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    timezone: str = "Asia/Shanghai"


class LocationContext(BaseModel):
    """装机、故障、网络查询等业务的地点参数。"""

    model_config = ConfigDict(extra="forbid")

    province: str | None = None
    city: str | None = None
    district: str | None = None
    address: str | None = None
    scene: str | None = None
    longitude: float | None = None
    latitude: float | None = None


class ProductContext(BaseModel):
    """套餐、流量包、宽带和权益产品参数。"""

    model_config = ConfigDict(extra="forbid")

    product_id: str | None = None
    product_name: str | None = None
    price_yuan: float | None = None
    data_gb: float | None = None
    voice_minutes: int | None = None
    sms_count: int | None = None
    bandwidth_mbps: int | None = None
    contract_months: int | None = None
    quantity: int | None = None


class BillingContext(BaseModel):
    """账单、充值、退款和发票参数。"""

    model_config = ConfigDict(extra="forbid")

    amount_yuan: float | None = None
    disputed_amount_yuan: float | None = None
    transaction_id: str | None = None
    payment_channel: str | None = None
    charge_item: str | None = None
    invoice_title: str | None = None
    taxpayer_number: str | None = None
    delivery_email: str | None = None


class NetworkContext(BaseModel):
    """移动网络、通话、短信和宽带故障参数。"""

    model_config = ConfigDict(extra="forbid")

    network_type: str | None = None
    device_model: str | None = None
    symptom: str | None = None
    signal_status: str | None = None
    modem_light_status: str | None = None
    indoor_or_outdoor: str | None = None
    duration: str | None = None
    affected_scope: str | None = None


class ContactContext(BaseModel):
    """报装、报修、投诉等业务的联系信息。"""

    model_config = ConfigDict(extra="forbid")

    contact_name: str | None = None
    contact_mobile: str | None = None
    preferred_channel: str | None = None


class ContextParameters(BaseModel):
    """第四元组：从请求中抽取的场景上下文和业务参数。"""

    model_config = ConfigDict(extra="forbid")

    time: TimeContext | None = None
    location: LocationContext | None = None
    product: ProductContext | None = None
    billing: BillingContext | None = None
    network: NetworkContext | None = None
    contact: ContactContext | None = None
    reason: str | None = None
    user_request: str | None = None
    service_channel: str | None = None
    order_id: str | None = None
    work_order_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ConstraintStatus(str, Enum):
    UNKNOWN = "未知"
    PENDING = "待校验"
    SATISFIED = "已满足"
    VIOLATED = "不满足"
    NOT_APPLICABLE = "不适用"


class ComparisonOperator(str, Enum):
    """约束和成功判据使用的标准比较运算符。"""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    MATCHES = "matches"
    BETWEEN = "between"
    CUSTOM = "custom"


class ConstraintViolationAction(str, Enum):
    """约束不满足时编排器应采取的处理方式。"""

    CLARIFY = "clarify"
    REQUIRE_CONFIRMATION = "require_confirmation"
    BLOCK = "block"
    FALLBACK = "fallback"
    WARN = "warn"


class ConstraintItem(BaseModel):
    """一条可验证的业务约束。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    description: str
    target: str | None = None
    operator: ComparisonOperator = ComparisonOperator.EQ
    expected: Any = None
    actual: Any = None
    source: str | None = None
    verification_method: str | None = None
    status: ConstraintStatus = ConstraintStatus.UNKNOWN
    required: bool = True
    on_violation: ConstraintViolationAction = ConstraintViolationAction.BLOCK
    message: str | None = None


class Confirmation(BaseModel):
    """HITL确认要求及确认结果。"""

    model_config = ConfigDict(extra="forbid")

    required: bool = False
    confirmed: bool = False
    confirmation_text: str | None = None
    confirmed_at: str | None = None


class IntentConstraints(BaseModel):
    """第五元组：身份、资费、权限和业务规则约束。"""

    model_config = ConfigDict(extra="forbid")

    hard: list[ConstraintItem] = Field(default_factory=list)
    soft: list[ConstraintItem] = Field(default_factory=list)
    confirmation: Confirmation = Field(default_factory=Confirmation)
    identity_verification_required: bool = False
    authorization_required: bool = False
    account_must_be_active: bool = False
    no_arrears_required: bool = False
    product_availability_required: bool = False
    network_coverage_required: bool = False
    prevent_duplicate_operation: bool = False
    privacy_masking_required: bool = True
    maximum_charge_yuan: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class CriterionStatus(str, Enum):
    PENDING = "待验证"
    SATISFIED = "已达成"
    FAILED = "未达成"


class GoalStatus(str, Enum):
    """目标整体的生命周期状态。"""

    PENDING = "待验证"
    PARTIALLY_SATISFIED = "部分达成"
    SATISFIED = "已达成"
    FAILED = "未达成"
    CANCELLED = "已取消"


class SuccessCriterion(BaseModel):
    """一条可验证的成功判据。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    description: str
    target: str | None = None
    operator: ComparisonOperator = ComparisonOperator.EQ
    expected: Any = None
    actual: Any = None
    verification_source: str | None = None
    verification_method: str | None = None
    status: CriterionStatus = CriterionStatus.PENDING
    required: bool = True
    evidence: dict[str, Any] = Field(default_factory=dict)


class IntentGoal(BaseModel):
    """第六元组：期望达到的目标状态及成功判据。"""

    model_config = ConfigDict(extra="forbid")

    description: str
    status: GoalStatus = GoalStatus.PENDING
    desired_state: dict[str, Any] = Field(default_factory=dict)
    success_criteria: list[SuccessCriterion] = Field(default_factory=list)
    required_result_fields: list[str] = Field(default_factory=list)
    deadline: str | None = None
    priority: int = Field(default=50, ge=1, le=100)
    partial_success_allowed: bool = False
    postconditions: dict[str, Any] = Field(default_factory=dict)
    failure_state: dict[str, Any] = Field(default_factory=dict)


class IntentSixTuple(BaseModel):
    """完整的中国移动业务意图六元组。"""

    model_config = ConfigDict(extra="forbid")

    subject: Subject
    action: Action
    business_object: BusinessObject | None = None
    context_parameters: ContextParameters = Field(default_factory=ContextParameters)
    constraints: IntentConstraints = Field(default_factory=IntentConstraints)
    goal: IntentGoal

    @field_validator("action", mode="before")
    @classmethod
    def accept_action_name(cls, value: Any) -> Any:
        """允许调用方用中文动作字符串快速创建六元组。"""

        if isinstance(value, str):
            return {"name": value}
        return value

    @field_validator("subject", mode="before")
    @classmethod
    def accept_subject_description(cls, value: Any) -> Any:
        """允许原型阶段直接传入主体描述。"""

        if isinstance(value, str):
            return {"description": value}
        return value


def get_supported_actions() -> list[str]:
    """返回可供提示词、知识匹配和前端下拉框使用的动作名称。"""

    return [action.value for action in MobileAction]
