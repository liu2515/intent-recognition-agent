"""HTTP请求和响应模型。"""

from pydantic import BaseModel, ConfigDict, Field

from intent_recognition_agent.domain.hitl_models import HITLAnswer
from intent_recognition_agent.domain.six_tuple import IntentSixTuple, Subject


class KnowledgeCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utterance: str = Field(min_length=1)
    six_tuple: IntentSixTuple
    created_by: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    match_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)


class KnowledgeReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1)
    reason: str | None = None


class KnowledgeMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    subject: Subject


class IntentStartRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "text": "给我办理30元10GB流量包，下月生效",
                    "user_id": "zhangsan",
                    "subject": {
                        "user_id": "zhangsan",
                        "username": "张三",
                        "role": "本人",
                        "mobile_number": "13955546332",
                    },
                }
            ]
        },
    )

    text: str = Field(min_length=1, max_length=8000)
    user_id: str = Field(min_length=1)
    thread_id: str | None = None
    session_id: str | None = None
    subject: Subject | None = None


class IntentResumeRequest(HITLAnswer):
    user_id: str = Field(min_length=1)


class IntentSixTupleExportRequest(BaseModel):
    """Request a JSON-only six-tuple for a downstream component."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"user_id": "zhangsan", "task_id": "task-1"}],
        },
    )

    user_id: str = Field(min_length=1)
    task_id: str | None = None
