from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

from models import Anime

_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = _ROOT / "config.json"


def _load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_config(data: dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def filter_by_genre(anime_list: list, filters: list[str]) -> list:
    if not filters:
        return list(anime_list)
    out = []
    for anime in anime_list:
        genres = anime.genres or []
        if any(g in filters for g in genres):
            out.append(anime)
    return out


def genres_from_jikan(genre_entries: list[dict[str, Any]] | None) -> list[str]:
    if not genre_entries:
        return []
    return [g["name"] for g in genre_entries if isinstance(g, dict) and g.get("name")]


def all_genre_names_from_jikan(data: dict[str, Any]) -> list[str]:
    names = genres_from_jikan(data.get("genres"))
    for d in data.get("demographics") or []:
        if isinstance(d, dict) and d.get("name"):
            names.append(d["name"])
    return names


_WEEKDAY_TO_INT = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _parse_weekday_label(day: str) -> int | None:
    if not day:
        return None
    key = day.strip().lower().rstrip("s")
    return _WEEKDAY_TO_INT.get(key)


def airing_datetime_from_jikan(data: dict[str, Any]) -> datetime.datetime | None:
    """
    Naive local datetime for the first weekly broadcast (used by just_aired).
    Broadcast is interpreted in Asia/Tokyo, then converted to system local time.
    """
    if (data.get("type") or "").upper() != "TV":
        return None
    broadcast = data.get("broadcast") or {}
    time_s = broadcast.get("time")
    day_s = broadcast.get("day")
    if not time_s or not day_s:
        return None
    aired = data.get("aired") or {}
    prop_from = (aired.get("prop") or {}).get("from") or {}
    y, m, d = prop_from.get("year"), prop_from.get("month"), prop_from.get("day")
    if not all(isinstance(x, int) for x in (y, m, d)):
        from_iso = aired.get("from")
        if not from_iso:
            return None
        try:
            dt = datetime.datetime.fromisoformat(from_iso.replace("Z", "+00:00"))
            y, m, d = dt.year, dt.month, dt.day
        except (ValueError, TypeError):
            return None
    target_wd = _parse_weekday_label(day_s)
    if target_wd is None:
        return None
    try:
        hour_s, minute_s = time_s.split(":")
        hour, minute = int(hour_s), int(minute_s)
    except (ValueError, AttributeError):
        return None

    first = datetime.datetime(y, m, d)
    delta = (target_wd - first.weekday()) % 7
    air_date = first + datetime.timedelta(days=delta)

    try:
        from zoneinfo import ZoneInfo

        jst = ZoneInfo("Asia/Tokyo")
        dt_jst = datetime.datetime(
            air_date.year, air_date.month, air_date.day, hour, minute, tzinfo=jst
        )
        return dt_jst.astimezone().replace(tzinfo=None)
    except Exception:
        return None


def apply_jikan_anime_payload(anime: Anime, data: dict[str, Any]) -> bool:
    """Fill Anime fields from a Jikan /anime/{id}/full `data` object. Returns False if unusable."""
    if (data.get("type") or "").upper() != "TV":
        return False
    dt = airing_datetime_from_jikan(data)
    if dt is None:
        return False

    anime.mal_url = data.get("url")
    anime.datetime_aired = dt
    score = data.get("score")
    anime.rating = str(score) if score is not None else "N/A"
    anime.genres = all_genre_names_from_jikan(data)

    jpg = (data.get("images") or {}).get("jpg") or {}
    if jpg.get("large_image_url"):
        anime.image_url = jpg["large_image_url"]

    ep = data.get("episodes")
    anime.episode = ep if isinstance(ep, int) else None
    if data.get("title"):
        anime.name = data["title"]
    return True


def get_tracked() -> list[str]:
    return list(_load_config()["tracking"])


def get_filters() -> list[str]:
    return list(_load_config()["filters"])


def add_filter(genre: str) -> bool:
    data = _load_config()
    if genre in data["filters"]:
        return False
    data["filters"].append(genre)
    _save_config(data)
    return True


def add_tracked(anime_name: str) -> bool:
    data = _load_config()
    if anime_name in data["tracking"]:
        return False
    data["tracking"].append(anime_name)
    _save_config(data)
    return True


def remove_filter(genre: str) -> bool:
    data = _load_config()
    if genre not in data["filters"]:
        return False
    data["filters"].remove(genre)
    _save_config(data)
    return True


def clear_filters() -> None:
    data = _load_config()
    data["filters"] = []
    _save_config(data)


def remove_tracked(anime_name: str) -> bool:
    data = _load_config()
    if anime_name not in data["tracking"]:
        return False
    data["tracking"].remove(anime_name)
    _save_config(data)
    return True


def just_aired(anime: Anime) -> bool:
    if anime.datetime_aired is None:
        return False
    curr_day = datetime.datetime.today().strftime("%A")
    curr_time = datetime.datetime.now().time().replace(second=0, microsecond=0)
    return (
        curr_day == anime.datetime_aired.strftime("%A")
        and curr_time == anime.datetime_aired.time().replace(second=0, microsecond=0)
    )


def get_last_episode(anime: Anime) -> int:
    if anime.episode is not None:
        return anime.episode
    if anime.datetime_aired is None:
        return 1
    episodes = 0
    curr_datetime = anime.datetime_aired
    while curr_datetime.date() < datetime.datetime.now().date():
        episodes += 1
        curr_datetime += datetime.timedelta(days=7)
    return episodes if episodes != 0 else 1


def rating_stars_display(rating: str) -> tuple[str, str]:
    """Returns (fraction_out_of_5_str, star_emoji_row) for embed; handles N/A."""
    if rating in ("N/A", "", None):
        return ("—", "—")
    try:
        mal_10 = float(rating)
    except (TypeError, ValueError):
        return ("—", "—")
    out_of_5 = round(mal_10 / 2, 2)
    stars = round(mal_10 / 2) * "⭐"
    return (str(out_of_5), stars)
