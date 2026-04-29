from abc import ABC, abstractmethod
from typing import List

from .context import RecommendContext
from .types import RecommendItem, EngineName


class BaseRecommender(ABC):
    @abstractmethod
    def recommend(self, ctx: RecommendContext, top_k: int) -> List[RecommendItem]:
        ...

    @property
    @abstractmethod
    def name(self) -> EngineName:
        ...
