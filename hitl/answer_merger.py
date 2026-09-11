"""把用户补充或确认信息合并回意图状态。"""

import re


AFFIRMATIVE_PATTERN = re.compile(
    r"^(?:我)?(?:确认|同意|确定|可以|是的|继续|办理|confirm|yes|approve)[。！!\s]*$",
    re.IGNORECASE,
)
NEGATIVE_PATTERN = re.compile(
    r"^(?:我)?(?:取消|不同意|不要|否|不是|停止|cancel|no|reject)[。！!\s]*$",
    re.IGNORECASE,
)
MOBILE_NUMBER_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def parse_confirmation(answer: str) -> bool | None:
    normalized = answer.strip()
    if AFFIRMATIVE_PATTERN.search(normalized):
        return True
    if NEGATIVE_PATTERN.search(normalized):
        return False
    return None


def merge_clarification_answer(
    subject: dict,
    answer: str,
    requested_fields: list[str],
) -> dict:
    """仅把可确定的补充字段合并为运行时事实，不让模型覆盖主体。"""
    updated = dict(subject)
    if "subject.mobile_number" in requested_fields:
        match = MOBILE_NUMBER_PATTERN.search(answer)
        if match:
            updated["mobile_number"] = match.group(0)
    return updated
