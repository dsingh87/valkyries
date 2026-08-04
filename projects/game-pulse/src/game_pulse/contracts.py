from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetricInterval(StrictModel):
    low: float
    high: float


class ModelMetrics(StrictModel):
    possession_brier: float = Field(ge=0, le=1)
    game_balanced_brier: float = Field(ge=0, le=1)
    log_loss: float = Field(ge=0)
    calibration_error: float = Field(ge=0, le=1)
    late_game_brier: float = Field(ge=0, le=1)
    brier_interval_95: MetricInterval | None = None


class ModelResult(StrictModel):
    name: str
    algorithm: str
    complexity_rank: int = Field(ge=0)
    promoted: bool
    promotion_note: str
    selection: ModelMetrics
    test: ModelMetrics


class CalibrationBin(StrictModel):
    bin_number: int = Field(ge=1)
    observations: int = Field(ge=1)
    mean_prediction: float = Field(ge=0, le=1)
    observed_win_rate: float = Field(ge=0, le=1)


class SplitSummary(StrictModel):
    train_games: int = Field(ge=1)
    validation_games: int = Field(ge=1)
    calibration_games: int = Field(ge=1)
    selection_games: int = Field(ge=1)
    test_games: int = Field(ge=1)
    train_end: datetime
    validation_end: datetime
    calibration_end: datetime
    selection_end: datetime
    test_start: datetime


class ModelCard(StrictModel):
    model_run_id: str
    champion: str
    built_at: datetime
    cutoff_at: datetime
    data_hash: str
    feature_schema_hash: str
    random_seed: int
    split: SplitSummary
    models: list[ModelResult]
    calibration: list[CalibrationBin]
    promotion_rule: str
    features: list[str]
    sequence_features: list[str]
    caveats: list[str]


class TimelinePoint(StrictModel):
    possession_number: int = Field(ge=0)
    period: int = Field(ge=1)
    period_label: str
    clock: str
    elapsed_seconds: int = Field(ge=0)
    valkyries_margin: int
    valkyries_possession: bool
    win_probability: float = Field(ge=0, le=1)
    next_win_probability: float = Field(ge=0, le=1)
    win_probability_added: float = Field(ge=-1, le=1)
    leverage: float = Field(ge=0, le=1)
    description: str
    synthetic: bool = False


class TurningPoint(StrictModel):
    rank: int = Field(ge=1, le=5)
    possession_number: int = Field(ge=1)
    period_label: str
    clock: str
    description: str
    win_probability_before: float = Field(ge=0, le=1)
    win_probability_after: float = Field(ge=0, le=1)
    win_probability_added: float = Field(ge=-1, le=1)


class GameSummary(StrictModel):
    game_id: str
    game_date: datetime
    matchup: str
    opponent: str
    location: str
    valkyries_score: int = Field(ge=0)
    opponent_score: int = Field(ge=0)
    result: str
    opening_win_probability: float = Field(ge=0, le=1)
    minimum_win_probability: float = Field(ge=0, le=1)
    maximum_win_probability: float = Field(ge=0, le=1)
    largest_swing: float = Field(ge=0, le=1)


class GameDetail(GameSummary):
    timeline: list[TimelinePoint]
    turning_points: list[TurningPoint]


class SourceRecord(StrictModel):
    name: str
    detail: str


class GamePulseArtifact(StrictModel):
    schema_version: str = "1.0"
    default_game_id: str
    target_team: str
    target_season: int
    data_cutoff_at: datetime
    frozen_at: datetime
    model_card: ModelCard
    games: list[GameDetail]
    sources: list[SourceRecord]
    caveats: list[str]


class HealthStatus(StrictModel):
    status: str
    schema_version: str
    artifact_frozen_at: datetime
    data_cutoff_at: datetime
    model_run_id: str
    champion: str
    default_game_id: str
    games_available: int = Field(ge=0)
