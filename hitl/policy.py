"""决定缺失、歧义和高风险场景是否需要人工介入。"""

from intent_recognition_agent.domain.validation import TupleValidationResult


def next_human_action(result: TupleValidationResult) -> str:
    if result.errors:
        return "invalid"
    if result.missing_fields or result.ambiguous_fields:
        return "clarify"
    if result.confirmation_required:
        return "confirm"
    return "complete"
