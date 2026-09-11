"""意图识别结果及三种转译模式的数据模型。"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from intent_recognition_agent.domain.six_tuple import IntentSixTuple


class TranslationMode(str, Enum):
    RULE = "rule"
    HYBRID = "hybrid"
    LLM = "llm"


class IntentStatus(str, Enum):
    PROCESSING = "processing"
    NEEDS_CLARIFICATION = "needs_clarification"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    COMPLETED = "completed"
    INVALID = "invalid"
    CANCELLED = "cancelled"


class EvidenceItem(BaseModel):
    """结构化字段对应的原文证据或知识来源。"""

    model_config = ConfigDict(extra="forbid")

    field_path: str
    source: Literal["user", "context", "knowledge", "inference"] = "user"
    source_text: str | None = None
    knowledge_id: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class IntentHypothesis(BaseModel):
    """在请求存在歧义时保留的候选动作。"""

    model_config = ConfigDict(extra="forbid")

    action: str
    confidence: float = Field(ge=0, le=1)
    reason: str | None = None


class TranslationDraft(BaseModel):
    """模型或规则产生的可校验草稿。"""

    model_config = ConfigDict(extra="forbid")

    six_tuple: IntentSixTuple
    evidence: list[EvidenceItem] = Field(default_factory=list)
    hypotheses: list[IntentHypothesis] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    ambiguous_fields: list[str] = Field(default_factory=list)


class IntentRecognitionResult(BaseModel):
    """对外返回的无损请求信封与结构化识别结果。"""

    model_config = ConfigDict(extra="forbid")

    thread_id: str
    user_id: str
    original_input: str
    normalized_input: str
    status: IntentStatus
    translation_mode: TranslationMode | None = None
    six_tuple: IntentSixTuple | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    hypotheses: list[IntentHypothesis] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    ambiguous_fields: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    hitl_question: str | None = None
    knowledge_coverage: str | None = None
    matched_template_id: str | None = None
    revision: int = 0
    knowledge_candidate_id: str | None = None
    knowledge_writeback_status: str | None = None
