"""知识模板应跨显式参数值复用，同时保留当前请求参数。"""

from __future__ import annotations

import unittest

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeMatchType,
    KnowledgeStatus,
    KnowledgeTemplate,
)
from intent_recognition_agent.domain.six_tuple import IntentSixTuple, Subject
from intent_recognition_agent.knowledge.coverage import evaluate_coverage
from intent_recognition_agent.knowledge.matcher import match_knowledge, normalize_utterance
from intent_recognition_agent.knowledge.rule_translator import translate_by_rule
from intent_recognition_agent.knowledge.runtime_slots import (
    extract_runtime_slots,
    parameterize_utterance,
)


class ParameterizedKnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        six_tuple = IntentSixTuple.model_validate(
            {
                "subject": {"role": "本人"},
                "action": "办理流量包",
                "business_object": {"type": "流量包", "name": "流量包"},
                "context_parameters": {
                    "time": {"effective_time": "下月生效"},
                    "product": {"price_yuan": 20, "data_gb": 10},
                },
                "constraints": {"maximum_charge_yuan": 20},
                "goal": {"description": "办理20元10GB流量包，下月生效"},
            }
        )
        expression = "给我办理20元10GB流量包，下月生效"
        self.template = KnowledgeTemplate(
            template_id="parameterized-data-package",
            status=KnowledgeStatus.ACTIVE,
            canonical_utterance=expression,
            normalized_utterance=normalize_utterance(expression),
            match_keywords=["办理流量包"],
            six_tuple=six_tuple,
            created_by="test-user",
        )

    def test_changed_price_and_time_are_complete_parameterized_match(self) -> None:
        utterance = "给我办理30元10GB流量包，立即生效"
        match = match_knowledge(utterance, [self.template])

        self.assertIsNotNone(match)
        self.assertEqual(match.match_type, KnowledgeMatchType.PARAMETERIZED)
        self.assertEqual(evaluate_coverage(match).value, "complete")

    def test_rule_translation_uses_current_request_parameters(self) -> None:
        utterance = "给我办理30元15GB流量包，立即生效"
        match = match_knowledge(utterance, [self.template])
        result = translate_by_rule(match, Subject(user_id="zhangsan"), utterance)

        self.assertEqual(result.context_parameters.product.price_yuan, 30)
        self.assertEqual(result.context_parameters.product.data_gb, 15)
        self.assertEqual(result.context_parameters.time.effective_time, "立即生效")
        self.assertEqual(result.constraints.maximum_charge_yuan, 30)
        self.assertEqual(result.context_parameters.user_request, utterance)
        self.assertIn("30元15GB", result.goal.description)

    def test_broadband_slots_are_not_tied_to_specific_values(self) -> None:
        first = "请帮我办理100M宽带，合约1年，北京"
        second = "我要申请500M宽带，合同2年，上海"

        self.assertEqual(parameterize_utterance(first), parameterize_utterance(second))
        slots = extract_runtime_slots("办理500M宽带，合同2年，北京，联系电话13855546925")
        self.assertEqual(slots["bandwidth_mbps"], 500)
        self.assertEqual(slots["contract_months"], 24)
        self.assertEqual(slots["city"], "北京")
        self.assertEqual(slots["contact_mobile"], "13855546925")

    def test_region_and_network_generation_are_parameterized(self) -> None:
        first = "查询北京5G网络状态"
        second = "查看上海4G网络状态"

        self.assertEqual(parameterize_utterance(first), parameterize_utterance(second))
        slots = extract_runtime_slots(second)
        self.assertEqual(slots["city"], "上海")
        self.assertEqual(slots["network_type"], "4G")


if __name__ == "__main__":
    unittest.main()
