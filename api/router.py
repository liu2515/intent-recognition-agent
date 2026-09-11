"""聚合意图识别和运行图路由。"""

from fastapi import APIRouter

from intent_recognition_agent.api.graph_routes import router as graph_router
from intent_recognition_agent.api.intent_routes import router as intent_router
from intent_recognition_agent.api.knowledge_routes import router as knowledge_router


router = APIRouter()
router.include_router(intent_router)
router.include_router(graph_router)
router.include_router(knowledge_router)
