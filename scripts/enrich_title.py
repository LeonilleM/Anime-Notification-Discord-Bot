#!/usr/bin/env python3
"""CLI: Jikan search + enrich one title (e.g. Jujutsu Kaisen)."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from catalog import AnimeCatalog  # noqa: E402
from models import Anime  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("title", help='Anime title, e.g. "Jujutsu Kaisen"')
    p.add_argument(
        "--url",
        default="https://www.crunchyroll.com/",
        help="Stream link stored on the Anime object (default placeholder).",
    )
    args = p.parse_args()

    cat = AnimeCatalog()
    show = Anime(name=args.title, crunchyroll_url=args.url)
    ok = cat.enrich_from_jikan(show)
    print("ok:", ok)
    print("title:", show.name)
    print("MAL:", show.mal_url)
    print("stream:", show.crunchyroll_url)
    print("score:", show.rating)
    print("genres:", show.genres)
    print("image:", show.image_url)
    print("slot (local):", show.datetime_aired)
    print("episodes:", show.episode)


if __name__ == "__main__":
    main()
