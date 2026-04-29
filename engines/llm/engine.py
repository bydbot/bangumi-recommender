from typing import List

from core.base import BaseRecommender
from core.context import RecommendContext
from core.types import RecommendItem, EngineName


class LLMRecommender(BaseRecommender):
    name = EngineName.LLM

    def recommend(self, ctx: RecommendContext, top_k: int) -> List[RecommendItem]:
        return []
