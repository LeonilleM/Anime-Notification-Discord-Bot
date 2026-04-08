import json

import helper


def test_get_tracked_uses_config_path(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"tracking": ["Alpha", "Beta"], "filters": ["Action"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(helper, "CONFIG_PATH", cfg)
    assert helper.get_tracked() == ["Alpha", "Beta"]
    assert helper.get_filters() == ["Action"]


def test_rating_stars_display() -> None:
    frac, stars = helper.rating_stars_display("8.0")
    assert frac == "4.0"
    assert stars == "⭐⭐⭐⭐"
