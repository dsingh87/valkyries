from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelRun(StrictModel):
    model_run_id: str
    cutoff_at: datetime
    data_hash: str
    feature_schema_hash: str
    algorithm: str
    metrics: dict[str, float | str | bool | None]
    status: str
    created_at: datetime


class ScenarioPrediction(StrictModel):
    prediction_id: str
    model_run_id: str
    target_game_id: str
    lineup_ids: list[str] = Field(min_length=5, max_length=5)
    lineup_names: list[str] = Field(min_length=5, max_length=5)
    expected_offense_pp100: float
    offense_interval_80: tuple[float, float]
    offensive_lift_pp100: float
    expected_defense_pp100: float
    defense_interval_80: tuple[float, float]
    defensive_change_pp100: float
    guardrail_probability: float = Field(ge=0, le=1)
    sample_possessions: int = Field(ge=0)
    meets_guardrail: bool


class Recommendation(StrictModel):
    recommendation_id: str
    rank: int = Field(ge=1)
    prediction_id: str
    adjustment: str
    evidence: str
    confidence: str
    caveat: str


class Brief(StrictModel):
    schema_version: str = "1.0"
    target_game_id: str
    matchup: str
    scheduled_at: datetime
    data_cutoff_at: datetime
    frozen_at: datetime
    question: str
    direct_answer: str
    defense_tolerance_pp100: float
    model_run: ModelRun
    recommendations: list[Recommendation]
    scenarios: list[ScenarioPrediction]
    sensitivity: dict[str, int]
    sources: list[dict[str, str]]
    caveats: list[str]


class HealthStatus(StrictModel):
    status: str
    source_freshness_at: datetime
    last_successful_pipeline_at: datetime | None
    published_model_version: str
    target_game_id: str
    artifact_frozen_at: datetime
