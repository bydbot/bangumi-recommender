from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class EngineName(str, Enum):
    GCN = "gcn"
    ITEMCF = "itemcf"
    CONTENT = "content"
    HOT = "hot"
    LLM = "llm"


@dataclass
class RecommendItem:
    rank: int
    subject_id: int
    name: str
    name_cn: str
    score: float
    source: EngineName
    is_wished: bool = False
    reasons: List[str] = field(default_factory=list)
    breakdown: Dict[str, float] = field(default_factory=dict)
    rating_score: float = 0.0
