"""应用级共享服务实例。"""

from typing import Any

from intent_recognition_agent.config.settings import settings
from intent_recognition_agent.domain.six_tuple import IntentSixTuple
from intent_recognition_agent.knowledge.mongo_repository import MongoKnowledgeRepository
from intent_recognition_agent.knowledge.neo4j_repository import Neo4jKnowledgeGraph
from intent_recognition_agent.knowledge.repository import KnowledgeRepository
from intent_recognition_agent.knowledge.writeback import KnowledgeWritebackService
from intent_recognition_agent.persistence.checkpointer import create_checkpointer
from intent_recognition_agent.persistence.intent_repository import (
    IntentRepository,
    MongoIntentRepository,
)
from intent_recognition_agent.persistence.mongodb import create_mongodb_client
from intent_recognition_agent.persistence.trace_repository import (
    MongoTraceRepository,
    TraceRepository,
)
from intent_recognition_agent.services.graph_service import GraphService
from intent_recognition_agent.services.intent_service import IntentService
from intent_recognition_agent.services.knowledge_graph_service import KnowledgeGraphService


mongodb_client: Any | None = None
neo4j_graph: Neo4jKnowledgeGraph | None = None
neo4j_error: str | None = None

if settings.mongodb_enabled:
    mongodb_client = create_mongodb_client(
        settings.mongodb_uri,
        settings.mongodb_timeout_ms,
    )
    knowledge_repository = MongoKnowledgeRepository(
        mongodb_client,
        settings.mongodb_database,
    )
    knowledge_repository.migrate_from_json(KnowledgeRepository())
    intent_repository = MongoIntentRepository(
        mongodb_client,
        settings.mongodb_database,
    )
    trace_repository = MongoTraceRepository(
        mongodb_client,
        settings.mongodb_database,
    )
    checkpointer = create_checkpointer(
        mongodb_client,
        database_name=settings.mongodb_database,
    )
else:
    knowledge_repository = KnowledgeRepository()
    intent_repository = IntentRepository()
    trace_repository = TraceRepository()
    checkpointer = create_checkpointer()

if settings.neo4j_enabled:
    candidate_graph: Neo4jKnowledgeGraph | None = None
    try:
        candidate_graph = Neo4jKnowledgeGraph(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )
        candidate_graph.rebuild(knowledge_repository.list_active())
        for completed in intent_repository.list_completed():
            candidate_graph.upsert_runtime_intent(
                thread_id=completed["thread_id"],
                user_id=completed["user_id"],
                six_tuple=IntentSixTuple.model_validate(completed["six_tuple"]),
            )
        neo4j_graph = candidate_graph
    except Exception as exc:
        if candidate_graph is not None:
            candidate_graph.close()
        neo4j_error = str(exc)

intent_service = IntentService(
    repository=knowledge_repository,
    intents=intent_repository,
    traces=trace_repository,
    checkpointer=checkpointer,
    graph_store=neo4j_graph,
)
graph_service = GraphService(trace_repository)
writeback_service = KnowledgeWritebackService(knowledge_repository, neo4j_graph)
knowledge_graph_service = KnowledgeGraphService(
    knowledge_repository,
    neo4j_graph,
    neo4j_error,
)


def close_resources() -> None:
    if neo4j_graph is not None:
        neo4j_graph.close()
    if mongodb_client is not None:
        mongodb_client.close()
