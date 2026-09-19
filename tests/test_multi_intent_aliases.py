"""覆盖多任务口语表达的规则降级行为。"""

from __future__ import annotations

import unittest

from intent_recognition_agent.domain.six_tuple import MobileAction, Subject
from intent_recognition_agent.domain.translation_models import IntentPlanDraft
from intent_recognition_agent.llm.client import HeuristicIntentTranslator
from intent_recognition_agent.services.intent_service import IntentService


class MultiIntentAliasTests(unittest.TestCase):
    def test_remove_current_number_and_apply_new_number_are_split_and_recognized(self) -> None:
        text = "给我消除当前手机号，并办理新的手机号"
        translator = HeuristicIntentTranslator()

        self.assertTrue(IntentService._looks_multi_intent(text))

        plan = translator.decompose(text, Subject(user_id="zhangsan"))
        self.assertEqual([task.text for task in plan.tasks], ["给我消除当前手机号", "办理新的手机号"])
        self.assertEqual(
            [task.action_hint for task in plan.tasks],
            [MobileAction.CANCEL_MOBILE_NUMBER.value, MobileAction.APPLY_MOBILE_CARD.value],
        )

        actions = [translator.translate(task.text, Subject()).six_tuple.action.name for task in plan.tasks]
        self.assertEqual(actions, [MobileAction.CANCEL_MOBILE_NUMBER, MobileAction.APPLY_MOBILE_CARD])

    def test_numeric_model_task_identifiers_are_normalized_to_strings(self) -> None:
        plan = IntentPlanDraft.model_validate(
            {
                "tasks": [
                    {
                        "task_id": 1,
                        "sequence": 1,
                        "text": "办理新的手机号",
                        "depends_on": [0],
                    }
                ]
            }
        )

        self.assertEqual(plan.tasks[0].task_id, "1")
        self.assertEqual(plan.tasks[0].depends_on, ["0"])


if __name__ == "__main__":
    unittest.main()
