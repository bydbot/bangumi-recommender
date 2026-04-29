import json
import sqlite3
from datetime import datetime
from typing import List

import config
from data.api_types import CollectionItem

_db_initialized = False


def _ensure_db(db_path=config.USER_INTERACTIONS_DB):
    global _db_initialized
    if not _db_initialized:
        init_user_db(db_path)
        _db_initialized = True


def init_user_db(db_path=config.USER_INTERACTIONS_DB):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_collections (
            user_id TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            rate REAL,
            collect_type INTEGER NOT NULL CHECK(collect_type IN (1, 2)),
            updated_at TEXT,
            PRIMARY KEY (user_id, subject_id, collect_type)
        )
    """)
    conn.commit()
    conn.close()


def sync_user_interactions(
    user_id: str,
    watched: List[CollectionItem],
    wished: List[CollectionItem],
    db_path=config.USER_INTERACTIONS_DB,
):
    _ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat()

    conn.execute("DELETE FROM user_collections WHERE user_id = ?", (user_id,))

    rows = []
    for item in watched:
        rows.append((user_id, item.subject_id, item.rate, 2, now))
    for item in wished:
        rows.append((user_id, item.subject_id, None, 1, now))

    conn.executemany(
        "INSERT OR REPLACE INTO user_collections (user_id, subject_id, rate, collect_type, updated_at) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def load_watched_from_db(user_id: str, db_path=config.USER_INTERACTIONS_DB) -> List[int]:
    _ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT subject_id, rate FROM user_collections WHERE user_id = ? AND collect_type = 2",
        (user_id,),
    ).fetchall()
    conn.close()
    return [int(r[0]) for r in rows]


def load_wished_from_db(user_id: str, db_path=config.USER_INTERACTIONS_DB) -> List[int]:
    _ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT subject_id FROM user_collections WHERE user_id = ? AND collect_type = 1",
        (user_id,),
    ).fetchall()
    conn.close()
    return [int(r[0]) for r in rows]


def load_history_ratings(user_id: str, db_path=config.USER_INTERACTIONS_DB) -> dict:
    _ensure_db(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT subject_id, rate FROM user_collections WHERE user_id = ? AND collect_type = 2 AND rate IS NOT NULL",
        (user_id,),
    ).fetchall()
    conn.close()
    return {int(r[0]): float(r[1]) for r in rows}
