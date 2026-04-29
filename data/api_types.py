from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class SlimSubject:
    id: int
    name: str = ""
    name_cn: str = ""
    type: int = 0
    rating_score: float = 0.0
    rating_total: int = 0
    images: Dict[str, str] = field(default_factory=dict)
    locked: bool = False
    nsfw: bool = False


@dataclass
class CollectionItem:
    subject_id: int
    name: str = ""
    name_cn: str = ""
    collect_type: int = 0
    rate: Optional[int] = None


@dataclass
class Subject:
    id: int
    name: str = ""
    name_cn: str = ""
    type: int = 0
    summary: str = ""
    meta_tags: List[str] = field(default_factory=list)
    tags: List[Dict[str, Any]] = field(default_factory=list)
    rating_score: float = 0.0
    rating_total: int = 0
    rating_rank: int = 0
    collection_wish: int = 0
    collection_watch: int = 0
    collection_doing: int = 0
    collection_on_hold: int = 0
    collection_dropped: int = 0
    infobox: List[Dict[str, Any]] = field(default_factory=list)
    airtime: Dict[str, Any] = field(default_factory=dict)
    images: Dict[str, str] = field(default_factory=dict)
    nsfw: bool = False


@dataclass
class SeasonalAnime:
    subject_id: int
    name: str
    name_cn: str
    summary: str
    meta_tags: List[str] = field(default_factory=list)
    rating_score: float = 0.0
    rating_total: int = 0
    wish_count: int = 0
    watch_count: int = 0
    airtime_date: str = ""
    airtime_year: int = 0
    airtime_month: int = 0
    season_label: str = ""
    infobox_items: List[Dict] = field(default_factory=list)
    is_completed: bool = False
    crawled_at: str = ""
