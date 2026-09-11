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

    return [
        search_active_intent_knowledge,
        query_business_objects,
        query_business_constraints,
    ]
