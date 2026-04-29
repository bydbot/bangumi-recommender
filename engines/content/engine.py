from typing import List

from core.base import BaseRecommender
from core.context import RecommendContext
from core.types import RecommendItem, EngineName
from data.anime_db import get_anime_rating
from .recommender import ContentRecommenderV2


class ContentBasedRecommender(BaseRecommender):
    name = EngineName.CONTENT

    def __init__(self):
        self._recommender = None

    def _load(self):
        if self._recommender is not None:
            return

        self._recommender = ContentRecommenderV2()

    def recommend(self, ctx: RecommendContext, top_k: int) -> List[RecommendItem]:
        try:
            self._load()
        except Exception as e:
            print(f"[content] 加载失败，返回空结果: {e}")
            return []

        watched = {}
        for sid in ctx.watched_subject_ids:
            if sid in ctx.history_ratings:
                watched[sid] = ctx.history_ratings[sid]
            else:
                rating = get_anime_rating(sid)
                if rating > 0:
                    watched[sid] = rating
                else:
                    watched[sid] = 1.0

        wished = list(ctx.wished_subject_ids)

        try:
            raw = self._recommender.recommend(
                watched=watched,
                wished=wished,
                top_k=top_k,
            )
        except Exception as e:
            print(f"[content] 推荐失败: {e}")
            return []

        results = []
        for i, item in enumerate(raw, start=1):
            results.append(
                RecommendItem(
                    rank=i,
                    subject_id=item.get("subject_id", 0),
                    name=item.get("name", ""),
                    name_cn=item.get("name_cn", ""),
                    score=round(item.get("score", 0.0), 4),
                    source=EngineName.CONTENT,
                    reasons=item.get("reasons", []),
                    breakdown=item.get("breakdown", {}),
                    rating_score=get_anime_rating(item.get("subject_id", 0)),
                )
            )
        return results
