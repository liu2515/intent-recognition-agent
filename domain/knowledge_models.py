"""知识模板、匹配证据和知识生命周期数据模型。"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from intent_recognition_agent.domain.six_tuple import IntentSixTuple


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"


class KnowledgeMatchType(str, Enum):
    EXACT = "exact"
    ALIAS = "alias"
    KEYWORDS = "keywords"


class KnowledgeCoverage(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class KnowledgeRelation(str, Enum):
    PERFORMED_BY = "PERFORMED_BY"
    ACTS_ON = "ACTS_ON"
    HAS_PARAMETER = "HAS_PARAMETER"
    HAS_CONSTRAINT = "HAS_CONSTRAINT"
    ACHIEVES = "ACHIEVES"


class KnowledgeTriple(BaseModel):
    """可直接导入图数据库的业务知识三元组。"""

    model_config = ConfigDict(extra="forbid")

    subject: str
    predicate: KnowledgeRelation
    object: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class KnowledgeTemplate(BaseModel):
    """由已确认六元组提炼出的可复用知识模板。"""

    model_config = ConfigDict(extra="forbid")

    template_id: str
    version: int = Field(default=1, ge=1)
    status: KnowledgeStatus = KnowledgeStatus.PENDING
    canonical_utterance: str
    normalized_utterance: str
    aliases: list[str] = Field(default_factory=list)
    match_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    six_tuple: IntentSixTuple
    triples: list[KnowledgeTriple] = Field(default_factory=list)
    origin: str = "llm"
    created_by: str
    created_at: datetime = Field(default_factory=utc_now)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None

    @field_validator("aliases", "match_keywords", "excluded_keywords")
    @classmethod
    def remove_duplicate_strings(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class KnowledgeMatch(BaseModel):
    """一次知识匹配结果。"""

    model_config = ConfigDict(extra="forbid")

    template: KnowledgeTemplate
    match_type: KnowledgeMatchType
    matched_expression: str
