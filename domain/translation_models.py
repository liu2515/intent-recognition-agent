"""意图识别结果及三种转译模式的数据模型。"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from intent_recognition_agent.domain.six_tuple import IntentSixTuple


class TranslationMode(str, Enum):
    RULE = "rule"
    HYBRID = "hybrid"
    LLM = "llm"


class TaskStatus(str, Enum):
    """多任务计划中单项任务的生命周期状态。"""

    PENDING = "pending"
    PROCESSING = "processing"
    NEEDS_CLARIFICATION = "needs_clarification"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    COMPLETED = "completed"
    INVALID = "invalid"
    CANCELLED = "cancelled"


class IntentTaskDraft(BaseModel):
    """任务分解阶段的轻量输出；六元组在后续按任务独立生成。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    text: str = Field(min_length=1)
    action_hint: str | None = None
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("task_id", mode="before")
    @classmethod
    def coerce_task_id(cls, value: object) -> str:
        """兼容部分模型把 task_id 返回为数字的情况。"""
        return str(value)

    @field_validator("depends_on", mode="before")
    @classmethod
    def coerce_dependencies(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        return [str(item) for item in value]


class IntentPlanDraft(BaseModel):
    """大模型一次调用返回的原子任务计划。"""

    model_config = ConfigDict(extra="forbid")

    tasks: list[IntentTaskDraft] = Field(min_length=1, max_length=8)


class IntentTaskResult(BaseModel):
    """对外返回的单项任务结果，沿用现有六元组结构。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    sequence: int
    text: str
    action_hint: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PROCESSING
    thread_id: str | None = None
    six_tuple: IntentSixTuple | None = None
    evidence: list["EvidenceItem"] = Field(default_factory=list)
    hypotheses: list["IntentHypothesis"] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    ambiguous_fields: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    hitl_question: str | None = None
    trace: list[dict[str, object]] = Field(default_factory=list)


class IntentPlanResult(BaseModel):
    """多任务识别结果；单任务时 tasks 为空以保持旧接口兼容。"""

    model_config = ConfigDict(extra="forbid")

    plan_id: str | None = None
    is_multi_intent: bool = False
    tasks: list[IntentTaskResult] = Field(default_factory=list)


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
    plan_id: str | None = None
    is_multi_intent: bool = False
    tasks: list[IntentTaskResult] = Field(default_factory=list)


# EvidenceItem/IntentHypothesis are declared below IntentTaskResult for backwards
# compatible module layout; resolve those forward references after import.
IntentTaskResult.model_rebuild()
