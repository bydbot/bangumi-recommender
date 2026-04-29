from typing import List

from core.base import BaseRecommender
from core.context import RecommendContext
from core.types import RecommendItem, EngineName
from data.db import get_hot_items
from data.anime_db import get_anime_name, get_anime_rating


class HotRecommender(BaseRecommender):
    name = EngineName.HOT

    def __init__(self, min_rating_count: int = 30):
        self._min_rating_count = min_rating_count

    def recommend(self, ctx: RecommendContext, top_k: int) -> List[RecommendItem]:
        hot_items = get_hot_items(top_k=top_k, min_rating_count=self._min_rating_count)
        results = []
        for i, (subject_id, score) in enumerate(hot_items, start=1):
            results.append(
                RecommendItem(
                    rank=i,
                    subject_id=subject_id,
                    name=get_anime_name(subject_id),
                    name_cn=get_anime_name(subject_id),
                    score=round(score, 4),
                    source=EngineName.HOT,
                    rating_score=get_anime_rating(subject_id),
                )
            )
        return results
