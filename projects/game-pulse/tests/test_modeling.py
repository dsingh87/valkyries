from datetime import UTC, datetime, timedelta

import pytest

from game_pulse.data import (
    CONTEXT_COLUMNS,
    SEQUENCE_COLUMNS,
    chronological_split,
    make_sequences,
)
from game_pulse.modeling import train_model_suite


@pytest.mark.modeling
def test_all_models_produce_deterministic_bounded_probabilities() -> None:
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    pytest.importorskip("keras")
    pytest.importorskip("xgboost")
    rows = []
    for game_index in range(70):
        season = 2025 if game_index < 60 else 2026
        home_win = game_index % 2
        for possession in range(1, 11):
            direction = 1 if home_win else -1
            row = {
                "possession_id": f"p-{game_index}-{possession}",
                "game_id": f"g-{game_index:03d}",
                "game_date": datetime(season, 1, 1, tzinfo=UTC)
                + timedelta(days=game_index),
                "season": season,
                "possession_number": possession,
                "home_win": home_win,
                "home_margin": direction * max(possession - 3, 0),
                "period": min((possession - 1) // 3 + 1, 4),
                "period_seconds_remaining": 600 - possession * 20,
                "game_seconds_remaining": 2400 - possession * 50,
                "is_home_offense": possession % 2,
                "rolling_net_advantage": float(direction * 2),
                "rest_advantage": 0.0,
                "rolling_missing": 0,
                "rest_missing": 0,
                "pressure": float(direction * possession / 10),
                "valid": 1,
                "home_score_delta": direction if possession % 3 == 0 else 0,
                "duration_seconds": 14,
                "home_offense": possession % 2,
                "half_court": 1,
                "action_turnover": int(possession % 5 == 0),
                "action_free_throw": 0,
                "action_field_goal": int(possession % 5 != 0),
                "action_rebound": 0,
                "action_other": 0,
            }
            assert set(CONTEXT_COLUMNS).issubset(row)
            assert set(SEQUENCE_COLUMNS).issubset(row)
            rows.append(row)
    frame = pd.DataFrame(rows)
    sequences = make_sequences(frame)
    split = chronological_split(frame, test_season=2026)
    output = train_model_suite(
        frame,
        sequences,
        split,
        cutoff=datetime(2026, 12, 31, tzinfo=UTC),
    )
    assert len(output.model_card.models) == 4
    assert {model.name for model in output.model_card.models} == {
        "prior",
        "logistic",
        "xgboost",
        "keras_gru",
    }
    assert np.isfinite(output.champion_test_probabilities).all()
    assert (
        (0 <= output.champion_test_probabilities)
        & (output.champion_test_probabilities <= 1)
    ).all()
    assert len(output.model_card.calibration) == 10
