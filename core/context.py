from dataclasses import dataclass, field
from typing import List, Dict, Set


@dataclass
class RecommendContext:
    user_id: str
    username: str
    watched_subject_ids: List[int] = field(default_factory=list)
    wished_subject_ids: Set[int] = field(default_factory=set)
    history_ratings: Dict[int, float] = field(default_factory=dict)
    collection_count: int = 0
    in_training_data: bool = False
    gcn_exclude_items: List[int] = field(default_factory=list)
    gcn_new_for_warm: List[int] = field(default_factory=list)
