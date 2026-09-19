"""模型推理阶段允许调用的只读知识工具。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool, tool

from intent_recognition_agent.knowledge.matcher import match_knowledge


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def create_read_only_tools(repository: Any) -> list[BaseTool]:
    """根据当前知识仓库创建工具；所有工具都没有写操作。"""

    @tool
    def search_active_intent_knowledge(query: str) -> str:
        """检索已审核生效的移动业务意图知识模板。"""

        templates = repository.list_active()
        match = match_knowledge(query, templates)
        if match is not None:
            return _json({"matched": True, "match": match.model_dump(mode="json")})
        normalized = query.lower().replace(" ", "")
        candidates = [
            item.model_dump(mode="json")
            for item in templates
            if item.six_tuple.action.name.value in query
            or any(keyword.lower().replace(" ", "") in normalized for keyword in item.match_keywords)
        ][:5]
        return _json({"matched": False, "candidates": candidates})

    @tool
    def query_business_objects(action: str = "") -> str:
        """查询某个移动业务动作已有的业务对象定义。"""

        items = []
        for template in repository.list_active():
            current_action = template.six_tuple.action.name.value
            if action and action not in current_action and current_action not in action:
                continue
            business_object = template.six_tuple.business_object
            if business_object is not None:
                items.append(
                    {
                        "action": current_action,
                        "object": business_object.model_dump(mode="json"),
                        "template_id": template.template_id,
                    }
                )
        return _json({"items": items[:20]})

    @tool
    def query_business_constraints(action: str) -> str:
        """查询某个移动业务动作已有的约束、确认要求和目标判据。"""

        items = []
        for template in repository.list_active():
            current_action = template.six_tuple.action.name.value
            if action not in current_action and current_action not in action:
                continue
            items.append(
                {
                    "action": current_action,
                    "constraints": template.six_tuple.constraints.model_dump(mode="json"),
                    "goal": template.six_tuple.goal.model_dump(mode="json"),
                    "template_id": template.template_id,
                }
            )
        return _json({"items": items[:10]})

    @tool
    def query_product_options(
        action: str,
        price_yuan: float | None = None,
        data_gb: float | None = None,
    ) -> str:
        """查询某项业务的可选产品规格；适用于套餐名称、金额、流量、合约期等信息不明确时。"""

        items = []
        for template in repository.list_active():
            current_action = template.six_tuple.action.name.value
            if action not in current_action and current_action not in action:
                continue
            product = template.six_tuple.context_parameters.product
            if product is None:
                continue
            if price_yuan is not None and product.price_yuan not in {None, price_yuan}:
                continue
            if data_gb is not None and product.data_gb not in {None, data_gb}:
                continue
            items.append(
                {
                    "action": current_action,
                    "product": product.model_dump(mode="json"),
                    "template_id": template.template_id,
                }
            )
        return _json(
            {
                "query": {"action": action, "price_yuan": price_yuan, "data_gb": data_gb},
                "items": items[:10],
            }
        )

    @tool
    def query_effective_time_policy(action: str, effective_time: str) -> str:
        """查询业务的生效时间规则；适用于立即生效、下月生效、指定日期生效等时间诉求。"""

        items = []
        for template in repository.list_active():
            current_action = template.six_tuple.action.name.value
            if action not in current_action and current_action not in action:
                continue
            time_context = template.six_tuple.context_parameters.time
            time_constraints = [
                constraint.model_dump(mode="json")
                for constraint in template.six_tuple.constraints.hard
                if "time" in constraint.target.lower()
                or "生效" in constraint.description
                or "生效" in constraint.code
            ]
            items.append(
                {
                    "action": current_action,
                    "requested_effective_time": effective_time,
                    "template_time": time_context.model_dump(mode="json") if time_context else None,
                    "time_constraints": time_constraints,
                    "template_id": template.template_id,
                }
            )
        return _json({"items": items[:10]})

    @tool
    def query_service_requirements(action: str) -> str:
        """查询办理前置条件、实名/授权校验、用户确认和必填结果字段；适用于判断是否可办理。"""

        items = []
        for template in repository.list_active():
            current_action = template.six_tuple.action.name.value
            if action not in current_action and current_action not in action:
                continue
            constraints = template.six_tuple.constraints
            items.append(
                {
                    "action": current_action,
                    "identity_verification_required": constraints.identity_verification_required,
                    "authorization_required": constraints.authorization_required,
                    "confirmation_required": constraints.confirmation.required,
                    "hard_constraints": [
                        item.model_dump(mode="json") for item in constraints.hard
                    ],
                    "required_result_fields": template.six_tuple.goal.required_result_fields,
                    "template_id": template.template_id,
                }
            )
        return _json({"items": items[:10]})

    return [
        search_active_intent_knowledge,
        query_business_objects,
        query_business_constraints,
        query_product_options,
        query_effective_time_policy,
        query_service_requirements,
    ]
