import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from data.api_types import CollectionItem


def _now_iso() -> str:
    return datetime.now().isoformat()


def _is_expired(fetched_at: str, ttl_hours: int) -> bool:
    try:
        dt = datetime.fromisoformat(fetched_at)
        return datetime.now() - dt > timedelta(hours=ttl_hours)
    except (ValueError, TypeError):
        return True


class ApiCache:
    def __init__(self, db_path: str, ttl_hours: int = 168):
        self._db_path = db_path
        self._ttl_hours = ttl_hours
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collection_cache (
                user_id TEXT PRIMARY KEY,
                watched_json TEXT,
                wished_json TEXT,
                fetched_at TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_fetched_at
            ON collection_cache(fetched_at)
        """)
        conn.commit()
        conn.close()

    def get(self, user_id: str) -> Optional[Tuple[List[CollectionItem], List[CollectionItem]]]:
        conn = sqlite3.connect(self._db_path)
        row = conn.execute(
            "SELECT watched_json, wished_json, fetched_at FROM collection_cache WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        conn.close()

        if not row:
            return None
        if _is_expired(row[2], self._ttl_hours):
            return None

        try:
            watched_raw = json.loads(row[0])
            wished_raw = json.loads(row[1])
        except json.JSONDecodeError:
            return None

        watched = [CollectionItem(**it) for it in watched_raw]
        wished = [CollectionItem(**it) for it in wished_raw]
        return watched, wished

    def set(self, user_id: str, watched: List[CollectionItem], wished: List[CollectionItem]):
        watched_json = json.dumps(
            [asdict(it) for it in watched], ensure_ascii=False
        )
        wished_json = json.dumps(
            [asdict(it) for it in wished], ensure_ascii=False
        )
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO collection_cache (user_id, watched_json, wished_json, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, watched_json, wished_json, _now_iso()),
        )
        conn.commit()
        conn.close()

    def is_fresh(self, user_id: str) -> bool:
        conn = sqlite3.connect(self._db_path)
        row = conn.execute(
            "SELECT fetched_at FROM collection_cache WHERE user_id = ?", (user_id,)
        ).fetchone()
        conn.close()
        if not row:
            return False
        return not _is_expired(row[0], self._ttl_hours)
