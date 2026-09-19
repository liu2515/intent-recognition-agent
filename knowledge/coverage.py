"""判断知识是完全命中、部分命中还是未命中。"""

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeCoverage,
    KnowledgeMatch,
    KnowledgeMatchType,
)


def evaluate_coverage(match: KnowledgeMatch | None) -> KnowledgeCoverage:
    if match is None:
        return KnowledgeCoverage.MISSING
    if match.match_type in (
        KnowledgeMatchType.EXACT,
        KnowledgeMatchType.ALIAS,
        KnowledgeMatchType.PARAMETERIZED,
        KnowledgeMatchType.SEMANTIC,
    ):
        return KnowledgeCoverage.COMPLETE
    return KnowledgeCoverage.PARTIAL
