"""意图识别大模型客户端及本地确定性降级实现。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from intent_recognition_agent.config.settings import settings
from intent_recognition_agent.domain.knowledge_models import KnowledgeMatch
from intent_recognition_agent.domain.six_tuple import (
    Action,
    BusinessObject,
    BusinessObjectType,
    Confirmation,
    ContextParameters,
    IntentConstraints,
    IntentGoal,
    IntentSixTuple,
    LocationContext,
    MobileAction,
    NetworkContext,
    ProductContext,
    Subject,
    TimeContext,
)
from intent_recognition_agent.domain.translation_models import (
    EvidenceItem,
    IntentHypothesis,
    TranslationDraft,
)
from intent_recognition_agent.domain.validation import WRITE_ACTIONS
from intent_recognition_agent.llm.structured_output import parse_translation_draft


class IntentTranslationError(RuntimeError):
    pass


class IntentTranslator(Protocol):
    def translate(
        self,
        text: str,
        subject: Subject,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft: ...

    def refine(
        self,
        text: str,
        subject: Subject,
        current: IntentSixTuple,
        feedback: str,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft: ...

    def decide_next(
        self,
        messages: Sequence[BaseMessage],
        tools: list[BaseTool],
    ) -> AIMessage: ...

    def translate_with_context(
        self,
        text: str,
        subject: Subject,
        tool_context: str,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft: ...


SYSTEM_PROMPT = """你是中国移动业务意图识别器。你的职责是理解用户想做什么，
输出严格符合给定结构的语义结果，不执行业务、不调用工具。
六个核心字段是主体、动作、业务对象、上下文参数、约束和目标。
必须遵守：
1. 只选择枚举中存在的动作，不创造动作名称。
2. 保留用户表达中的时间、金额、地点、产品规格和否定约束。
3. 用户没有明确说“确认、同意、办理”等扣费授权时，不得把 confirmed 设为 true。
4. 无法确定的内容写入 missing_fields 或 ambiguous_fields，不得臆造。
5. evidence 记录字段对应的原文片段；推断内容标记 source=inference。
6. goal 描述用户期望的业务结果，不写具体工具调用步骤。
7. “办理流量卡、办理月流量卡、办理电话卡、办理手机卡”等表达识别为“办理手机卡”；
   但如果同一句出现“注销、销号、销户”等终止动作，必须识别为“注销手机号码”。
   “办理流量包、开通流量包、加流量”才识别为“办理流量包”；“取消/退订流量包”才识别为“取消流量包”。
"""


class LLMIntentTranslator:
    """使用支持结构化输出的聊天模型生成意图草稿。"""

    def __init__(self, model: BaseChatModel | None = None) -> None:
        if model is None:
            if not settings.llm_available:
                raise IntentTranslationError("意图模型未配置")
            model = ChatOpenAI(
                model=settings.model_name,
                api_key=settings.api_key,
                base_url=settings.base_url,
                temperature=0,
                timeout=settings.model_timeout_seconds,
                max_retries=1,
            )
        self.model = model
        self.structured_model = model.with_structured_output(TranslationDraft)

    def _invoke(self, instruction: str) -> TranslationDraft:
        result = self.structured_model.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=instruction)]
        )
        return parse_translation_draft(result)

    def translate(
        self,
        text: str,
        subject: Subject,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft:
        knowledge = (
            knowledge_match.template.model_dump_json(exclude_none=True)
            if knowledge_match is not None
            else "无"
        )
        return self._invoke(
            "请识别下面的用户请求。\n"
            f"当前主体：{subject.model_dump_json(exclude_none=True)}\n"
            f"可参考但不可覆盖用户原意的知识：{knowledge}\n"
            f"用户原文：{text}"
        )

    def decide_next(
        self,
        messages: Sequence[BaseMessage],
        tools: list[BaseTool],
    ) -> AIMessage:
        result = self.model.bind_tools(tools).invoke(list(messages))
        if isinstance(result, AIMessage):
            return result
        return AIMessage(content=str(getattr(result, "content", result)))

    def translate_with_context(
        self,
        text: str,
        subject: Subject,
        tool_context: str,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft:
        knowledge = (
            knowledge_match.template.model_dump_json(exclude_none=True)
            if knowledge_match is not None
            else "无"
        )
        return self._invoke(
            "请根据用户原文和只读工具结果生成最终六元组草稿。"
            "工具结果只能作为证据，不得视为业务已执行。\n"
            f"当前主体：{subject.model_dump_json(exclude_none=True)}\n"
            f"部分命中的知识：{knowledge}\n"
            f"只读工具结果：{tool_context or '未调用工具'}\n"
            f"用户原文：{text}"
        )

    def refine(
        self,
        text: str,
        subject: Subject,
        current: IntentSixTuple,
        feedback: str,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft:
        return self._invoke(
            "根据用户补充回答修正当前意图。保留未被回答否定的已知字段。\n"
            f"原始请求：{text}\n"
            f"当前主体：{subject.model_dump_json(exclude_none=True)}\n"
            f"当前意图：{current.model_dump_json(exclude_none=True)}\n"
            f"用户补充：{feedback}"
        )


ACTION_ALIASES: dict[MobileAction, tuple[str, ...]] = {
    MobileAction.APPLY_MOBILE_CARD: (
        "办理手机卡", "办手机卡", "办理电话卡", "办电话卡", "新办手机卡",
        "新办电话卡", "申请手机卡", "申请电话卡", "办理新号码", "办新号", "办卡",
        "手机卡", "电话卡", "sim卡", "流量卡", "月流量卡", "每月流量卡",
    ),
    MobileAction.SELECT_MOBILE_NUMBER: ("选择手机号", "选手机号", "选择号码", "挑选号码", "选靓号"),
    MobileAction.ACTIVATE_MOBILE_CARD: ("激活手机卡", "激活电话卡", "激活sim卡", "开卡激活"),
    MobileAction.REPLACE_MOBILE_CARD: ("补换手机卡", "补办手机卡", "换手机卡", "补电话卡", "换电话卡"),
    MobileAction.REPORT_SIM_LOSS: ("sim卡挂失", "手机卡挂失", "电话卡挂失", "卡丢了", "电话卡丢了"),
    MobileAction.RELEASE_SIM_LOSS: ("解除sim卡挂失", "解除手机卡挂失", "解除电话卡挂失", "恢复电话卡"),
    MobileAction.TRANSFER_NUMBER_OWNERSHIP: ("号码过户", "手机卡过户", "电话卡过户"),
    MobileAction.PORT_MOBILE_NUMBER: ("携号转网", "电话卡转网", "手机卡转网"),
    MobileAction.CANCEL_MOBILE_NUMBER: (
        "注销手机号码", "注销手机号", "注销电话卡", "流量卡销号", "注销流量卡",
        "流量卡注销", "销号", "销户",
    ),
    MobileAction.QUERY_MOBILE_CARD_STATUS: ("查询手机卡状态", "查询电话卡状态", "手机卡状态", "电话卡状态", "查手机卡", "查电话卡"),
    MobileAction.QUERY_DATA_BALANCE: ("剩多少流量", "流量余量", "查流量", "流量余额"),
    MobileAction.ACTIVATE_DATA_PACKAGE: ("办理流量包", "开通流量包", "买流量包", "加流量", "流量不够"),
    MobileAction.CANCEL_DATA_PACKAGE: ("取消流量包", "退订流量包"),
    MobileAction.QUERY_DATA_USAGE_DETAILS: ("流量明细", "流量用在哪", "流量使用"),
    MobileAction.QUERY_BALANCE: ("话费余额", "剩多少话费", "查话费"),
    MobileAction.QUERY_BILL_DETAILS: ("账单明细", "查账单", "本月账单"),
    MobileAction.EXPLAIN_CHARGE: ("扣费原因", "为什么扣费", "这笔钱"),
    MobileAction.HANDLE_BILL_ANOMALY: ("账单异常", "乱扣费", "费用不对"),
    MobileAction.RECHARGE_BALANCE: ("充话费", "话费充值"),
    MobileAction.QUERY_CURRENT_PLAN: ("当前套餐", "我的套餐"),
    MobileAction.CHANGE_MOBILE_PLAN: ("更换套餐", "变更套餐", "改套餐"),
    MobileAction.RECOMMEND_MOBILE_PLAN: ("推荐套餐", "什么套餐合适", "便宜的套餐"),
    MobileAction.QUERY_PUK_CODE: ("puk码",),
    MobileAction.APPLY_BROADBAND_INSTALLATION: ("宽带报装", "装宽带", "办理宽带"),
    MobileAction.APPLY_BROADBAND_REPAIR: ("宽带报修", "宽带坏了", "宽带故障"),
    MobileAction.RUN_BROADBAND_SPEED_TEST: ("宽带测速", "测网速"),
    MobileAction.HANDLE_SLOW_INTERNET: ("上网慢", "网速慢", "网络很慢"),
    MobileAction.HANDLE_NO_INTERNET: ("无法上网", "上不了网", "没网"),
    MobileAction.HANDLE_5G_NETWORK_PROBLEM: ("5g网络问题", "5g信号", "5g故障"),
    MobileAction.HANDLE_CALL_PROBLEM: ("无法打电话", "通话异常", "电话打不通"),
    MobileAction.HANDLE_SMS_PROBLEM: ("短信异常", "收不到短信", "发不了短信"),
    MobileAction.QUERY_POINTS_BALANCE: ("积分余额", "多少积分", "查积分"),
    MobileAction.REDEEM_POINTS_ITEM: ("积分兑换", "用积分换"),
    MobileAction.QUERY_AVAILABLE_BENEFITS: ("可用权益", "有什么权益", "套餐权益"),
    MobileAction.RESET_SERVICE_PASSWORD: ("重置服务密码", "忘记服务密码"),
    MobileAction.HANDLE_LOGIN_PROBLEM: ("无法登录", "登录不了", "登录问题"),
    MobileAction.SUBMIT_BILLING_COMPLAINT: ("费用投诉", "扣费投诉"),
    MobileAction.SUBMIT_NETWORK_COMPLAINT: ("网络投诉", "信号投诉"),
    MobileAction.SUBMIT_SERVICE_COMPLAINT: ("业务投诉", "我要投诉"),
    MobileAction.QUERY_COMPLAINT_PROGRESS: ("投诉进度", "投诉处理到哪"),
    MobileAction.TRANSFER_HUMAN_SERVICE: ("人工客服", "转人工", "找人工"),
}

OBJECT_BY_ACTION: dict[MobileAction, BusinessObjectType] = {
    MobileAction.APPLY_MOBILE_CARD: BusinessObjectType.MOBILE_CARD,
    MobileAction.SELECT_MOBILE_NUMBER: BusinessObjectType.MOBILE_NUMBER,
    MobileAction.ACTIVATE_MOBILE_CARD: BusinessObjectType.MOBILE_CARD,
    MobileAction.REPLACE_MOBILE_CARD: BusinessObjectType.MOBILE_CARD,
    MobileAction.QUERY_DATA_BALANCE: BusinessObjectType.DATA_QUOTA,
    MobileAction.ACTIVATE_DATA_PACKAGE: BusinessObjectType.DATA_PACKAGE,
    MobileAction.CANCEL_DATA_PACKAGE: BusinessObjectType.DATA_PACKAGE,
    MobileAction.QUERY_DATA_USAGE_DETAILS: BusinessObjectType.DATA_QUOTA,
    MobileAction.QUERY_BALANCE: BusinessObjectType.MOBILE_ACCOUNT,
    MobileAction.QUERY_BILL_DETAILS: BusinessObjectType.BILL,
    MobileAction.EXPLAIN_CHARGE: BusinessObjectType.CHARGE_ITEM,
    MobileAction.HANDLE_BILL_ANOMALY: BusinessObjectType.BILL,
    MobileAction.RECHARGE_BALANCE: BusinessObjectType.RECHARGE_ORDER,
    MobileAction.QUERY_CURRENT_PLAN: BusinessObjectType.MOBILE_PLAN,
    MobileAction.CHANGE_MOBILE_PLAN: BusinessObjectType.MOBILE_PLAN,
    MobileAction.RECOMMEND_MOBILE_PLAN: BusinessObjectType.MOBILE_PLAN,
    MobileAction.REPORT_SIM_LOSS: BusinessObjectType.SIM_CARD,
    MobileAction.CANCEL_MOBILE_NUMBER: BusinessObjectType.MOBILE_NUMBER,
    MobileAction.QUERY_PUK_CODE: BusinessObjectType.PUK_CODE,
    MobileAction.APPLY_BROADBAND_INSTALLATION: BusinessObjectType.BROADBAND_LINE,
    MobileAction.APPLY_BROADBAND_REPAIR: BusinessObjectType.BROADBAND_WORK_ORDER,
    MobileAction.RUN_BROADBAND_SPEED_TEST: BusinessObjectType.BROADBAND_LINE,
    MobileAction.HANDLE_SLOW_INTERNET: BusinessObjectType.MOBILE_NETWORK,
    MobileAction.HANDLE_NO_INTERNET: BusinessObjectType.MOBILE_NETWORK,
    MobileAction.HANDLE_5G_NETWORK_PROBLEM: BusinessObjectType.MOBILE_NETWORK,
    MobileAction.HANDLE_CALL_PROBLEM: BusinessObjectType.CALL_SERVICE,
    MobileAction.HANDLE_SMS_PROBLEM: BusinessObjectType.SMS_SERVICE,
    MobileAction.QUERY_POINTS_BALANCE: BusinessObjectType.POINTS_ACCOUNT,
    MobileAction.REDEEM_POINTS_ITEM: BusinessObjectType.POINTS_ITEM,
    MobileAction.QUERY_AVAILABLE_BENEFITS: BusinessObjectType.CUSTOMER_BENEFIT,
    MobileAction.RESET_SERVICE_PASSWORD: BusinessObjectType.SERVICE_PASSWORD,
    MobileAction.HANDLE_LOGIN_PROBLEM: BusinessObjectType.USER_ACCOUNT,
    MobileAction.SUBMIT_BILLING_COMPLAINT: BusinessObjectType.COMPLAINT_WORK_ORDER,
    MobileAction.SUBMIT_NETWORK_COMPLAINT: BusinessObjectType.COMPLAINT_WORK_ORDER,
    MobileAction.SUBMIT_SERVICE_COMPLAINT: BusinessObjectType.COMPLAINT_WORK_ORDER,
    MobileAction.QUERY_COMPLAINT_PROGRESS: BusinessObjectType.COMPLAINT_WORK_ORDER,
    MobileAction.TRANSFER_HUMAN_SERVICE: BusinessObjectType.HUMAN_SERVICE,
}


def _core_expression(action: MobileAction) -> str:
    value = action.value.lower()
    for prefix in ("查询", "办理", "处理", "申请", "提交", "修改", "取消", "解除", "进行", "开具", "领取", "推荐", "转接", "兑换", "激活", "选择", "注销"):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


class HeuristicIntentTranslator:
    """离线演示与模型故障时使用的保守规则识别器。"""

    def _rank_actions(self, text: str) -> list[tuple[MobileAction, int, str]]:
        lowered = text.lower().replace(" ", "")
        ranked: list[tuple[MobileAction, int, str]] = []
        verb_groups = {
            "QUERY_": ("查", "多少", "剩", "详情", "明细", "状态"),
            "ACTIVATE_": ("办理", "开通", "购买", "买"),
            "APPLY_": ("办理", "申请", "报装", "报修"),
            "CANCEL_": ("取消", "退订", "不要", "注销", "销号", "销户"),
            "CHANGE_": ("变更", "更换", "改"),
            "HANDLE_": ("处理", "故障", "异常", "慢", "不了", "不通"),
            "SUBMIT_": ("提交", "投诉", "评价"),
            "RECOMMEND_": ("推荐", "合适", "便宜"),
        }
        for action in MobileAction:
            expressions: Sequence[str] = (*ACTION_ALIASES.get(action, ()), action.value, _core_expression(action))
            matched = [item for item in expressions if len(item) >= 2 and item.lower() in lowered]
            if matched:
                strongest = max(matched, key=len)
                verb_bonus = 0
                for prefix, verbs in verb_groups.items():
                    if action.name.startswith(prefix) and any(verb in lowered for verb in verbs):
                        verb_bonus = 10
                        break
                ranked.append((action, len(strongest) + verb_bonus, strongest))
        return sorted(ranked, key=lambda item: item[1], reverse=True)

    def translate(
        self,
        text: str,
        subject: Subject,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft:
        ranked = self._rank_actions(text)
        if not ranked:
            raise IntentTranslationError("无法从请求中确定受支持的移动业务动作")
        action, top_score, expression = ranked[0]
        competing = [item for item in ranked[1:] if item[1] == top_score and item[0] != action]
        ambiguous = ["action"] if competing else []
        hypotheses = [
            IntentHypothesis(action=item[0].value, confidence=max(0.4, 0.9 - index * 0.15), reason=f"命中“{item[2]}”")
            for index, item in enumerate(ranked[:3])
        ]

        price_match = re.search(r"(\d+(?:\.\d+)?)\s*元", text, re.IGNORECASE)
        data_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gb|g)(?![a-z])", text, re.IGNORECASE)
        time_value = next((item for item in ("立即生效", "当月生效", "次月生效", "下月生效", "下个月生效") if item in text), None)
        confirmed = bool(re.search(r"(?:我)?确认|同意(?:办理|扣费)|确定办理", text))
        product = None
        if price_match or data_match:
            product = ProductContext(
                price_yuan=float(price_match.group(1)) if price_match else None,
                data_gb=float(data_match.group(1)) if data_match else None,
            )
        location_match = re.search(r"(?:在|位于)([\u4e00-\u9fff]{2,20}?)(?:的)?(?:5g|4g|网络|信号|宽带)", text, re.IGNORECASE)
        location = LocationContext(address=location_match.group(1)) if location_match else None
        network = None
        if action.name.startswith("HANDLE_") and action in {
            MobileAction.HANDLE_SLOW_INTERNET,
            MobileAction.HANDLE_NO_INTERNET,
            MobileAction.HANDLE_5G_NETWORK_PROBLEM,
            MobileAction.HANDLE_CALL_PROBLEM,
            MobileAction.HANDLE_SMS_PROBLEM,
        }:
            network = NetworkContext(
                network_type="5G" if "5g" in text.lower() else None,
                symptom=text,
            )

        object_type = OBJECT_BY_ACTION.get(action, BusinessObjectType.OTHER)
        constraints = IntentConstraints(
            confirmation=Confirmation(
                required=action in WRITE_ACTIONS,
                confirmed=confirmed,
                confirmation_text=text if confirmed else None,
            ),
            prevent_duplicate_operation=action in WRITE_ACTIONS,
            maximum_charge_yuan=float(price_match.group(1)) if price_match else None,
        )
        value = IntentSixTuple(
            subject=subject,
            action=Action(name=action, original_expression=expression),
            business_object=BusinessObject(type=object_type, name=expression),
            context_parameters=ContextParameters(
                time=TimeContext(effective_time=time_value) if time_value else None,
                product=product,
                location=location,
                network=network,
                user_request=text,
            ),
            constraints=constraints,
            goal=IntentGoal(
                description=f"完成“{action.value}”并返回可验证的业务结果",
                desired_state={"action_completed": True},
                required_result_fields=["status"],
            ),
        )
        evidence = [
            EvidenceItem(field_path="six_tuple.action.name", source_text=expression, confidence=0.9),
        ]
        if price_match:
            evidence.append(EvidenceItem(field_path="six_tuple.context_parameters.product.price_yuan", source_text=price_match.group(0)))
        if data_match:
            evidence.append(EvidenceItem(field_path="six_tuple.context_parameters.product.data_gb", source_text=data_match.group(0)))
        return TranslationDraft(
            six_tuple=value,
            evidence=evidence,
            hypotheses=hypotheses,
            ambiguous_fields=ambiguous,
        )

    def refine(
        self,
        text: str,
        subject: Subject,
        current: IntentSixTuple,
        feedback: str,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft:
        combined = f"{text}。用户补充：{feedback}"
        draft = self.translate(combined, subject, knowledge_match)
        if re.search(r"确认|同意|是的|确定|可以", feedback):
            draft.six_tuple.constraints.confirmation.confirmed = True
            draft.six_tuple.constraints.confirmation.confirmation_text = feedback
        return draft

    def decide_next(
        self,
        messages: Sequence[BaseMessage],
        tools: list[BaseTool],
    ) -> AIMessage:
        return AIMessage(content="离线规则已完成信息判断，进入结构化六元组编译。")

    def translate_with_context(
        self,
        text: str,
        subject: Subject,
        tool_context: str,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft:
        return self.translate(text, subject, knowledge_match)


class ResilientIntentTranslator:
    """优先使用模型，失败时仅对可明确识别的请求进行规则降级。"""

    def __init__(self, primary: IntentTranslator | None = None) -> None:
        self.fallback = HeuristicIntentTranslator()
        if primary is not None:
            self.primary = primary
        elif settings.llm_available:
            try:
                self.primary = LLMIntentTranslator()
            except Exception:
                self.primary = None
        else:
            self.primary = None

    @staticmethod
    def _apply_explicit_action_guard(text: str, draft: TranslationDraft) -> TranslationDraft:
        """用高置信度的终止词覆盖模型可能产生的“流量卡=办卡”误判。"""
        normalized = text.lower().replace(" ", "")
        cancel_number = any(word in normalized for word in ("注销", "销号", "销户"))
        cancel_package = any(word in normalized for word in ("取消", "退订")) and "流量包" in normalized
        if cancel_package:
            draft.six_tuple.action.name = MobileAction.CANCEL_DATA_PACKAGE
            draft.six_tuple.business_object = BusinessObject(
                type=BusinessObjectType.DATA_PACKAGE,
                name="流量包",
            )
        elif cancel_number and any(
            word in normalized
            for word in ("号码", "手机号", "手机号码", "电话卡", "手机卡", "流量卡", "sim卡")
        ):
            draft.six_tuple.action.name = MobileAction.CANCEL_MOBILE_NUMBER
            draft.six_tuple.business_object = BusinessObject(
                type=BusinessObjectType.MOBILE_NUMBER,
                name="手机号码",
            )
        else:
            return draft
        draft.six_tuple.constraints.confirmation.required = True
        return draft

    def translate(self, text: str, subject: Subject, knowledge_match: KnowledgeMatch | None = None) -> TranslationDraft:
        if self.primary is not None:
            try:
                draft = self.primary.translate(text, subject, knowledge_match)
                return self._apply_explicit_action_guard(text, draft)
            except Exception:
                pass
        return self._apply_explicit_action_guard(
            text, self.fallback.translate(text, subject, knowledge_match)
        )

    def refine(self, text: str, subject: Subject, current: IntentSixTuple, feedback: str, knowledge_match: KnowledgeMatch | None = None) -> TranslationDraft:
        if self.primary is not None:
            try:
                draft = self.primary.refine(text, subject, current, feedback, knowledge_match)
                return self._apply_explicit_action_guard(f"{text}。{feedback}", draft)
            except Exception:
                pass
        return self._apply_explicit_action_guard(
            f"{text}。{feedback}",
            self.fallback.refine(text, subject, current, feedback, knowledge_match),
        )

    def decide_next(
        self,
        messages: Sequence[BaseMessage],
        tools: list[BaseTool],
    ) -> AIMessage:
        if self.primary is not None:
            try:
                return self.primary.decide_next(messages, tools)
            except Exception:
                pass
        return self.fallback.decide_next(messages, tools)

    def translate_with_context(
        self,
        text: str,
        subject: Subject,
        tool_context: str,
        knowledge_match: KnowledgeMatch | None = None,
    ) -> TranslationDraft:
        if self.primary is not None:
            try:
                draft = self.primary.translate_with_context(
                    text, subject, tool_context, knowledge_match
                )
                return self._apply_explicit_action_guard(text, draft)
            except Exception:
                pass
        return self._apply_explicit_action_guard(
            text,
            self.fallback.translate_with_context(
                text, subject, tool_context, knowledge_match
            ),
        )
