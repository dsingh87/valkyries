from datetime import UTC, datetime, timedelta

import pytest

from game_pulse.data import (
    action_bucket,
    chronological_split,
    display_clock,
    home_margin_before,
    home_score_delta,
    make_sequences,
    period_label,
    period_seconds_remaining,
)


def test_score_perspective_helpers() -> None:
    assert home_margin_before(4, True) == 4
    assert home_margin_before(4, False) == -4
    assert home_score_delta(3, True) == 3
    assert home_score_delta(3, False) == -3


def test_regulation_and_overtime_clock() -> None:
    assert period_seconds_remaining(1, 0) == 600
    assert period_seconds_remaining(4, 2398) == 2
    assert period_seconds_remaining(5, 2400) == 300
    assert period_seconds_remaining(6, 2999) == 1
    assert display_clock(4, 2335) == "1:05"
    assert display_clock(5, 2525) == "2:55"
    assert period_label(4) == "Q4"
    assert period_label(5) == "OT1"


@pytest.mark.parametrize(
    ("action", "points", "expected"),
    [
        ("Bad Pass Turnover", 0, "turnover"),
        ("Free Throw - 2 of 2", 1, "free_throw"),
        ("Defensive Rebound", 0, "rebound"),
        ("Jump Shot", 2, "field_goal"),
        ("End Period", 0, "other"),
    ],
)
def test_action_bucket(action: str, points: int, expected: str) -> None:
    assert action_bucket(action, points) == expected


@pytest.mark.modeling
def test_sequences_only_include_prior_possessions() -> None:
    pd = pytest.importorskip("pandas")
    rows = []
    for possession in range(1, 13):
        rows.append(
            {
                "game_id": "g1",
                "possession_number": possession,
                "valid": 1,
                "home_score_delta": possession,
                "duration_seconds": 10,
                "home_offense": possession % 2,
                "half_court": 1,
                "action_turnover": 0,
                "action_free_throw": 0,
                "action_field_goal": 1,
                "action_rebound": 0,
                "action_other": 0,
            }
        )
    frame = pd.DataFrame(rows)
    sequences = make_sequences(frame)
    assert sequences[0].sum() == 0
    assert sequences[1, -1, 1] == 1
    assert sequences[11, 0, 1] == 2
    assert 12 not in sequences[11, :, 1]


@pytest.mark.modeling
def test_chronological_split_keeps_2026_test_only() -> None:
    pd = pytest.importorskip("pandas")
    games = []
    for index in range(40):
        games.append(
            {
                "game_id": f"pre-{index:02d}",
                "game_date": datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index),
                "season": 2025,
            }
        )
    for index in range(5):
        games.append(
            {
                "game_id": f"test-{index:02d}",
                "game_date": datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
                "season": 2026,
            }
        )
    split = chronological_split(pd.DataFrame(games), test_season=2026)
    assert set(split.test_games) == {f"test-{index:02d}" for index in range(5)}
    assert not set(split.test_games).intersection(
        game for group in split.groups()[:-1] for game in group
    )
