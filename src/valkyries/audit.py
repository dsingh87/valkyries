from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from valkyries.api_models import Brief
from valkyries.database import Database


def audit_game(
    database: Database,
    *,
    brief: Brief,
    output_path: Path,
) -> dict[str, Any]:
    p = database.placeholder
    games = database.query(
        f"SELECT * FROM games WHERE game_id = {p}", (brief.target_game_id,)
    )
    if not games:
        result: dict[str, Any] = {
            "schema_version": "1.0",
            "target_game_id": brief.target_game_id,
            "status": "pending",
            "audited_at": datetime.now(UTC).isoformat(),
            "message": "The target game is not complete in the validated store.",
            "frozen_artifact_hash": brief.model_run.data_hash,
        }
    else:
        actual = database.query(
            f"""
            SELECT
                offense_lineup AS lineup_key,
                COUNT(*) AS half_court_possessions,
                SUM(points) AS half_court_points
            FROM possessions
            WHERE game_id = {p} AND is_half_court_7 = 1
            GROUP BY offense_lineup
            """,
            (brief.target_game_id,),
        )
        actual_by_lineup = {row["lineup_key"]: row for row in actual}
        comparisons = []
        for scenario in brief.scenarios:
            lineup_key = "|".join(sorted(scenario.lineup_ids))
            row = actual_by_lineup.get(lineup_key)
            if row is None or not row["half_court_possessions"]:
                continue
            actual_rating = (
                100.0 * row["half_court_points"] / row["half_court_possessions"]
            )
            comparisons.append(
                {
                    "lineup_names": scenario.lineup_names,
                    "predicted_offense_pp100": scenario.expected_offense_pp100,
                    "actual_offense_pp100": round(actual_rating, 1),
                    "absolute_error": round(
                        abs(actual_rating - scenario.expected_offense_pp100), 1
                    ),
                    "actual_possessions": row["half_court_possessions"],
                }
            )
        game = games[0]
        result = {
            "schema_version": "1.0",
            "target_game_id": brief.target_game_id,
            "status": "complete",
            "audited_at": datetime.now(UTC).isoformat(),
            "final_score": {
                game["away_team_abbreviation"]: game["away_score"],
                game["home_team_abbreviation"]: game["home_score"],
            },
            "lineup_comparisons": comparisons,
            "frozen_model_run_id": brief.model_run.model_run_id,
            "note": (
                "Observed lineup outcomes are descriptive and do not validate a "
                "causal rotation effect. The original pregame artifact is unchanged."
            ),
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    return result
