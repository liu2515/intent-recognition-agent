"""HITL 补充、确认和恢复请求的数据模型。"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class HITLKind(str, Enum):
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"


class HITLPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: HITLKind
    question: str
    fields: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)


class HITLAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
