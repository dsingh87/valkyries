from pathlib import Path

import pytest

from game_pulse.artifact import DEFAULT_CUTOFF
from game_pulse.data import load_feature_frame


@pytest.mark.modeling
def test_current_source_snapshot_reconciles() -> None:
    database = Path(__file__).resolve().parents[3] / "data" / "valkyries.sqlite3"
    if not database.exists():
        pytest.skip("local source database is not checked into Git")
    frame = load_feature_frame(f"sqlite:///{database}", DEFAULT_CUTOFF)
    games = frame[["game_id", "season"]].drop_duplicates("game_id")
    target = frame[
        (frame["season"] == 2026)
        & (
            (frame["home_team_abbreviation"] == "GS")
            | (frame["away_team_abbreviation"] == "GS")
        )
    ]["game_id"].nunique()
    assert len(games) == 737
    assert len(frame) == 119_931
    assert target == 29
