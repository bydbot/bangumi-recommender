from typing import Dict, List

from .context import RecommendContext
from .types import RecommendItem, EngineName


def _min_max_normalize(items: List[RecommendItem]) -> List[RecommendItem]:
    if not items:
        return items
    scores = [it.score for it in items]
    s_min, s_max = min(scores), max(scores)
    if s_max == s_min:
        normalized = [0.5] * len(items)
    else:
        normalized = [(s - s_min) / (s_max - s_min) for s in scores]
    for it, ns in zip(items, normalized):
        it.score = ns
    return items


class WeightedFusion:
    def __init__(self, weights: Dict[EngineName, float]):
        self._weights = weights

    def merge(
        self,
        results_by_engine: Dict[EngineName, List[RecommendItem]],
        ctx: RecommendContext,
        top_k: int,
    ) -> List[RecommendItem]:
        merged: Dict[int, RecommendItem] = {}

        for engine_name, items in results_by_engine.items():
            if not items:
                continue
            weight = self._weights.get(engine_name, 0.0)
            if weight == 0.0:
                continue
            normalized = _min_max_normalize(items)
            for it in normalized:
                weighted_score = it.score * weight
                sid = it.subject_id
                if sid not in merged or weighted_score > merged[sid].score:
                    merged[sid] = RecommendItem(
                        rank=0,
                        subject_id=sid,
                        name=it.name,
                        name_cn=it.name_cn,
                        score=weighted_score,
                        source=it.source,
                        is_wished=sid in ctx.wished_subject_ids,
                        reasons=it.reasons,
                        breakdown=it.breakdown,
                        rating_score=it.rating_score,
                    )

        sorted_items = sorted(merged.values(), key=lambda x: x.score, reverse=True)
        for i, it in enumerate(sorted_items[:top_k], start=1):
            it.rank = i
        return sorted_items[:top_k]
