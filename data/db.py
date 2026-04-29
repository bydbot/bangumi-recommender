import math
import sqlite3
from datetime import datetime
from typing import List, Tuple

import config


def _time_decay_factor(air_date: str, now: datetime, half_life_days: int) -> float:
    if not air_date:
        return 0.5
    try:
        air_dt = datetime.fromisoformat(air_date)
        days_since = (now - air_dt).days
        if days_since <= 0:
            return 1.0
        return math.exp(-math.log(2) * days_since / half_life_days)
    except (ValueError, TypeError):
        return 0.5


def get_hot_items(top_k: int = 100, min_rating_count: int = 30) -> List[Tuple[int, float]]:
    conn = sqlite3.connect(config.ANIME_META_DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            id as subject_id,
            score,
            favorite_done as watch_count,
            favorite_wish as wish_count,
            date
        FROM anime_entries
        WHERE score > 0
          AND (favorite_done + favorite_wish) >= ?
        ORDER BY (favorite_done + favorite_wish) DESC
        LIMIT ?
    """, (min_rating_count, top_k))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    max_watch = max((r[2] for r in rows), default=1)
    max_wish = max((r[3] for r in rows), default=1)
    max_score = max((r[1] for r in rows), default=1)
    now = datetime.now()
    half_life = config.HOT_TIME_DECAY_HALF_LIFE_DAYS

    results = []
    for sid, score, watch_count, wish_count, air_date in rows:
        decay = _time_decay_factor(air_date, now, half_life)
        norm_score = score / config.HOT_NORMALIZE_RATING_SCALE
        norm_watch = watch_count / max_watch if max_watch > 0 else 0
        norm_wish = wish_count / max_wish if max_wish > 0 else 0
        hot_score = (
            config.HOT_WEIGHT_WISHED * norm_wish
            + config.HOT_WEIGHT_WATCHED * norm_watch
            + config.HOT_WEIGHT_RATING * norm_score
        ) * decay
        results.append((int(sid), hot_score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]
