from datetime import UTC, datetime
from pathlib import Path

import pytest

from game_pulse.artifact import freeze_artifact
from game_pulse.contracts import (
    CalibrationBin,
    GameDetail,
    GamePulseArtifact,
    MetricInterval,
    ModelCard,
    ModelMetrics,
    ModelResult,
    SourceRecord,
    SplitSummary,
    TimelinePoint,
    TurningPoint,
)


def sample_artifact() -> GamePulseArtifact:
    now = datetime(2026, 8, 3, 8, 0, tzinfo=UTC)
    metrics = ModelMetrics(
        possession_brier=0.18,
        game_balanced_brier=0.19,
        log_loss=0.55,
        calibration_error=0.03,
        late_game_brier=0.14,
        brier_interval_95=MetricInterval(low=0.17, high=0.21),
    )
    card = ModelCard(
        model_run_id="test-model-run",
        champion="logistic",
        built_at=now,
        cutoff_at=now,
        data_hash="a" * 64,
        feature_schema_hash="b" * 64,
        random_seed=87,
        split=SplitSummary(
            train_games=10,
            validation_games=3,
            calibration_games=2,
            selection_games=2,
            test_games=5,
            train_end=now,
            validation_end=now,
            calibration_end=now,
            selection_end=now,
            test_start=now,
        ),
        models=[
            ModelResult(
                name="logistic",
                algorithm="test",
                complexity_rank=1,
                promoted=True,
                promotion_note="test",
                selection=metrics,
                test=metrics,
            )
        ],
        calibration=[
            CalibrationBin(
                bin_number=1,
                observations=10,
                mean_prediction=0.25,
                observed_win_rate=0.2,
            ),
            CalibrationBin(
                bin_number=2,
                observations=10,
                mean_prediction=0.75,
                observed_win_rate=0.8,
            ),
        ],
        promotion_rule="test rule",
        features=["margin"],
        sequence_features=["valid"],
        caveats=["test caveat"],
    )
    point = TimelinePoint(
        possession_number=1,
        period=1,
        period_label="Q1",
        clock="10:00",
        elapsed_seconds=0,
        valkyries_margin=0,
        valkyries_possession=True,
        win_probability=0.55,
        next_win_probability=0.65,
        win_probability_added=0.10,
        leverage=0.10,
        description="Jump Shot",
    )
    final = TimelinePoint(
        possession_number=2,
        period=4,
        period_label="Q4",
        clock="0:00",
        elapsed_seconds=2400,
        valkyries_margin=2,
        valkyries_possession=False,
        win_probability=1.0,
        next_win_probability=1.0,
        win_probability_added=0.0,
        leverage=0.0,
        description="Final horn",
        synthetic=True,
    )
    game = GameDetail(
        game_id="401857098",
        game_date=now,
        matchup="GS at PHX",
        opponent="PHX",
        location="Away",
        valkyries_score=91,
        opponent_score=89,
        result="W",
        opening_win_probability=0.55,
        minimum_win_probability=0.55,
        maximum_win_probability=0.65,
        largest_swing=0.10,
        timeline=[point, final],
        turning_points=[
            TurningPoint(
                rank=1,
                possession_number=1,
                period_label="Q1",
                clock="10:00",
                description="Jump Shot",
                win_probability_before=0.55,
                win_probability_after=0.65,
                win_probability_added=0.10,
            )
        ],
    )
    return GamePulseArtifact(
        default_game_id=game.game_id,
        target_team="GS",
        target_season=2026,
        data_cutoff_at=now,
        frozen_at=now,
        model_card=card,
        games=[game],
        sources=[SourceRecord(name="test", detail="test")],
        caveats=["test"],
    )


@pytest.fixture
def artifact_path(tmp_path: Path) -> Path:
    path = tmp_path / "game_pulse.json"
    freeze_artifact(sample_artifact(), path)
    return path
