import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List

import config
from core.fusion import WeightedFusion
from core.types import RecommendItem, EngineName


def _now_iso() -> str:
    return datetime.now().isoformat()


def _is_expired(created_at: str, ttl_hours: int) -> bool:
    try:
        dt = datetime.fromisoformat(created_at)
        return datetime.now() - dt > timedelta(hours=ttl_hours)
    except (ValueError, TypeError):
        return True


def _determine_engine_combo(collection_count: int, in_training_data: bool, available_engines=None) -> str:
    from core.router import RecommendRouter
    names = RecommendRouter.get_engine_names(
        collection_count, in_training_data,
        available_engines=set(available_engines) if available_engines else None,
    )
    return "+".join(n.value for n in names)


def _item_to_dict(item: RecommendItem) -> dict:
    return {
        "subject_id": item.subject_id,
        "name": item.name,
        "name_cn": item.name_cn,
        "score": item.score,
        "source": item.source.value,
        "reasons": item.reasons,
        "breakdown": item.breakdown,
        "rating_score": item.rating_score,
        "is_wished": item.is_wished,
    }


def _dict_to_item(data: dict) -> RecommendItem:
    return RecommendItem(
        rank=0,
        subject_id=data["subject_id"],
        name=data.get("name", ""),
        name_cn=data.get("name_cn", ""),
        score=data["score"],
        source=EngineName(data["source"]),
        reasons=data.get("reasons", []),
        breakdown=data.get("breakdown", {}),
        rating_score=data.get("rating_score", 0.0),
        is_wished=data.get("is_wished", False),
    )


class EngineCache:
    def __init__(self, db_path=config.RECOMMEND_CACHE_DB, ttl_hours=config.RECOMMEND_CACHE_TTL_HOURS):
        self._db_path = db_path
        self._ttl_hours = ttl_hours
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS engine_cache (
                user_id TEXT NOT NULL,
                engine_name TEXT NOT NULL,
                items_json TEXT NOT NULL,
                created_at TEXT,
                PRIMARY KEY (user_id, engine_name)
            )
        """)
        conn.commit()
        conn.close()

    def save_engine_results(self, user_id: str, engine_name: EngineName, items: List[RecommendItem]):
        top_m = config.CACHE_ENGINE_TOP_M
        top_items = items[:top_m]
        data = [_item_to_dict(it) for it in top_items]
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO engine_cache (user_id, engine_name, items_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, engine_name.value, json.dumps(data, ensure_ascii=False), _now_iso()),
        )
        conn.commit()
        conn.close()

    def load_engine_results(self, user_id: str, engine_names: List[EngineName]) -> Optional[Dict[EngineName, List[RecommendItem]]]:
        conn = sqlite3.connect(self._db_path)
        results = {}
        for name in engine_names:
            row = conn.execute(
                "SELECT items_json, created_at FROM engine_cache WHERE user_id = ? AND engine_name = ?",
                (user_id, name.value),
            ).fetchone()
            if not row:
                conn.close()
                return None
            if _is_expired(row[1], self._ttl_hours):
                conn.close()
                return None
            items_data = json.loads(row[0])
            results[name] = [_dict_to_item(d) for d in items_data]
        conn.close()
        return results

    def clear(self, user_id: str = None):
        conn = sqlite3.connect(self._db_path)
        if user_id:
            conn.execute("DELETE FROM engine_cache WHERE user_id = ?", (user_id,))
        else:
            conn.execute("DELETE FROM engine_cache")
        conn.commit()
        conn.close()


class RecommendCache:
    def __init__(self, db_path=config.RECOMMEND_CACHE_DB, ttl_hours=config.RECOMMEND_CACHE_TTL_HOURS):
        self._engine_cache = EngineCache(db_path, ttl_hours)

    def try_fusion_from_cache(
        self, ctx, top_k: int, weights: Dict[EngineName, float],
        available_engines=None,
    ) -> Optional[Dict]:
        combo = _determine_engine_combo(ctx.collection_count, ctx.in_training_data, available_engines)
        if not combo:
            return None

        engine_names = [EngineName(n) for n in combo.split("+") if n]
        cached_results = self._engine_cache.load_engine_results(ctx.user_id, engine_names)
        if not cached_results:
            return None

        print(f"[cache] 引擎缓存命中，重新融合 top_k={top_k}")
        fusion = WeightedFusion(weights)
        final = fusion.merge(cached_results, ctx, top_k)

        return {
            "user_id": ctx.user_id,
            "source": combo,
            "collection_count": ctx.collection_count,
            "wished_count": len(ctx.wished_subject_ids),
            "in_training_data": ctx.in_training_data,
            "gcn_exclude_items": len(ctx.gcn_exclude_items),
            "gcn_new_for_warm": len(ctx.gcn_new_for_warm),
            "recommendations": [
                {
                    "rank": it.rank,
                    "subject_id": it.subject_id,
                    "name": it.name_cn or it.name,
                    "name_cn": it.name_cn,
                    "score": it.score,
                    "source": it.source.value,
                    "is_wished": it.is_wished,
                    "rating_score": it.rating_score,
                    "reasons": it.reasons,
                }
                for it in final
            ],
        }

    def save_engine_results(self, user_id: str, engine_name: EngineName, items: List[RecommendItem]):
        self._engine_cache.save_engine_results(user_id, engine_name, items)

    def clear(self, user_id: str = None):
        self._engine_cache.clear(user_id)
