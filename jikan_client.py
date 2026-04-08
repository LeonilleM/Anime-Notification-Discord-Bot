"""
Thin Jikan REST client (v4). https://jikan.moe/
Respect rate limits: ~3 requests/second to the public API.
"""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import requests

JIKAN_BASE = "https://api.jikan.moe/v4"
_MIN_INTERVAL = 0.9
_last = 0.0


def _throttle() -> None:
    global _last
    now = time.monotonic()
    wait = _MIN_INTERVAL - (now - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.monotonic()


def get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{JIKAN_BASE}{path}"
    backoff = 2.0
    last: requests.Response | None = None
    for _ in range(5):
        _throttle()
        r = requests.get(url, params=params or {}, timeout=30)
        last = r
        if r.status_code == 429:
            time.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)
            continue
        r.raise_for_status()
        return r.json()
    if last is not None:
        last.raise_for_status()
    raise requests.HTTPError("Jikan request failed")


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
    data = get_json(f"/seasons/{year}/{quote(season)}")
    return data.get("data") or []
