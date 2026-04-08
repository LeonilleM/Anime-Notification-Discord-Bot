"""
Build anime lists from a saved Crunchyroll browse page and/or Jikan (api.jikan.moe).
"""
from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

import jikan_client
from helper import apply_jikan_anime_payload
from models import Anime

log = logging.getLogger(__name__)

# Short user queries → extra Jikan search terms (API often misses 2–3 letter strings).
SEARCH_ALIASES: dict[str, str] = {
    "jjk": "Jujutsu Kaisen",
    "jujutsu": "Jujutsu Kaisen",
    "mha": "Boku no Hero Academia",
    "bnha": "Boku no Hero Academia",
    "op": "One Piece",
    "aot": "Attack on Titan",
    "csm": "Chainsaw Man",
    "rezero": "Re:Zero kara Hajimeru Isekai Seikatsu",
    "slime": "Tensei shitara Slime Datta Ken",
}

_ROOT = Path(__file__).resolve().parent
DEFAULT_CRUNCHYROLL_SNAPSHOT = _ROOT / "Crunchyroll.html"


def _search_queries(raw: str) -> list[str]:
    q = raw.strip()
    out: list[str] = []
    key = q.lower()
    if key in SEARCH_ALIASES:
        out.append(SEARCH_ALIASES[key])
    out.append(q)
    seen: set[str] = set()
    unique: list[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


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
        # Short / acronym queries: prefer TV whose title contains the query
        if len(name_l) <= 4 and name_l.isalpha():
            for r in results:
                if (r.get("type") or "").lower() != "tv":
                    continue
                for key in ("title", "title_english"):
                    t = (r.get(key) or "").lower()
                    if name_l in t or t.startswith(name_l):
                        return r.get("mal_id")
        for r in results:
            if (r.get("type") or "").lower() == "tv":
                return r.get("mal_id")
        return results[0].get("mal_id")

    def _anime_search_results(self, name: str) -> list[dict[str, Any]]:
        """Try alias-expanded queries, TV-only first, then any type."""
        for query in _search_queries(name):
            for type_ in ("tv", None):
                label = "tv" if type_ else "any"
                try:
                    rows = jikan_client.anime_search(query, limit=15, type_=type_)
                except Exception as exc:
                    log.warning("jikan anime_search failed query=%r type=%s: %s", query, label, exc)
                    continue
                if rows:
                    log.info(
                        "jikan search ok query=%r type=%s count=%s first=%r",
                        query,
                        label,
                        len(rows),
                        (rows[0].get("title") or "")[:60],
                    )
                    return rows
        log.warning("jikan search: no results for %r (tried aliases + tv/any)", name)
        return []

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
            results = self._anime_search_results(show.name)
            mal_id = self._pick_search_result(show.name, results)
            if not mal_id:
                log.warning("pick_search_result: no mal_id for query %r", show.name)
                return False
            log.info("picked mal_id=%s for query %r", mal_id, show.name)
            mal_id = self.resolve_latest_airing_sequel(mal_id)
            data = jikan_client.anime_full(mal_id)
        except Exception:
            log.exception("jikan chain failed for query %r", show.name)
            return False
        ok = apply_jikan_anime_payload(show, data)
        if not ok:
            log.warning(
                "apply_jikan_anime_payload failed mal_id=%s (need TV + MAL broadcast fields)",
                mal_id,
            )
        else:
            log.info("enriched ok title=%r mal_id=%s", show.name, mal_id)
        return ok


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
