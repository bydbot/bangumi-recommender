import json
import time
import requests
from typing import Optional, List, Tuple, Dict, Any

import config
from data.api_cache import ApiCache
from .api_types import SlimSubject, CollectionItem, Subject, SeasonalAnime

_session = None
_cache: Optional[ApiCache] = None


def _get_cache() -> ApiCache:
    global _cache
    if _cache is None:
        _cache = ApiCache(config.API_CACHE_DB, config.API_CACHE_TTL_HOURS)
    return _cache


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": config.BANGUMI_USER_AGENT})
    if config.ACCESS_TOKEN:
        _session.headers["Authorization"] = f"Bearer {config.ACCESS_TOKEN}"
    return _session


def _api_get(path: str, params: dict = None) -> Optional[dict]:
    url = f"{config.BANGUMI_API_BASE}{path}"
    for attempt in range(config.API_MAX_RETRIES):
        try:
            resp = _get_session().get(url, params=params, timeout=30)
            if resp.status_code == 429:
                time.sleep(60)
                continue
            resp.raise_for_status()
            return resp.json() if resp.text else None
        except requests.RequestException as e:
            if attempt < config.API_MAX_RETRIES - 1:
                time.sleep(config.API_REQUEST_DELAY * (attempt + 1))
            else:
                print(f"API 请求失败 {path}: {e}")
                return None


def check_user_exists(username: str) -> bool:
    resp = _api_get(f"/v0/users/{username}")
    return resp is not None and "id" in resp


def fetch_collections(
    username: str, collect_type: int, limit: int = 50
) -> List[CollectionItem]:
    items: List[CollectionItem] = []
    offset = 0
    while True:
        resp = _api_get(
            f"/v0/users/{username}/collections",
            params={
                "subject_type": 2,
                "type": collect_type,
                "limit": limit,
                "offset": offset,
            },
        )
        if not resp or not resp.get("data"):
            break
        for entry in resp["data"]:
            subject = entry.get("subject", {})
            items.append(CollectionItem(
                subject_id=subject.get("id", entry.get("subject_id", 0)),
                name=subject.get("name", ""),
                name_cn=subject.get("name_cn", ""),
                collect_type=collect_type,
                rate=entry.get("rate"),
            ))
        total = resp.get("total", 0)
        if offset + limit >= total:
            break
        offset += limit
        time.sleep(config.API_REQUEST_DELAY)
    return items


def fetch_watched_and_wished(
    username: str, force_refresh: bool = False
) -> Tuple[List[CollectionItem], List[CollectionItem], bool]:
    cache = _get_cache()
    if not force_refresh:
        cached = cache.get(username)
        if cached is not None:
            return cached[0], cached[1], True

    watched = fetch_collections(username, collect_type=2)
    time.sleep(config.API_REQUEST_DELAY)
    wished = fetch_collections(username, collect_type=1)

    cache.set(username, watched, wished)
    from data.sync_db import sync_user_interactions
    sync_user_interactions(str(username), watched, wished)
    return watched, wished, False


def browse_seasonal(year: int, month: int, sort: str = "date") -> List[SlimSubject]:
    subjects: Dict[int, SlimSubject] = {}
    for m in [month, month + 1]:
        page = 1
        while True:
            resp = _api_get(
                "/p1/subjects",
                params={"type": 2, "year": year, "month": m, "sort": sort, "page": page},
            )
            if not resp or not resp.get("data"):
                break
            for s in resp["data"]:
                sid = s.get("id", 0)
                if sid and sid not in subjects:
                    rating = s.get("rating", {}) or {}
                    subjects[sid] = SlimSubject(
                        id=sid,
                        name=s.get("name", ""),
                        name_cn=s.get("nameCN", ""),
                        type=s.get("type", 2),
                        rating_score=rating.get("score", 0.0) or 0.0,
                        rating_total=rating.get("total", 0) or 0,
                        images=s.get("images", {}),
                        locked=s.get("locked", False),
                        nsfw=s.get("nsfw", False),
                    )
            if page * 50 >= resp.get("total", 0):
                break
            page += 1
            time.sleep(config.API_REQUEST_DELAY)
    return list(subjects.values())


def get_subject_detail(subject_id: int) -> Optional[Subject]:
    resp = _api_get(f"/p1/subjects/{subject_id}")
    if not resp:
        return None
    rating = resp.get("rating", {}) or {}
    collection = resp.get("collection", {}) or {}
    airtime = resp.get("airtime", {}) or {}
    return Subject(
        id=resp.get("id", subject_id),
        name=resp.get("name", ""),
        name_cn=resp.get("nameCN", ""),
        type=resp.get("type", 2),
        summary=resp.get("summary", ""),
        meta_tags=resp.get("metaTags", []),
        tags=resp.get("tags", []),
        rating_score=rating.get("score", 0.0) or 0.0,
        rating_total=rating.get("total", 0) or 0,
        rating_rank=rating.get("rank", 0) or 0,
        collection_wish=collection.get("1", 0) or 0,
        collection_watch=collection.get("2", 0) or 0,
        collection_doing=collection.get("3", 0) or 0,
        collection_on_hold=collection.get("4", 0) or 0,
        collection_dropped=collection.get("5", 0) or 0,
        infobox=resp.get("infobox", []),
        airtime=airtime,
        images=resp.get("images", {}),
        nsfw=resp.get("nsfw", False),
    )


def fetch_calendar() -> Dict[int, SlimSubject]:
    resp = _api_get("/calendar")
    if not resp:
        return {}
    airing_animes: Dict[int, SlimSubject] = {}
    for day_items in resp:
        if not isinstance(day_items, dict):
            continue
        items = day_items.get("items", [])
        for item in items:
            if not item:
                continue
            sid = item.get("id", 0)
            if sid and sid not in airing_animes:
                airing_animes[sid] = SlimSubject(
                    id=sid,
                    name=item.get("name", ""),
                    name_cn=item.get("name_cn", ""),
                    type=item.get("type", 2),
                    rating_score=item.get("rating", {}).get("score", 0.0) or 0.0,
                    rating_total=item.get("rating", {}).get("total", 0) or 0,
                    images=item.get("images", {}),
                    locked=item.get("locked", False),
                    nsfw=item.get("nsfw", False),
                )
    return airing_animes


def browse_and_detail_seasonal(year: int, month: int) -> List[SeasonalAnime]:
    from datetime import datetime
    slim_list = browse_seasonal(year, month)
    results = []
    season_label = f"{year}-{month:02d}"
    now = datetime.now().isoformat()
    for slim in slim_list:
        time.sleep(config.API_REQUEST_DELAY)
        detail = get_subject_detail(slim.id)
        if not detail:
            continue
        airtime = detail.airtime
        results.append(SeasonalAnime(
            subject_id=slim.id,
            name=detail.name,
            name_cn=detail.name_cn,
            summary=detail.summary,
            meta_tags=detail.meta_tags,
            rating_score=detail.rating_score,
            rating_total=detail.rating_total,
            wish_count=detail.collection_wish,
            watch_count=detail.collection_watch,
            airtime_date=airtime.get("date", ""),
            airtime_year=airtime.get("year", year),
            airtime_month=airtime.get("month", month),
            season_label=season_label,
            infobox_items=detail.infobox,
            is_completed=False,
            crawled_at=now,
        ))
    return results
