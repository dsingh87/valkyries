from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import NormalDist

from valkyries.api_models import Brief, ModelRun
from valkyries.database import Database
from valkyries.recommend import (
    build_recommendations,
    build_scenarios,
    persist_scenarios,
)


def freeze_brief(
    database: Database,
    *,
    model_run: ModelRun,
    target_game_id: str,
    scheduled_at: datetime,
    output_path: Path,
    defense_tolerance: float = 2.0,
) -> Brief:
    scenarios = build_scenarios(
        database,
        model_run=model_run,
        target_game_id=target_game_id,
        defense_tolerance=defense_tolerance,
    )
    recommendations = build_recommendations(scenarios)
    persist_scenarios(database, scenarios, recommendations)
    normal = NormalDist()
    sensitivity: dict[str, int] = {}
    for tolerance in (0, 1, 2):
        qualifying_at_tolerance = 0
        for scenario in scenarios:
            interval_width = (
                scenario.defense_interval_80[1] - scenario.defense_interval_80[0]
            )
            standard_error = max(interval_width / (2 * 1.2816), 0.01)
            probability = normal.cdf(
                (tolerance - scenario.defensive_change_pp100) / standard_error
            )
            qualifying_at_tolerance += probability >= 0.75
        sensitivity[str(tolerance)] = qualifying_at_tolerance
    frozen_at = datetime.now(UTC)
    qualifying = sum(scenario.meets_guardrail for scenario in scenarios)
    direct_answer = (
        f"{qualifying} observed Golden State lineup groups clear the default "
        f"defensive-risk screen. The three highest-ranked groups are candidates "
        "for bounded stints, not prescriptions for a coaching rotation."
    )
    brief = Brief(
        target_game_id=target_game_id,
        matchup="Toronto Tempo at Golden State Valkyries",
        scheduled_at=scheduled_at,
        data_cutoff_at=model_run.cutoff_at,
        frozen_at=frozen_at,
        question=(
            "Which feasible Golden State lineup adjustments project to improve "
            "half-court offense against Toronto without materially weakening defense?"
        ),
        direct_answer=direct_answer,
        defense_tolerance_pp100=defense_tolerance,
        model_run=model_run,
        recommendations=recommendations,
        scenarios=scenarios,
        sensitivity=sensitivity,
        sources=[
            {
                "label": "ESPN WNBA scoreboard and game summaries",
                "url": "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard",
            },
            {
                "label": "Official WNBA August 4 game page",
                "url": "https://www.wnba.com/game/tor-vs-gsv-1022600225",
            },
        ],
        caveats=[
            "Half-court possessions use a seven-second public play-by-play proxy; sensitivity is also calculated at five and nine seconds.",
            "Lineup estimates are observational and partially pooled. They do not identify causal rotation effects.",
            "Feature ablations found no material holdout gain from lineup, opponent-style, or rest inputs; recommendation confidence is directional.",
            "The nominal 80% PyMC posterior-predictive interval covered 67.1% of holdout aggregates and is not calibrated.",
            "Public events cannot reliably identify defensive coverages, screening actions, or off-ball responsibilities.",
            "The pregame artifact is immutable; postgame data is evaluated only through the separate audit path.",
        ],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = brief.model_dump_json(indent=2)
    output_path.write_text(serialized)
    checksum_path = output_path.with_suffix(output_path.suffix + ".sha256")
    checksum_path.write_text(
        hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        + f"  {output_path.name}\n"
    )
    return brief


def load_brief(path: Path) -> Brief:
    return Brief.model_validate_json(path.read_text())


def latest_model_run(database: Database) -> ModelRun:
    rows = database.query(
        "SELECT * FROM model_runs WHERE status = 'complete' ORDER BY created_at DESC LIMIT 1"
    )
    if not rows:
        raise ValueError("no completed model run is available")
    row = rows[0]
    metrics_payload = json.loads(row["metrics_json"])
    baseline = metrics_payload.get("baseline", {})
    xgboost = metrics_payload.get("xgboost", {})
    pymc = metrics_payload.get("pymc", {})
    return ModelRun(
        model_run_id=row["model_run_id"],
        cutoff_at=row["cutoff_at"],
        data_hash=row["data_hash"],
        feature_schema_hash=row["feature_schema_hash"],
        algorithm=row["algorithm"],
        metrics={
            "baseline_mae": baseline.get("mae"),
            "baseline_rmse": baseline.get("rmse"),
            "baseline_calibration_error": baseline.get("calibration_error"),
            "baseline_game_rating_mae": baseline.get("game_rating_mae"),
            "xgboost_mae": xgboost.get("mae"),
            "xgboost_rmse": xgboost.get("rmse"),
            "xgboost_calibration_error": xgboost.get("calibration_error"),
            "xgboost_game_rating_mae": xgboost.get("game_rating_mae"),
            "xgboost_wins_gate": metrics_payload.get("xgboost_wins_gate"),
            "pymc_interval_coverage_80": pymc.get("interval_coverage_80"),
        },
        status=row["status"],
        created_at=row["created_at"],
    )
