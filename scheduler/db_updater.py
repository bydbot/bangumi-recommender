import json
import sqlite3
import time
from datetime import datetime

import config


def update_completed_anime(db_path=config.SEASONAL_DB, min_rating_count=30):
    from data.api_client import get_subject_detail, fetch_calendar

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    pending = cursor.execute(
        "SELECT subject_id FROM seasonal_anime WHERE is_completed = 0"
    ).fetchall()

    if not pending:
        print("[updater] 无需更新的条目")
        conn.close()
        return

    print("[updater] 获取当前放送日历...")
    airing_animes = fetch_calendar()
    airing_ids = set(airing_animes.keys())
    print(f"[updater] 当前放送中动画: {len(airing_ids)} 部")

    updated = 0
    inserted_meta = 0

    for (sid,) in pending:
        if sid not in airing_ids:
            time.sleep(config.API_REQUEST_DELAY)
            detail = get_subject_detail(sid)
            if not detail:
                continue

            if detail.rating_total < min_rating_count:
                print(f"[updater] 丢弃 (已完结但评分人数不足): {detail.name_cn or detail.name} (评分人数: {detail.rating_total})")
                cursor.execute("DELETE FROM seasonal_anime WHERE subject_id = ?", (sid,))
                continue

            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE seasonal_anime
                SET is_completed = 1, completed_at = ?,
                    rating_total = ?, rating_score = ?,
                    wish_count = ?, watch_count = ?,
                    updated_at = ?
                WHERE subject_id = ?
            """, (now, detail.rating_total, detail.rating_score,
                  detail.collection_wish, detail.collection_watch,
                  now, sid))
            updated += 1
            print(f"[updater] 标记完结 (不在放送列表中): {detail.name_cn or detail.name}")

            _insert_anime_meta(detail)
            inserted_meta += 1
            print(f"[updater] 同步到 anime_meta.db: {detail.name_cn or detail.name}")

        time.sleep(config.API_REQUEST_DELAY)

    conn.commit()
    conn.close()
    print(f"[updater] 本次: {updated} 部完结, {inserted_meta} 部同步到动画条目总库")


def _insert_anime_meta(detail):
    from data.anime_db import insert_or_replace_anime
    data = {
        "id": detail.id,
        "name": detail.name,
        "name_cn": detail.name_cn,
        "type": detail.type,
        "infobox": json.dumps(detail.infobox, ensure_ascii=False) if detail.infobox else "{}",
        "platform": 0,
        "summary": detail.summary,
        "nsfw": detail.nsfw,
        "tags": detail.tags,
        "meta_tags": detail.meta_tags,
        "score": detail.rating_score,
        "score_details": {},
        "rank": detail.rating_rank,
        "date": detail.airtime.get("date", ""),
        "series": False,
        "favorite": {
            "wish": detail.collection_wish,
            "done": detail.collection_watch,
            "doing": detail.collection_doing or 0,
            "on_hold": detail.collection_on_hold or 0,
            "dropped": detail.collection_dropped or 0,
        },
        "episode_ids": [],
    }
    insert_or_replace_anime(data)
