"""
Build anime lists from a saved Crunchyroll browse page and/or Jikan (api.jikan.moe).
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

import jikan_client
from helper import apply_jikan_anime_payload
from models import Anime

_ROOT = Path(__file__).resolve().parent
DEFAULT_CRUNCHYROLL_SNAPSHOT = _ROOT / "Crunchyroll.html"


class AnimeCatalog:
    """Enrich show metadata via Jikan; optional Crunchyroll HTML for titles + stream links."""

    def __init__(self, crunchyroll_html_path: Path | None = None) -> None:
        self._crunchy_path = crunchyroll_html_path or DEFAULT_CRUNCHYROLL_SNAPSHOT

    def load_from_crunchyroll_snapshot(self) -> list[Anime]:
        """Parse local Crunchyroll HTML and enrich each row with Jikan."""
        text = self._crunchy_path.read_bytes()
        soup = BeautifulSoup(text, "lxml")
        cards = soup.find_all(
            "div",
            class_="wrapper hover-toggle-queue container-shadow hover-classes",
        )
        portrait_by_alt: dict[str, str] = {}
        for img in soup.find_all("img", class_="portrait"):
            alt = img.get("alt")
            if alt and "src" in img.attrs:
                portrait_by_alt[alt] = img["src"]

        shows: list[Anime] = []
        for card in cards:
            parts = card.text.split()
            if len(parts) >= 2:
                parts.pop()
                parts.pop()
            title = " ".join(parts).strip()
            link = card.find("a", class_="portrait-element block-link titlefix")
            if not link or not link.get("href"):
                continue
            url = "https://www.crunchyroll.com/" + link["href"].lstrip("/")
            show = Anime(name=title, crunchyroll_url=url)
            if title in portrait_by_alt:
                show.image_url = portrait_by_alt[title]
            shows.append(show)

        return [s for s in shows if self._enrich_from_jikan(s)]

    def load_season_jikan(self, year: int, season: str, limit: int | None = None) -> list[Anime]:
        """Current-season list from Jikan only (season: winter|spring|summer|fall)."""
        entries = jikan_client.season_anime(year, season)
        if limit is not None:
            entries = entries[:limit]

        out: list[Anime] = []
        for entry in entries:
            mal_id = entry.get("mal_id")
            if not mal_id:
                continue
            title = entry.get("title") or "Unknown"
            page = entry.get("url") or ""
            show = Anime(name=title, crunchyroll_url=page or "https://myanimelist.net/")
            try:
                data = jikan_client.anime_full(mal_id)
            except Exception:
                continue
            if apply_jikan_anime_payload(show, data):
                show.crunchyroll_url = page or show.mal_url or show.crunchyroll_url
                out.append(show)
        return out

    def _pick_search_result(self, name: str, results: list[dict[str, Any]]) -> int | None:
        if not results:
            return None
        name_l = name.lower().strip()
        for r in results:
            if (r.get("type") or "").lower() == "tv" and (
                (r.get("title") or "").lower() == name_l
                or (r.get("title_english") or "").lower() == name_l
            ):
                return r.get("mal_id")
        for r in results:
            if (r.get("type") or "").lower() == "tv":
                return r.get("mal_id")
        return results[0].get("mal_id")

    def resolve_latest_airing_sequel(self, start_mal_id: int) -> int:
        """Follow TV sequels while the current entry is still airing."""
        current = start_mal_id
        while True:
            data = jikan_client.anime_full(current)
            if not data.get("airing") or (data.get("type") or "").upper() != "TV":
                return current
            sequel_id = _first_sequel_anime_id(data)
            if not sequel_id:
                return current
            nxt = jikan_client.anime_full(sequel_id)
            if (nxt.get("type") or "").upper() == "TV" and nxt.get("airing"):
                current = sequel_id
            else:
                return current

    def enrich_from_jikan(self, show: Anime) -> bool:
        """Public wrapper for tests (search + sequel resolution + full details)."""
        return self._enrich_from_jikan(show)

    def _enrich_from_jikan(self, show: Anime) -> bool:
        try:
            results = jikan_client.anime_search(show.name, limit=8, type_="tv")
            mal_id = self._pick_search_result(show.name, results)
            if not mal_id:
                return False
            mal_id = self.resolve_latest_airing_sequel(mal_id)
            data = jikan_client.anime_full(mal_id)
        except Exception:
            return False
        return apply_jikan_anime_payload(show, data)


def _first_sequel_anime_id(data: dict[str, Any]) -> int | None:
    for rel in data.get("relations") or []:
        if rel.get("relation") != "Sequel":
            continue
        for e in rel.get("entry") or []:
            if e.get("type") == "anime" and e.get("mal_id"):
                return e["mal_id"]
    return None


def sample_dummy_shows() -> list[Anime]:
    """Two fake entries airing in ~1 minute — for `!test` notifications."""
    soon = (datetime.datetime.now() + datetime.timedelta(minutes=1)).replace(
        second=0, microsecond=0
    )
    one = Anime(
        name="One Piece",
        crunchyroll_url="https://www.crunchyroll.com/one-piece",
        mal_url="https://myanimelist.net/anime/21/One_Piece",
        image_url="https://img1.ak.crunchyroll.com/i/spire4/8056a82e973dde98ebb82abd39dc69731564519729_full.jpg",
        rating="8.53",
        genres=["Action", "Adventure", "Comedy", "Super Power", "Drama", "Fantasy", "Shounen"],
        datetime_aired=soon,
        episode=969,
    )
    two = Anime(
        name="My Hero Academia",
        crunchyroll_url="https://www.crunchyroll.com/my-hero-academia",
        mal_url="https://myanimelist.net/anime/41587/Boku_no_Hero_Academia_5th_Season",
        image_url="https://img1.ak.crunchyroll.com/i/spire3/137c90ecc4fae013811fab5275b307791617056778_full.jpg",
        rating="7.68",
        genres=["Action", "Comedy", "Super Power", "School", "Shounen"],
        datetime_aired=soon,
        episode=91,
    )
    return [one, two]
