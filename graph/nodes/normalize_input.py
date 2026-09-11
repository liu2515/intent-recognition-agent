"""规范化用户输入并提取可直接确定的实体信息。"""

import re
import unicodedata

from intent_recognition_agent.domain.intent_state import IntentAgentState


SPACE_PATTERN = re.compile(r"\s+")
MOBILE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def normalize_input(state: IntentAgentState) -> IntentAgentState:
    text = unicodedata.normalize("NFKC", state["original_input"]).strip()
    normalized = SPACE_PATTERN.sub(" ", text)
    subject = dict(state.get("subject") or {})
    mobile = MOBILE_PATTERN.search(text)
    if mobile and not subject.get("mobile_number"):
        subject["mobile_number"] = mobile.group(0)
    return {"normalized_input": normalized, "subject": subject}
