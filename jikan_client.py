"""
Thin Jikan REST client (v4). https://jikan.moe/

Serializes requests with a lock, enforces a minimum interval, and backs off on 429
(including Retry-After when present).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

JIKAN_BASE = "https://api.jikan.moe/v4"
_MIN_INTERVAL = 0.9
_last = 0.0
_lock = threading.Lock()
_MAX_ATTEMPTS = 8
_BASE_BACKOFF = 2.0
_MAX_BACKOFF = 60.0


def _throttle_unlocked() -> None:
    global _last
    now = time.monotonic()
    wait = _MIN_INTERVAL - (now - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.monotonic()


def _parse_retry_after(response: requests.Response) -> float | None:
    h = response.headers.get("Retry-After")
    if not h:
        return None
    try:
        return float(h)
    except ValueError:
        return None


def get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Single-flight HTTP GET: one Jikan request at a time + 429 backoff."""
    url = f"{JIKAN_BASE}{path}"
    backoff = _BASE_BACKOFF
    last: requests.Response | None = None

    with _lock:
        for attempt in range(_MAX_ATTEMPTS):
            _throttle_unlocked()
            r = requests.get(url, params=params or {}, timeout=45)
            last = r
            if r.status_code == 429:
                ra = _parse_retry_after(r)
                sleep_s = ra if ra is not None else backoff
                sleep_s = min(max(sleep_s, 1.0), _MAX_BACKOFF)
                log.warning(
                    "Jikan 429 (attempt %s/%s) sleeping %.1fs path=%s",
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    sleep_s,
                    path,
                )
                time.sleep(sleep_s)
                backoff = min(backoff * 1.75, _MAX_BACKOFF)
                continue
            r.raise_for_status()
            return r.json()

        if last is not None:
            last.raise_for_status()
        raise requests.HTTPError("Jikan request failed after retries")


def anime_search(query: str, limit: int = 5, type_: str | None = "tv") -> list[dict[str, Any]]:
    params: dict[str, Any] = {"q": query, "limit": limit}
    if type_:
        params["type"] = type_
    data = get_json("/anime", params=params)
    return data.get("data") or []


def anime_full(mal_id: int) -> dict[str, Any]:
    data = get_json(f"/anime/{mal_id}/full")
    return data["data"]


def season_anime(year: int, season: str) -> list[dict[str, Any]]:
    """season: winter | spring | summer | fall"""
    from urllib.parse import quote

    data = get_json(f"/seasons/{year}/{quote(season)}")
    return data.get("data") or []


def top_anime(*, filter_: str = "airing", limit: int = 10) -> list[dict[str, Any]]:
    """filter_: airing | upcoming | bypopularity | favorite (see Jikan docs)."""
    data = get_json("/top/anime", params={"filter": filter_, "limit": limit})
    return data.get("data") or []
