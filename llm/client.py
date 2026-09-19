"""意图识别大模型客户端及本地确定性降级实现。"""

from __future__ import annotations

import logging
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from intent_recognition_agent.config.settings import settings
from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeCoverage,
    KnowledgeCoverageDecision,
    KnowledgeMatch,
    KnowledgeNormalization,
    KnowledgeTemplate,
)
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
    IntentPlanDraft,
    IntentHypothesis,
    IntentTaskDraft,
    TranslationDraft,
)
from intent_recognition_agent.domain.validation import WRITE_ACTIONS
from intent_recognition_agent.llm.structured_output import parse_intent_plan, parse_translation_draft


logger = logging.getLogger(__name__)


class IntentTranslationError(RuntimeError):
    pass


class IntentTranslator(Protocol):
    def decompose(self, text: str, subject: Subject) -> IntentPlanDraft: ...

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

    def assess_knowledge_coverage(
        self,
        text: str,
        subject: Subject,
        templates: list[KnowledgeTemplate],
    ) -> KnowledgeCoverageDecision: ...

    def normalize_for_knowledge(
        self,
        text: str,
        subject: Subject,
        templates: list[KnowledgeTemplate],
    ) -> KnowledgeNormalization: ...


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
7. “办理流量卡、办理月流量卡、办理电话卡、办理手机卡、办理新的手机号”等表达识别为“办理手机卡”；
   “消除当前手机号、消除手机号、注销、销号、销户”等终止号码表达识别为“注销手机号码”，并要求用户确认。
   “办理流量包、开通流量包、加流量”才识别为“办理流量包”；“取消/退订流量包”才识别为“取消流量包”。
"""


_PROMPT_DIRECTORY = Path(__file__).resolve().parent / "prompts"
_STAGE_PROMPT_FILES = {
    "translate": "translate.txt",
    "refine": "refine.txt",
    "complete": "complete.txt",
    "finalize": "finalize.txt",
    "clarification": "clarification.txt",
    "coverage": "coverage.txt",
    "knowledge_normalize": "knowledge_normalize.txt",
}


def _load_stage_prompts() -> dict[str, str]:
    """在启动时读取阶段提示词；缺失时保留基础约束，避免服务不可用。"""
    prompts: dict[str, str] = {}
    for stage, filename in _STAGE_PROMPT_FILES.items():
        path = _PROMPT_DIRECTORY / filename
        try:
            prompts[stage] = path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("未能读取阶段提示词 %s", path, exc_info=True)
            prompts[stage] = ""
    return prompts


_STAGE_PROMPTS = _load_stage_prompts()


def system_prompt_for(*stages: str) -> str:
    """组合通用规则和当前模型阶段的专属约束。"""
    parts = [SYSTEM_PROMPT]
    for stage in stages:
        prompt = _STAGE_PROMPTS.get(stage, "")
        if prompt:
            parts.append(f"【{stage} 阶段约束】\n{prompt}")
    return "\n\n".join(parts)


class LLMIntentTranslator:
    """使用支持结构化输出的聊天模型生成意图草稿。"""

    def __init__(self, model: BaseChatModel | None = None) -> None:
        knowledge_model = model
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
            # 知识检索阶段只做语义标准化和覆盖判断。该结果属于可降级的
            # 检索增强信息，必须使用短超时且禁止重试，避免一个辅助步骤
            # 阻塞完整工作流两分钟。
            knowledge_model = ChatOpenAI(
                model=settings.model_name,
                api_key=settings.api_key,
                base_url=settings.base_url,
                temperature=0,
                timeout=settings.knowledge_model_timeout_seconds,
                max_retries=0,
            )
        if knowledge_model is None:
            knowledge_model = model
        self.model = model
        self.structured_model = model.with_structured_output(TranslationDraft)
        self.plan_model = model.with_structured_output(IntentPlanDraft)
        self.coverage_model = knowledge_model.with_structured_output(KnowledgeCoverageDecision)
        self.knowledge_normalizer = knowledge_model.with_structured_output(KnowledgeNormalization)

    def _invoke(self, instruction: str, *, stages: tuple[str, ...]) -> TranslationDraft:
        result = self.structured_model.invoke(
            [SystemMessage(content=system_prompt_for(*stages)), HumanMessage(content=instruction)]
        )
        return parse_translation_draft(result)

    def decompose(self, text: str, subject: Subject) -> IntentPlanDraft:
        """先识别原始请求中的原子任务，再分别生成六元组。"""
        prompt = (
            "请把用户请求拆分为互不重叠的原子移动业务任务。必须返回 1 至 8 项任务，绝不能返回空 tasks。"
            "每项任务只能对应一个主要业务动作；保留任务原文中的手机号、套餐、时间等信息。"
            "没有明确依赖时 depends_on 为空；出现‘先/然后/之后’时按真实先后填写。"
            "不要把同一项业务的参数拆成多个任务，最多返回 8 项。"
            "“消除当前手机号，并办理新的手机号”必须拆为两项："
            "第一项 text 为“消除当前手机号”、action_hint 为“注销手机号码”；"
            "第二项 text 为“办理新的手机号”、action_hint 为“办理手机卡”。"
            "如果不能确定动作，也必须保留原文作为一项任务，并将 action_hint 设为 null。"
            "只返回 JSON：{tasks:[{task_id,sequence,text,action_hint,depends_on}]}。\n"
            f"当前主体：{subject.model_dump_json(exclude_none=True)}\n"
            f"用户原文：{text}"
        )
        result = self.plan_model.invoke(
            [SystemMessage(content=system_prompt_for()), HumanMessage(content=prompt)]
        )
        return parse_intent_plan(result)

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
            f"用户原文：{text}",
            stages=("translate", "clarification"),
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
            f"用户原文：{text}",
            stages=("complete", "clarification", "finalize"),
        )

    def assess_knowledge_coverage(
        self,
        text: str,
        subject: Subject,
        templates: list[KnowledgeTemplate],
    ) -> KnowledgeCoverageDecision:
        candidates = [
            {
                "template_id": item.template_id,
                "canonical_utterance": item.canonical_utterance,
                "aliases": item.aliases,
                "match_keywords": item.match_keywords,
                "action": item.six_tuple.action.model_dump(mode="json"),
                "business_object": (
                    item.six_tuple.business_object.model_dump(mode="json")
                    if item.six_tuple.business_object
                    else None
                ),
                "context_parameters": item.six_tuple.context_parameters.model_dump(
                    mode="json", exclude_none=True
                ),
            }
            for item in templates
        ]
        result = self.coverage_model.invoke(
            [
                SystemMessage(content=system_prompt_for("coverage")),
                HumanMessage(
                    content=(
                        f"当前主体：{subject.model_dump_json(exclude_none=True)}\n"
                        f"用户请求：{text}\n"
                        f"候选知识模板：{json.dumps(candidates, ensure_ascii=False, default=str)}"
                    )
                ),
            ]
        )
        return KnowledgeCoverageDecision.model_validate(result)

    def normalize_for_knowledge(
        self,
        text: str,
        subject: Subject,
        templates: list[KnowledgeTemplate],
    ) -> KnowledgeNormalization:
        """在确定性检索前，将自然表达归一到受控业务表达。"""

        candidates = [
            {
                "template_id": item.template_id,
                "canonical_utterance": item.canonical_utterance,
                "aliases": item.aliases,
                "action": item.six_tuple.action.model_dump(mode="json"),
                "business_object": (
                    item.six_tuple.business_object.model_dump(mode="json")
                    if item.six_tuple.business_object
                    else None
                ),
            }
            for item in templates
        ]
        result = self.knowledge_normalizer.invoke(
            [
                SystemMessage(content=system_prompt_for("knowledge_normalize")),
                HumanMessage(
                    content=(
                        f"当前主体：{subject.model_dump_json(exclude_none=True)}\n"
                        f"用户原文：{text}\n"
                        f"候选知识模板：{json.dumps(candidates, ensure_ascii=False, default=str)}"
                    )
                ),
            ]
        )
        return KnowledgeNormalization.model_validate(result)

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
            f"用户补充：{feedback}",
            stages=("refine", "clarification"),
        )


ACTION_ALIASES: dict[MobileAction, tuple[str, ...]] = {
    MobileAction.APPLY_MOBILE_CARD: (
        "办理手机卡", "办手机卡", "办理电话卡", "办电话卡", "新办手机卡",
        "新办电话卡", "申请手机卡", "申请电话卡", "办理新号码", "办新号", "办卡",
        "办理新手机号", "办理新的手机号", "办新手机号", "办新的手机号", "新办手机号",
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
        "流量卡注销", "消除当前手机号", "消除手机号", "消除手机号码",
        "注销当前手机号", "注销当前手机号码", "当前手机号注销", "当前手机号码注销",
        "手机号注销", "手机号码注销", "当前手机号销号", "当前手机号销户",
        "销号", "销户",
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
    MobileAction.QUERY_CURRENT_PLAN: (
        "当前套餐",
        "我的套餐",
        "查询套餐",
        "查套餐",
        "生效的套餐",
        "当前生效套餐",
        "当月生效的套餐",
        "本月生效的套餐",
    ),
    MobileAction.QUERY_PLAN_DETAILS: ("查询套餐详情", "套餐详情", "套餐内容"),
    MobileAction.QUERY_PLAN_EFFECTIVE_TIME: (
        "查询套餐生效时间",
        "套餐生效时间",
        "套餐什么时候生效",
        "套餐何时生效",
    ),
    MobileAction.CHANGE_MOBILE_PLAN: ("更换套餐", "变更套餐", "改套餐"),
    MobileAction.RECOMMEND_MOBILE_PLAN: ("推荐套餐", "什么套餐合适", "便宜的套餐"),
    MobileAction.QUERY_PUK_CODE: ("puk码",),
    MobileAction.APPLY_BROADBAND_INSTALLATION: ("宽带报装", "装宽带", "办理宽带"),
    MobileAction.APPLY_BROADBAND_REPAIR: ("宽带报修", "宽带坏了", "宽带故障"),
    MobileAction.RUN_BROADBAND_SPEED_TEST: ("宽带测速", "测网速"),
    MobileAction.HANDLE_SLOW_INTERNET: ("上网慢", "网速慢", "网络很慢"),
    MobileAction.HANDLE_NO_INTERNET: ("无法上网", "上不了网", "没网"),
    MobileAction.HANDLE_5G_NETWORK_PROBLEM: ("5g网络问题", "5g信号", "5g故障"),
    MobileAction.HANDLE_CALL_PROBLEM: (
        "无法打电话", "通话异常", "电话打不通", "电话打不出去", "电话拨不出去",
        "电话无法拨出", "无法拨号", "呼叫失败",
    ),
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
    MobileAction.QUERY_PLAN_DETAILS: BusinessObjectType.MOBILE_PLAN,
    MobileAction.QUERY_PLAN_EFFECTIVE_TIME: BusinessObjectType.MOBILE_PLAN,
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

    def decompose(self, text: str, subject: Subject) -> IntentPlanDraft:
        """离线降级：只在明显的连接词/分号处拆分，并过滤无动作片段。"""
        parts = [item.strip(" \uFF0C,\u3002\uFF1B;\t") for item in re.split(
            r"(?:\u7136\u540E|\u63A5\u7740|\u4E4B\u540E|\u518D|\u540C\u65F6|\u5E76\u4E14|\u5E76|\u53E6\u5916|\u987A\u4FBF|\u4EE5\u53CA|\uFF1B|;)", text
        )]
        parts = [item for item in parts if item]
        if not parts:
            parts = [text.strip()]
        tasks = []
        for index, part in enumerate(parts, 1):
            ranked = self._rank_actions(part)
            tasks.append(
                IntentTaskDraft(
                    task_id=f"task-{index}",
                    sequence=index,
                    text=part,
                    action_hint=ranked[0][0].value if ranked else None,
                    depends_on=[f"task-{index - 1}"]
                    if index > 1 and re.search(r"\u7136\u540E|\u4E4B\u540E|\u63A5\u7740|\u518D", text)
                    else [],
                )
            )
        return IntentPlanDraft(tasks=tasks)

    def _rank_actions(self, text: str) -> list[tuple[MobileAction, int, str]]:
        lowered = text.lower().replace(" ", "")
        ranked: list[tuple[MobileAction, int, str]] = []
        verb_groups = {
            "QUERY_": ("查", "多少", "剩", "详情", "明细", "状态"),
            "ACTIVATE_": ("办理", "开通", "购买", "买"),
            "APPLY_": ("办理", "申请", "报装", "报修"),
            "CANCEL_": ("取消", "退订", "不要", "注销", "销号", "销户", "消除"),
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

        # 处理中文自然语序中的动作/对象倒装，避免模型不可用时降级识别失败。
        # 例如“当前手机号注销了”“我要把手机卡销户”并不一定包含
        # ACTION_ALIASES 中的连续短语，但语义上仍明确表示销号。
        cancel_number_verbs = ("注销", "销号", "销户", "消除")
        number_objects = (
            "手机号码",
            "手机号",
            "电话号码",
            "电话卡",
            "手机卡",
            "流量卡",
            "sim卡",
        )
        if (
            any(verb in lowered for verb in cancel_number_verbs)
            and any(obj in lowered for obj in number_objects)
            and not any(item[0] == MobileAction.CANCEL_MOBILE_NUMBER for item in ranked)
        ):
            ranked.append(
                (
                    MobileAction.CANCEL_MOBILE_NUMBER,
                    20,
                    "注销" if "注销" in lowered else "销号",
                )
            )

        # “流量包取消/退订”同样支持对象在前的表达。
        if (
            "流量包" in lowered
            and any(verb in lowered for verb in ("取消", "退订"))
            and not any(item[0] == MobileAction.CANCEL_DATA_PACKAGE for item in ranked)
        ):
            ranked.append(
                (
                    MobileAction.CANCEL_DATA_PACKAGE,
                    20,
                    "取消" if "取消" in lowered else "退订",
                )
            )

        # 账单/扣费类请求通常会在“为什么、这个月、多扣、收费”等词之间
        # 插入时间、金额或修饰语，不能只依赖“为什么扣费”这种固定短语。
        charge_terms = ("扣费", "扣了", "多扣", "乱扣", "收费", "账单", "金额", "费用")
        if any(term in lowered for term in charge_terms):
            if (
                any(term in lowered for term in ("为什么", "为何", "怎么回事", "原因"))
                and not any(item[0] == MobileAction.EXPLAIN_CHARGE for item in ranked)
            ):
                ranked.append((MobileAction.EXPLAIN_CHARGE, 20, "扣费原因"))
            elif (
                any(term in lowered for term in ("多扣", "乱扣", "不对", "异常"))
                and not any(item[0] == MobileAction.HANDLE_BILL_ANOMALY for item in ranked)
            ):
                ranked.append((MobileAction.HANDLE_BILL_ANOMALY, 20, "账单异常"))

        # 通话故障通常会描述“电话/拨号 + 无法拨出/打不通”，
        # 即使短信、流量等其他能力正常，也仍应归入通话异常。
        call_objects = ("电话", "通话", "拨号", "呼叫")
        call_failures = (
            "打不出去",
            "拨不出去",
            "打不通",
            "无法拨出",
            "无法打",
            "不能打",
            "呼叫失败",
            "通话异常",
        )
        if (
            any(item in lowered for item in call_objects)
            and any(item in lowered for item in call_failures)
            and not any(item[0] == MobileAction.HANDLE_CALL_PROBLEM for item in ranked)
        ):
            ranked.append((MobileAction.HANDLE_CALL_PROBLEM, 20, "通话异常"))

        if (
            "5g" in lowered
            and any(
                item in lowered
                for item in ("不稳定", "没信号", "无信号", "信号差", "网络问题", "断网")
            )
            and not any(item[0] == MobileAction.HANDLE_5G_NETWORK_PROBLEM for item in ranked)
        ):
            ranked.append((MobileAction.HANDLE_5G_NETWORK_PROBLEM, 30, "5G网络异常"))

        # 组合识别“查询动词 + 套餐对象 + 生效时间”。时间位于套餐前后都可识别：
        # “查询当月生效的套餐”是在筛选当前套餐；“套餐什么时候生效”是在查询生效时间。
        query_terms = ("查询", "查一下", "查查", "查看", "看看", "了解")
        plan_terms = ("套餐", "资费方案")
        effective_terms = (
            "当月生效",
            "本月生效",
            "当前生效",
            "正在生效",
            "立即生效",
            "次月生效",
            "下月生效",
        )
        if (
            any(item in lowered for item in query_terms)
            and any(item in lowered for item in plan_terms)
            and any(item in lowered for item in effective_terms)
        ):
            asks_when = any(
                item in lowered
                for item in ("什么时候生效", "何时生效", "生效时间", "几号生效")
            )
            inferred_action = (
                MobileAction.QUERY_PLAN_EFFECTIVE_TIME
                if asks_when
                else MobileAction.QUERY_CURRENT_PLAN
            )
            if not any(item[0] == inferred_action for item in ranked):
                ranked.append((inferred_action, 30, "套餐生效条件"))
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

    def assess_knowledge_coverage(
        self,
        text: str,
        subject: Subject,
        templates: list[KnowledgeTemplate],
    ) -> KnowledgeCoverageDecision:
        # 离线降级只复用确定性匹配；不能在没有模型时假装完成语义判断。
        from intent_recognition_agent.knowledge.matcher import match_knowledge

        match = match_knowledge(text, templates)
        if match is None:
            return KnowledgeCoverageDecision(
                coverage=KnowledgeCoverage.MISSING,
                reason="离线模式下没有确定性知识匹配",
            )
        return KnowledgeCoverageDecision(
            coverage=KnowledgeCoverage.COMPLETE,
            matched_template_id=match.template.template_id,
            confidence=1.0,
            reason="确定性匹配已命中知识模板",
        )

    def normalize_for_knowledge(
        self,
        text: str,
        subject: Subject,
        templates: list[KnowledgeTemplate],
    ) -> KnowledgeNormalization:
        """离线降级：使用受控动作枚举生成可检索的标准化表达。"""

        ranked = self._rank_actions(text)
        if not ranked:
            return KnowledgeNormalization(
                normalized_text=text,
                confidence=0.0,
                reason="本地规则未识别出受控动作，保留原文检索",
            )
        action, confidence_score, expression = ranked[0]
        object_type = OBJECT_BY_ACTION.get(action)
        return KnowledgeNormalization(
            normalized_text=f"{action.value} {text}",
            action=action.value,
            business_object=object_type.value if object_type else None,
            extracted_parameters={},
            confidence=min(1.0, confidence_score / 20),
            reason=f"本地规则命中{expression}",
        )


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
        cancel_number = any(word in normalized for word in ("注销", "销号", "销户", "消除"))
        cancel_package = any(word in normalized for word in ("取消", "退订")) and "流量包" in normalized
        is_5g_fault = "5g" in normalized and any(
            word in normalized
            for word in ("不稳定", "没信号", "无信号", "信号差", "网络问题", "断网")
        )
        if is_5g_fault:
            draft.six_tuple.action.name = MobileAction.HANDLE_5G_NETWORK_PROBLEM
            draft.six_tuple.business_object = BusinessObject(
                type=BusinessObjectType.MOBILE_NETWORK,
                name="5G网络",
            )
            network = draft.six_tuple.context_parameters.network or NetworkContext()
            network.network_type = "5G"
            draft.six_tuple.context_parameters.network = network
        elif cancel_package:
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
            return ResilientIntentTranslator._apply_explicit_parameter_guard(text, draft)
        if cancel_package or cancel_number:
            draft.six_tuple.constraints.confirmation.required = True
        return ResilientIntentTranslator._apply_explicit_parameter_guard(text, draft)

    @staticmethod
    def _apply_explicit_parameter_guard(text: str, draft: TranslationDraft) -> TranslationDraft:
        """User-specified values are facts and must override model/template defaults."""
        price_match = re.search(r"(\d+(?:\.\d+)?)\s*元", text, re.IGNORECASE)
        data_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:gb|g)(?![a-z])", text, re.IGNORECASE)
        time_value = next(
            (
                item
                for item in ("立即生效", "当月生效", "次月生效", "下月生效", "下个月生效")
                if item in text
            ),
            None,
        )
        value = draft.six_tuple
        context = value.context_parameters
        context.user_request = text

        if price_match or data_match:
            product = context.product or ProductContext()
            if price_match:
                product.price_yuan = float(price_match.group(1))
                value.constraints.maximum_charge_yuan = float(price_match.group(1))
            if data_match:
                product.data_gb = float(data_match.group(1))
            context.product = product

        if time_value:
            time_context = context.time or TimeContext()
            time_context.effective_time = time_value
            context.time = time_context

        if value.action.name == MobileAction.ACTIVATE_DATA_PACKAGE and (price_match or data_match):
            specification = []
            if price_match:
                specification.append(f"{float(price_match.group(1)):g}元")
            if data_match:
                specification.append(f"{float(data_match.group(1)):g}GB")
            suffix = f"，{time_value}" if time_value else ""
            value.goal.description = f"为用户办理{''.join(specification)}流量包{suffix}"
        return draft

    def decompose(self, text: str, subject: Subject) -> IntentPlanDraft:
        if self.primary is not None:
            try:
                plan = self._normalize_plan(self.primary.decompose(text, subject), text)
                fallback_plan = self.fallback.decompose(text, subject)
                if self._prefer_deterministic_plan(plan, fallback_plan):
                    logger.info("规则计划识别出更完整的多任务，覆盖模型任务计划")
                    return fallback_plan
                return plan
            except Exception:
                logger.warning("大模型意图分解失败，已降级使用规则拆分", exc_info=True)
                pass
        return self.fallback.decompose(text, subject)

    @staticmethod
    def _prefer_deterministic_plan(
        model_plan: IntentPlanDraft,
        fallback_plan: IntentPlanDraft,
    ) -> bool:
        """规则能明确识别更多业务动作时，避免模型漏拆导致任务丢失。"""
        fallback_is_actionable = bool(fallback_plan.tasks) and all(
            task.action_hint for task in fallback_plan.tasks
        )
        if not fallback_is_actionable:
            return False
        model_has_unknown_action = any(not task.action_hint for task in model_plan.tasks)
        return model_has_unknown_action or len(fallback_plan.tasks) > len(model_plan.tasks)

    @staticmethod
    def _normalize_plan(plan: IntentPlanDraft, original: str) -> IntentPlanDraft:
        """修正模型遗漏的序号/依赖，避免前端和调度器收到不一致计划。"""
        ordered = sorted(plan.tasks, key=lambda item: item.sequence)
        id_map: dict[str, str] = {}
        tasks: list[IntentTaskDraft] = []
        for index, item in enumerate(ordered, 1):
            new_id = f"task-{index}"
            id_map[item.task_id] = new_id
            tasks.append(item.model_copy(update={"task_id": new_id, "sequence": index}))
        for index, item in enumerate(tasks):
            dependencies = [id_map.get(dep, dep) for dep in item.depends_on if dep != item.task_id]
            if index > 0 and not dependencies and re.search(r"\u7136\u540E|\u4E4B\u540E|\u63A5\u7740|\u518D", original):
                dependencies = [tasks[index - 1].task_id]
            tasks[index] = item.model_copy(update={"depends_on": list(dict.fromkeys(dependencies))})
        return IntentPlanDraft(tasks=tasks)

    def translate(self, text: str, subject: Subject, knowledge_match: KnowledgeMatch | None = None) -> TranslationDraft:
        if self.primary is not None:
            try:
                draft = self.primary.translate(text, subject, knowledge_match)
                return self._apply_explicit_action_guard(text, draft)
            except Exception:
                logger.warning("大模型意图识别失败，已降级使用规则识别", exc_info=True)
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

    def assess_knowledge_coverage(
        self,
        text: str,
        subject: Subject,
        templates: list[KnowledgeTemplate],
    ) -> KnowledgeCoverageDecision:
        decision: KnowledgeCoverageDecision
        if self.primary is not None:
            try:
                decision = self.primary.assess_knowledge_coverage(text, subject, templates)
            except Exception:
                logger.warning("大模型知识覆盖判断失败，已降级使用确定性匹配", exc_info=True)
                decision = self.fallback.assess_knowledge_coverage(text, subject, templates)
        else:
            decision = self.fallback.assess_knowledge_coverage(text, subject, templates)

        # 语义相似不等于业务动作相同。例如“5G没信号”不能复用
        # “电话打不出去”的通话故障模板。确定性动作能识别时，以动作一致性兜底。
        ranked = self.fallback._rank_actions(text)
        if decision.matched_template_id and ranked:
            top_score = ranked[0][1]
            expected_actions = {
                action for action, score, _ in ranked if score == top_score
            }
            matched = next(
                (
                    item
                    for item in templates
                    if item.template_id == decision.matched_template_id
                ),
                None,
            )
            if matched is not None and matched.six_tuple.action.name not in expected_actions:
                return KnowledgeCoverageDecision(
                    coverage=KnowledgeCoverage.MISSING,
                    matched_template_id=None,
                    confidence=0.0,
                    reason=(
                        "语义候选的业务动作与用户请求不一致："
                        f"请求={ranked[0][0].value}，候选={matched.six_tuple.action.name.value}"
                    ),
                )
        return decision

    def normalize_for_knowledge(
        self,
        text: str,
        subject: Subject,
        templates: list[KnowledgeTemplate],
    ) -> KnowledgeNormalization:
        if self.primary is not None:
            try:
                return self.primary.normalize_for_knowledge(text, subject, templates)
            except Exception:
                logger.warning("大模型知识检索标准化失败，已降级使用本地标准化", exc_info=True)
        return self.fallback.normalize_for_knowledge(text, subject, templates)
