"""查询与当前用户需求有关的业务意图知识。"""

from collections import OrderedDict
from collections.abc import Callable
from threading import RLock

from intent_recognition_agent.domain.knowledge_models import (
    KnowledgeCoverage,
    KnowledgeMatch,
    KnowledgeMatchType,
    KnowledgeNormalization,
    KnowledgeTemplate,
)
from intent_recognition_agent.domain.intent_state import IntentAgentState
from intent_recognition_agent.knowledge.matcher import (
    match_knowledge,
    normalize_utterance,
)
from intent_recognition_agent.knowledge.repository import KnowledgeRepository
from intent_recognition_agent.domain.six_tuple import Subject
from intent_recognition_agent.llm.client import IntentTranslator


NORMALIZATION_CANDIDATE_LIMIT = 8
NORMALIZATION_CACHE_SIZE = 128


def _template_fingerprint(templates: list[KnowledgeTemplate]) -> tuple[tuple[object, ...], ...]:
    """生成随知识内容变化的缓存版本，删除或更新模板后自动失效。"""

    return tuple(
        (
            item.template_id,
            item.version,
            item.normalized_utterance,
            tuple(item.aliases),
            tuple(item.match_keywords),
            item.six_tuple.action.name.value,
        )
        for item in templates
    )


def _normalization_candidates(
    query: str,
    templates: list[KnowledgeTemplate],
) -> list[KnowledgeTemplate]:
    """仅把与原文存在词面线索的少量模板发送给模型。"""

    normalized_query = normalize_utterance(query)
    ranked: list[tuple[int, int, KnowledgeTemplate]] = []
    for index, template in enumerate(templates):
        business_object = template.six_tuple.business_object
        expressions = [
            template.canonical_utterance,
            *template.aliases,
            *template.match_keywords,
            template.six_tuple.action.name.value,
            business_object.type.value if business_object else "",
            business_object.name if business_object else "",
        ]
        score = 0
        for expression in expressions:
            normalized_expression = normalize_utterance(expression or "")
            if not normalized_expression:
                continue
            if normalized_expression in normalized_query:
                score += 3
            elif normalized_query and normalized_query in normalized_expression:
                score += 1
        ranked.append((score, -index, template))

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    positive = [item[2] for item in ranked if item[0] > 0]
    selected = positive or [item[2] for item in ranked]
    return selected[:NORMALIZATION_CANDIDATE_LIMIT]


def create_retrieve_knowledge_node(
    repository: KnowledgeRepository,
    translator: IntentTranslator | None = None,
) -> Callable[[IntentAgentState], IntentAgentState]:
    normalization_cache: OrderedDict[
        tuple[str, tuple[tuple[object, ...], ...]],
        KnowledgeNormalization,
    ] = OrderedDict()
    cache_lock = RLock()

    def retrieve_knowledge(state: IntentAgentState) -> IntentAgentState:
        templates = repository.list_active()
        original_query = state["normalized_input"]
        # 精确、别名、参数化和唯一关键词匹配都是毫秒级操作。已有规则能够
        # 覆盖时直接返回，绝不能为了“标准化”先阻塞一次模型请求。
        match = match_knowledge(original_query, templates)
        result: IntentAgentState = {
            "matched_template": match.model_dump(mode="json") if match else None,
            "knowledge_hits": [match.model_dump(mode="json")] if match else [],
        }
        if match is not None or not templates or translator is None:
            if match is not None:
                result["knowledge_normalization"] = {
                    "normalized_text": original_query,
                    "confidence": 1.0,
                    "reason": "确定性知识规则已命中，已跳过模型标准化",
                    "skipped": True,
                    "cache_hit": False,
                }
            return result

        subject = Subject.model_validate(state.get("subject") or {})
        candidate_templates = _normalization_candidates(original_query, templates)
        normalize = getattr(translator, "normalize_for_knowledge", None)
        if normalize is not None:
            cache_key = (original_query, _template_fingerprint(candidate_templates))
            with cache_lock:
                normalization = normalization_cache.get(cache_key)
                if normalization is not None:
                    normalization_cache.move_to_end(cache_key)
            cache_hit = normalization is not None
            if normalization is None:
                try:
                    normalization = normalize(
                        original_query,
                        subject,
                        candidate_templates,
                    )
                except Exception:
                    # 短超时后立即降级。不要在同一检索节点继续发起第二个
                    # 语义覆盖请求，否则辅助检索又会造成串行阻塞。
                    result["knowledge_normalization"] = {
                        "normalized_text": original_query,
                        "confidence": 0.0,
                        "reason": "知识标准化超时或失败，已回退原文规则匹配",
                        "skipped": False,
                        "cache_hit": False,
                    }
                    return result
                with cache_lock:
                    normalization_cache[cache_key] = normalization
                    normalization_cache.move_to_end(cache_key)
                    while len(normalization_cache) > NORMALIZATION_CACHE_SIZE:
                        normalization_cache.popitem(last=False)

            normalization_payload = normalization.model_dump(mode="json")
            normalization_payload["skipped"] = False
            normalization_payload["cache_hit"] = cache_hit
            result["knowledge_normalization"] = normalization_payload
            normalized_query = normalization.normalized_text.strip()
            if normalized_query and normalized_query != original_query:
                match = match_knowledge(normalized_query, templates)
                if match is not None:
                    result["matched_template"] = match.model_dump(mode="json")
                    result["knowledge_hits"] = [match.model_dump(mode="json")]
                    return result

        assess = getattr(translator, "assess_knowledge_coverage", None)
        if assess is None:
            return result
        try:
            decision = assess(
                original_query,
                subject,
                candidate_templates,
            )
        except Exception:
            # 覆盖判断失败不应阻断识别；后续会进入完整模型路径。
            return result

        result["knowledge_coverage_decision"] = decision.model_dump(mode="json")
        if decision.coverage == KnowledgeCoverage.MISSING or not decision.matched_template_id:
            return result
        template = next(
            (item for item in templates if item.template_id == decision.matched_template_id),
            None,
        )
        if template is None:
            return result
        semantic_match = KnowledgeMatch(
            template=template,
            match_type=KnowledgeMatchType.SEMANTIC,
            matched_expression=decision.reason or "模型语义覆盖判断",
        )
        result["matched_template"] = semantic_match.model_dump(mode="json")
        result["knowledge_hits"] = [semantic_match.model_dump(mode="json")]
        return result

    return retrieve_knowledge
