"""意图识别服务的FastAPI启动入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intent_recognition_agent.api.router import router
from intent_recognition_agent.config.settings import settings
from intent_recognition_agent.services.container import (
    close_resources,
    mongodb_client,
    neo4j_error,
    neo4j_graph,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    close_resources()


app = FastAPI(
    title="中国移动意图识别智能体",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "persistence": "mongodb" if mongodb_client is not None else "memory",
        "neo4j": {
            "enabled": settings.neo4j_enabled,
            "connected": neo4j_graph is not None,
            "error": neo4j_error,
        },
    }
