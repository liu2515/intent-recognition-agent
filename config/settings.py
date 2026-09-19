"""模型、服务端口和持久化配置。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False, encoding="utf-8")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class IntentSettings:
    """意图识别服务配置，所有字段均允许通过环境变量覆盖。"""

    host: str = os.getenv("INTENT_AGENT_HOST", "127.0.0.1")
    port: int = int(os.getenv("INTENT_AGENT_PORT", "8096"))
    model_name: str = os.getenv("INTENT_MODEL_NAME", os.getenv("MAIN_MODEL_NAME", "qwen-plus"))
    # 意图模型优先使用独立配置；未配置时兼容原有的百炼/远程模型配置。
    api_key: str = os.getenv(
        "INTENT_MODEL_API_KEY",
        os.getenv("DASHSCOPE_API_KEY", ""),
    )
    base_url: str = os.getenv(
        "INTENT_MODEL_BASE_URL",
        os.getenv("DASHSCOPE_BASE_URL", ""),
    ).rstrip("/")
    model_timeout_seconds: float = float(os.getenv("INTENT_MODEL_TIMEOUT", "60"))
    knowledge_model_timeout_seconds: float = float(
        os.getenv("INTENT_KNOWLEDGE_MODEL_TIMEOUT", "15")
    )
    use_llm: bool = _as_bool(os.getenv("INTENT_USE_LLM"), True)
    cors_origins: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv(
            "INTENT_CORS_ORIGINS",
            "http://localhost:3001,http://127.0.0.1:3001",
        ).split(",")
        if item.strip()
    )
    persistence_backend: str = os.getenv(
        "INTENT_PERSISTENCE_BACKEND", "mongodb"
    ).strip().lower()
    mongodb_uri: str = os.getenv(
        "INTENT_MONGODB_URI",
        os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017/?authSource=admin"),
    )
    mongodb_database: str = os.getenv(
        "INTENT_MONGODB_DATABASE", "intent_recognition_db"
    )
    mongodb_timeout_ms: int = int(os.getenv("INTENT_MONGODB_TIMEOUT_MS", "3000"))
    neo4j_enabled: bool = _as_bool(os.getenv("INTENT_NEO4J_ENABLED"), False)
    neo4j_uri: str = os.getenv("INTENT_NEO4J_URI", "neo4j://127.0.0.1:7687")
    neo4j_username: str = os.getenv("INTENT_NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("INTENT_NEO4J_PASSWORD", "")
    neo4j_database: str = os.getenv("INTENT_NEO4J_DATABASE", "neo4j")

    @property
    def llm_available(self) -> bool:
        return self.use_llm and bool(self.api_key and self.base_url and self.model_name)

    @property
    def mongodb_enabled(self) -> bool:
        return self.persistence_backend == "mongodb"


settings = IntentSettings()
