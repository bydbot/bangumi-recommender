import json
import sqlite3
from datetime import datetime
from typing import Dict, Optional

import config


def init_anime_db(db_path=config.ANIME_META_DB):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anime_entries (
            id INTEGER PRIMARY KEY,
            name TEXT,
            name_cn TEXT,
            type INTEGER,
            infobox TEXT,
            platform INTEGER,
            summary TEXT,
            nsfw INTEGER,
            tags TEXT,
            meta_tags TEXT,
            score REAL,
            score_details TEXT,
            rank INTEGER,
            date TEXT,
            series INTEGER,
            favorite_wish INTEGER,
            favorite_done INTEGER,
            favorite_doing INTEGER,
            favorite_on_hold INTEGER,
            favorite_dropped INTEGER,
            episode_ids TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def _json_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False) if obj else "[]"


def import_anime_jsonlines(jsonlines_path: str = config.ANIME_JSONLINES,
                           db_path=config.ANIME_META_DB):
    import os
    if not os.path.exists(jsonlines_path):
        print(f"[anime_db] {jsonlines_path} 不存在，跳过导入")
        return 0

    init_anime_db(db_path)
    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat()
    count = 0

    with open(jsonlines_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            sid = data.get("id")
            if not sid:
                continue
            favorite = data.get("favorite", {}) or {}
            conn.execute("""
                INSERT OR IGNORE INTO anime_entries (
                    id, name, name_cn, type, infobox, platform, summary, nsfw,
                    tags, meta_tags, score, score_details, rank, date, series,
                    favorite_wish, favorite_done, favorite_doing, favorite_on_hold, favorite_dropped,
                    episode_ids, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sid,
                data.get("name", ""),
                data.get("name_cn", ""),
                data.get("type", 0),
                data.get("infobox", "{}"),
                data.get("platform", 0),
                data.get("summary", ""),
                1 if data.get("nsfw") else 0,
                _json_dump(data.get("tags", [])),
                _json_dump(data.get("meta_tags", [])),
                data.get("score", 0.0) or 0.0,
                _json_dump(data.get("score_details", {})),
                data.get("rank", 0) or 0,
                data.get("date", ""),
                1 if data.get("series") else 0,
                favorite.get("wish", 0),
                favorite.get("done", 0),
                favorite.get("doing", 0),
                favorite.get("on_hold", 0),
                favorite.get("dropped", 0),
                _json_dump(data.get("episode_ids", [])),
                now,
                now,
            ))
            count += 1

    conn.commit()
    conn.close()
    print(f"[anime_db] 导入完成: {count} 条")
    return count


def insert_or_replace_anime(data: dict, db_path=config.ANIME_META_DB):
    init_anime_db(db_path)
    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat()
    favorite = data.get("favorite", {}) or {}
    sid = data.get("id")
    conn.execute("""
        INSERT OR REPLACE INTO anime_entries (
            id, name, name_cn, type, infobox, platform, summary, nsfw,
            tags, meta_tags, score, score_details, rank, date, series,
            favorite_wish, favorite_done, favorite_doing, favorite_on_hold, favorite_dropped,
            episode_ids, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sid, data.get("name", ""), data.get("name_cn", ""),
        data.get("type", 0), data.get("infobox", "{}"),
        data.get("platform", 0), data.get("summary", ""),
        1 if data.get("nsfw") else 0,
        _json_dump(data.get("tags", [])), _json_dump(data.get("meta_tags", [])),
        data.get("score", 0.0) or 0.0, _json_dump(data.get("score_details", {})),
        data.get("rank", 0) or 0, data.get("date", ""),
        1 if data.get("series") else 0,
        favorite.get("wish", 0), favorite.get("done", 0),
        favorite.get("doing", 0), favorite.get("on_hold", 0), favorite.get("dropped", 0),
        _json_dump(data.get("episode_ids", [])),
        now, now,
    ))
    conn.commit()
    conn.close()


def get_anime_meta(subject_id: int, db_path=config.ANIME_META_DB) -> Optional[dict]:
    init_anime_db(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name, name_cn, score FROM anime_entries WHERE id = ?",
        (subject_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"name": row[0], "name_cn": row[1], "score": row[2]}


def get_anime_name(subject_id: int, db_path=config.ANIME_META_DB) -> str:
    meta = get_anime_meta(subject_id, db_path)
    if not meta:
        return f"Unknown ({subject_id})"
    return meta.get("name_cn") or meta.get("name", f"Unknown ({subject_id})")


def get_anime_rating(subject_id: int, db_path=config.ANIME_META_DB) -> float:
    meta = get_anime_meta(subject_id, db_path)
    return (meta.get("score") or 0.0) if meta else 0.0
