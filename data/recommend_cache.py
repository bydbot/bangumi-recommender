import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict

import config


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


class RecommendCache:
    def __init__(self, db_path=config.RECOMMEND_CACHE_DB, ttl_hours=config.RECOMMEND_CACHE_TTL_HOURS):
        self._db_path = db_path
        self._ttl_hours = ttl_hours
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recommend_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                engine_combo TEXT NOT NULL,
                top_k INTEGER DEFAULT 100,
                result_json TEXT,
                created_at TEXT,
                UNIQUE(user_id, engine_combo, top_k)
            )
        """)
        conn.commit()
        conn.close()

    def get(self, user_id: str, engine_combo: str, top_k: int) -> Optional[Dict]:
        conn = sqlite3.connect(self._db_path)
        row = conn.execute(
            "SELECT result_json, created_at FROM recommend_cache WHERE user_id = ? AND engine_combo = ? AND top_k = ?",
            (user_id, engine_combo, top_k),
        ).fetchone()
        conn.close()
        if not row:
            return None
        if _is_expired(row[1], self._ttl_hours):
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    def get_for_user(self, ctx, top_k: int, available_engines=None) -> Optional[Dict]:
        combo = _determine_engine_combo(ctx.collection_count, ctx.in_training_data, available_engines)
        return self.get(ctx.user_id, combo, top_k)

    def get_for_user_with_combo(self, ctx, top_k: int, engine_combo: str) -> Optional[Dict]:
        return self.get(ctx.user_id, engine_combo, top_k)

    def set(self, user_id: str, engine_combo: str, top_k: int, result: Dict):
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO recommend_cache (user_id, engine_combo, top_k, result_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, engine_combo, top_k, json.dumps(result, ensure_ascii=False), _now_iso()),
        )
        conn.commit()
        conn.close()

    def clear(self, user_id: str = None):
        conn = sqlite3.connect(self._db_path)
        if user_id:
            conn.execute("DELETE FROM recommend_cache WHERE user_id = ?", (user_id,))
        else:
            conn.execute("DELETE FROM recommend_cache")
        conn.commit()
        conn.close()
