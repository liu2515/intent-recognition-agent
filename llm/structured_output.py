"""模型结构化输出解析与校验。"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from intent_recognition_agent.domain.translation_models import TranslationDraft


class StructuredOutputError(ValueError):
    """模型返回值无法转换成意图草稿。"""


def parse_translation_draft(value: Any) -> TranslationDraft:
    if isinstance(value, TranslationDraft):
        return value
    if hasattr(value, "content"):
        value = value.content
    if isinstance(value, dict):
        return TranslationDraft.model_validate(value)
    if not isinstance(value, str):
        raise StructuredOutputError(f"不支持的模型输出类型: {type(value).__name__}")

    text = value.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        payload = json.loads(text)
        return TranslationDraft.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise StructuredOutputError(f"模型没有返回合法的意图结构: {exc}") from exc
