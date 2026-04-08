from parsing import parse_season_args


def test_parse_season_args_ok() -> None:
    assert parse_season_args("2026 spring") == (2026, "spring")
    assert parse_season_args("2026  spring") == (2026, "spring")
    assert parse_season_args("fall 2025") == (2025, "fall")


def test_parse_season_args_invalid() -> None:
    assert parse_season_args("2026") is None
    assert parse_season_args("spring") is None
    assert parse_season_args("") is None
