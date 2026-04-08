from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Anime:
    """One show the bot tracks or enriches from Jikan."""

    name: str
    crunchyroll_url: str
    mal_url: str | None = None
    image_url: str | None = None
    genres: list[str] | None = None
    rating: str | None = None
    datetime_aired: datetime | None = None
    episode: int | None = None

    def format_genres(self) -> str:
        if not self.genres:
            return "N/A"
        return ", ".join(self.genres)
