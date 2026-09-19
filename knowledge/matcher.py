"""将用户输入确定性匹配到已经审核的知识模板。"""

import re
import unicodedata

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeMatch,
    KnowledgeMatchType,
    KnowledgeTemplate,
)
from intent_recognition_agent.knowledge.runtime_slots import parameterize_utterance


MOBILE_NUMBER_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)")
NON_WORD_PATTERN = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")


def redact_mobile_numbers(text: str) -> str:
    """写入知识前屏蔽完整手机号。"""

    return MOBILE_NUMBER_PATTERN.sub(r"\1****\3", text)


def normalize_utterance(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", redact_mobile_numbers(text)).lower()
    return NON_WORD_PATTERN.sub("", normalized)


def normalize_intent_pattern(text: str) -> str:
    """把通用业务参数替换为槽位，得到可复用的表达模式。"""

    return parameterize_utterance(text)


def match_knowledge(
    utterance: str,
    templates: list[KnowledgeTemplate],
) -> KnowledgeMatch | None:
    """按精确表达、审核别名、关键词依次匹配活动模板。"""

    normalized = normalize_utterance(utterance)
    active = [template for template in templates if template.status.value == "active"]

    for template in active:
        if normalized == template.normalized_utterance:
            return KnowledgeMatch(
                template=template,
                match_type=KnowledgeMatchType.EXACT,
                matched_expression=template.canonical_utterance,
            )

    for template in active:
        for alias in template.aliases:
            if normalized == normalize_utterance(alias):
                return KnowledgeMatch(
                    template=template,
                    match_type=KnowledgeMatchType.ALIAS,
                    matched_expression=alias,
                )

    pattern = normalize_intent_pattern(utterance)
    for template in active:
        expressions = [template.canonical_utterance, *template.aliases]
        for expression in expressions:
            if pattern == normalize_intent_pattern(expression):
                return KnowledgeMatch(
                    template=template,
                    match_type=KnowledgeMatchType.PARAMETERIZED,
                    matched_expression=expression,
                )

    keyword_matches: list[KnowledgeTemplate] = []
    for template in active:
        required = [normalize_utterance(word) for word in template.match_keywords]
        excluded = [normalize_utterance(word) for word in template.excluded_keywords]
        if required and all(word in normalized for word in required):
            if not any(word in normalized for word in excluded):
                keyword_matches.append(template)

    if len(keyword_matches) == 1:
        template = keyword_matches[0]
        return KnowledgeMatch(
            template=template,
            match_type=KnowledgeMatchType.KEYWORDS,
            matched_expression=" + ".join(template.match_keywords),
        )

    return None
