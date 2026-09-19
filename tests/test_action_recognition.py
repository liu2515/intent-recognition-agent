"""本地降级识别应支持常见的中文动作/对象语序。"""

from __future__ import annotations

import unittest

from intent_recognition_agent.domain.six_tuple import MobileAction, Subject
from intent_recognition_agent.llm.client import HeuristicIntentTranslator


class ActionRecognitionTests(unittest.TestCase):
    def test_cancel_mobile_number_with_object_before_verb(self) -> None:
        text = "我希望将当前手机号注销了"
        result = HeuristicIntentTranslator().translate(
            text,
            Subject(user_id="zhangsan", username="张三"),
        )

        self.assertEqual(result.six_tuple.action.name, MobileAction.CANCEL_MOBILE_NUMBER)

    def test_cancel_data_package_with_object_before_verb(self) -> None:
        text = "这个流量包我想退订"
        result = HeuristicIntentTranslator().translate(
            text,
            Subject(user_id="zhangsan", username="张三"),
        )

        self.assertEqual(result.six_tuple.action.name, MobileAction.CANCEL_DATA_PACKAGE)

    def test_charge_question_with_intervening_month_and_amount(self) -> None:
        text = "为什么这个月多扣了50元"
        result = HeuristicIntentTranslator().translate(
            text,
            Subject(user_id="zhangsan", username="张三"),
        )

        self.assertEqual(result.six_tuple.action.name, MobileAction.EXPLAIN_CHARGE)

    def test_call_failure_with_sms_still_normalizes_to_call_problem(self) -> None:
        text = "电话打不出去，但是短信正常"
        result = HeuristicIntentTranslator().translate(
            text,
            Subject(user_id="zhangsan", username="张三"),
        )

        self.assertEqual(result.six_tuple.action.name, MobileAction.HANDLE_CALL_PROBLEM)


if __name__ == "__main__":
    unittest.main()
