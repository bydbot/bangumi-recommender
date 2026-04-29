import sqlite3
import json
import time
from datetime import datetime
from typing import List

import config
from data.api_client import browse_and_detail_seasonal
from data.api_types import SeasonalAnime


def init_db(db_path: str = config.SEASONAL_DB):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seasonal_anime (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER UNIQUE NOT NULL,
            name TEXT,
            name_cn TEXT,
            summary TEXT,
            meta_tags TEXT,
            rating_score REAL,
            rating_total INTEGER,
            wish_count INTEGER,
            watch_count INTEGER,
            airtime_date TEXT,
            airtime_year INTEGER,
            airtime_month INTEGER,
            season_label TEXT,
            infobox TEXT,
            is_completed INTEGER DEFAULT 0,
            completed_at TEXT,
            crawled_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS update_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_label TEXT,
            crawled_count INTEGER,
            completed_count INTEGER,
            started_at TEXT,
            finished_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def _upsert_anime(conn: sqlite3.Connection, item: SeasonalAnime):
    conn.execute("""
        INSERT OR REPLACE INTO seasonal_anime (
            subject_id, name, name_cn, summary, meta_tags,
            rating_score, rating_total, wish_count, watch_count,
            airtime_date, airtime_year, airtime_month, season_label,
            infobox, is_completed, crawled_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.subject_id, item.name, item.name_cn, item.summary,
        json.dumps(item.meta_tags, ensure_ascii=False) if item.meta_tags else "[]",
        item.rating_score, item.rating_total, item.wish_count, item.watch_count,
        item.airtime_date, item.airtime_year, item.airtime_month, item.season_label,
        json.dumps(item.infobox_items, ensure_ascii=False) if item.infobox_items else "[]",
        1 if item.is_completed else 0,
        datetime.now().isoformat() if item.is_completed else None,
        item.crawled_at,
        datetime.now().isoformat(),
    ))


def crawl_and_persist(year: int, month: int, db_path: str = config.SEASONAL_DB) -> int:
    from data.api_client import fetch_calendar
    season_label = f"{year}-{month:02d}"
    started_at = datetime.now().isoformat()

    print(f"[seasonal] 开始爬取 {season_label} 当季新番...")
    results = browse_and_detail_seasonal(year, month)
    print(f"[seasonal] 共获取 {len(results)} 部动画")

    print(f"[seasonal] 获取当前放送日历...")
    airing_animes = fetch_calendar()
    airing_ids = set(airing_animes.keys())
    print(f"[seasonal] 当前放送中动画: {len(airing_ids)} 部")

    for item in results:
        if item.subject_id not in airing_ids:
            item.is_completed = True

    init_db(db_path)
    conn = sqlite3.connect(db_path)

    completed = 0
    for item in results:
        _upsert_anime(conn, item)
        if item.is_completed:
            completed += 1
    conn.commit()

    conn.execute("""
        INSERT INTO update_log (season_label, crawled_count, completed_count, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?)
    """, (season_label, len(results), completed, started_at, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    print(f"[seasonal] 已保存 {len(results)} 部 (其中 {completed} 部已完结)")
    return len(results)
