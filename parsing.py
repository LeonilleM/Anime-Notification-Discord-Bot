"""Small pure helpers (safe to import without Discord env)."""


def parse_season_args(s: str) -> tuple[int, str] | None:
    """Parse e.g. '2026 spring' → (2026, 'spring')."""
    tokens = s.lower().split()
    year: int | None = None
    season: str | None = None
    valid = frozenset({"winter", "spring", "summer", "fall"})
    for t in tokens:
        if t.isdigit() and len(t) == 4:
            year = int(t)
        if t in valid:
            season = t
    if year is not None and season is not None:
        return year, season
    return None
