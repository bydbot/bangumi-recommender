import json
from typing import Dict, List, Tuple

from core.base import BaseRecommender
from core.context import RecommendContext
from core.types import RecommendItem, EngineName
from data.anime_db import get_anime_name, get_anime_rating


class ItemCFRecommender(BaseRecommender):
    name = EngineName.ITEMCF

    def __init__(self, sim_path: str):
        self._sim_path = sim_path
        self._sim: Dict[int, List[Tuple[int, float]]] = {}

    def _load_sim(self):
        if self._sim:
            return
        with open(self._sim_path, "r", encoding="utf-8") as f:
            raw: Dict[str, List[Tuple[int, float]]] = json.load(f)
            self._sim = {int(k): [(int(i), float(s)) for i, s in v] for k, v in raw.items()}

    def recommend(self, ctx: RecommendContext, top_k: int) -> List[RecommendItem]:
        self._load_sim()

        history = list(ctx.history_ratings.items())
        if not history:
            return []

        user_mean = sum(r for _, r in history) / len(history)
        seen = set(ctx.watched_subject_ids)

        scores: Dict[int, float] = {}
        for sid, rate in history:
            similar_items = self._sim.get(sid, [])
            for sim_id, sim_score in similar_items:
                if sim_id in seen:
                    continue
                scores[sim_id] = scores.get(sim_id, 0.0) + sim_score * (rate - user_mean)

        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for i, (subject_id, score) in enumerate(sorted_items, start=1):
            results.append(
                RecommendItem(
                    rank=i,
                    subject_id=subject_id,
                    name=get_anime_name(subject_id),
                    name_cn=get_anime_name(subject_id),
                    score=round(score, 4),
                    source=EngineName.ITEMCF,
                    rating_score=get_anime_rating(subject_id),
                )
            )
        return results
