from typing import Dict, List, Optional

from .base import BaseRecommender
from .context import RecommendContext
from .types import EngineName


class RecommendRouter:
    def __init__(self, engines: Dict[EngineName, BaseRecommender]):
        self._engines = engines

    @staticmethod
    def get_engine_names(collection_count: int, in_training_data: bool,
                         available_engines: Optional[set] = None) -> List[EngineName]:
        import config
        if collection_count <= 50:
            names = [EngineName.CONTENT, EngineName.HOT, EngineName.LLM]
        elif in_training_data:
            names = [EngineName.GCN, EngineName.LLM]
        else:
            names = [EngineName.CONTENT, EngineName.ITEMCF, EngineName.LLM]
        if not config.ENABLE_LLM:
            names = [n for n in names if n != EngineName.LLM]
        if available_engines is not None:
            names = [n for n in names if n in available_engines]
        return names

    def route(self, ctx: RecommendContext) -> List[BaseRecommender]:
        names = self.get_engine_names(
            ctx.collection_count, ctx.in_training_data,
            available_engines=set(self._engines.keys()),
        )
        return [self._engines[n] for n in names]
