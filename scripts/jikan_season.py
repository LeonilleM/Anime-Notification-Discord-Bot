#!/usr/bin/env python3
"""CLI: print a few shows from Jikan seasonal endpoint."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from catalog import AnimeCatalog  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Sample Jikan seasonal data.")
    p.add_argument("year", type=int)
    p.add_argument("season", choices=("winter", "spring", "summer", "fall"))
    p.add_argument("-n", "--limit", type=int, default=5)
    args = p.parse_args()

    cat = AnimeCatalog()
    shows = cat.load_season_jikan(args.year, args.season, limit=args.limit)
    print(f"{args.season} {args.year}: {len(shows)} shows with TV + broadcast\n")
    for s in shows:
        print("---")
        print(s.name)
        print("  MAL:", s.mal_url)
        print("  Link:", s.crunchyroll_url)
        print("  Score:", s.rating, "|", s.format_genres())
        print("  Slot (local):", s.datetime_aired)


if __name__ == "__main__":
    main()
