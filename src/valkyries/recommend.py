from __future__ import annotations

import hashlib
import math
from datetime import timedelta
from statistics import NormalDist

from valkyries.api_models import ModelRun, Recommendation, ScenarioPrediction
from valkyries.database import Database


def _stable_id(*parts: object) -> str:
    return hashlib.sha256(":".join(map(str, parts)).encode("utf-8")).hexdigest()[:24]


def _team_id(database: Database, abbreviation: str) -> str:
    p = database.placeholder
    rows = database.query(
        f"""
        SELECT home_team_id AS team_id FROM games WHERE home_team_abbreviation = {p}
        UNION
        SELECT away_team_id AS team_id FROM games WHERE away_team_abbreviation = {p}
        LIMIT 1
        """,
        (abbreviation, abbreviation),
    )
    if not rows:
        raise ValueError(f"team {abbreviation!r} is not present in the database")
    return str(rows[0]["team_id"])


def _team_baseline(
    database: Database, team_id: str, *, season: int
) -> tuple[float, float]:
    p = database.placeholder
    rows = database.query(
        f"""
        SELECT
            100.0 * SUM(CASE WHEN offense_team_id = {p} AND is_half_court_7 = 1 THEN points ELSE 0 END)
                / NULLIF(SUM(CASE WHEN offense_team_id = {p} AND is_half_court_7 = 1 THEN 1 ELSE 0 END), 0) AS offense_rating,
            100.0 * SUM(CASE WHEN defense_team_id = {p} AND is_half_court_7 = 1 THEN points ELSE 0 END)
                / NULLIF(SUM(CASE WHEN defense_team_id = {p} AND is_half_court_7 = 1 THEN 1 ELSE 0 END), 0) AS defense_rating
        FROM possessions pz
        JOIN games g ON g.game_id = pz.game_id
        WHERE pz.score_correction = 0
          AND CAST(SUBSTR(g.game_date, 1, 4) AS INTEGER) = {p}
        """,
        (team_id, team_id, team_id, team_id, season),
    )
    if not rows or rows[0]["offense_rating"] is None:
        raise ValueError("team baseline cannot be computed")
    return float(rows[0]["offense_rating"]), float(rows[0]["defense_rating"])


def _matchup_context(
    database: Database,
    *,
    team_id: str,
    opponent_id: str,
    season: int,
) -> dict[str, float]:
    """Return current-season league, opponent, and direct-matchup context."""
    p = database.placeholder
    rows = database.query(
        f"""
        SELECT
            100.0 * SUM(CASE WHEN is_half_court_7 = 1 THEN points ELSE 0 END)
                / NULLIF(SUM(CASE WHEN is_half_court_7 = 1 THEN 1 ELSE 0 END), 0) AS league_rating,
            100.0 * SUM(CASE WHEN offense_team_id = {p} AND is_half_court_7 = 1 THEN points ELSE 0 END)
                / NULLIF(SUM(CASE WHEN offense_team_id = {p} AND is_half_court_7 = 1 THEN 1 ELSE 0 END), 0) AS opponent_offense,
            100.0 * SUM(CASE WHEN defense_team_id = {p} AND is_half_court_7 = 1 THEN points ELSE 0 END)
                / NULLIF(SUM(CASE WHEN defense_team_id = {p} AND is_half_court_7 = 1 THEN 1 ELSE 0 END), 0) AS opponent_defense,
            100.0 * SUM(CASE WHEN offense_team_id = {p} AND defense_team_id = {p} AND is_half_court_7 = 1 THEN points ELSE 0 END)
                / NULLIF(SUM(CASE WHEN offense_team_id = {p} AND defense_team_id = {p} AND is_half_court_7 = 1 THEN 1 ELSE 0 END), 0) AS direct_offense,
            SUM(CASE WHEN offense_team_id = {p} AND defense_team_id = {p} AND is_half_court_7 = 1 THEN 1 ELSE 0 END) AS direct_offense_n,
            100.0 * SUM(CASE WHEN offense_team_id = {p} AND defense_team_id = {p} AND is_half_court_7 = 1 THEN points ELSE 0 END)
                / NULLIF(SUM(CASE WHEN offense_team_id = {p} AND defense_team_id = {p} AND is_half_court_7 = 1 THEN 1 ELSE 0 END), 0) AS direct_defense,
            SUM(CASE WHEN offense_team_id = {p} AND defense_team_id = {p} AND is_half_court_7 = 1 THEN 1 ELSE 0 END) AS direct_defense_n
        FROM possessions pz
        JOIN games g ON g.game_id = pz.game_id
        WHERE pz.score_correction = 0
          AND CAST(SUBSTR(g.game_date, 1, 4) AS INTEGER) = {p}
        """,
        (
            opponent_id,
            opponent_id,
            opponent_id,
            opponent_id,
            team_id,
            opponent_id,
            team_id,
            opponent_id,
            team_id,
            opponent_id,
            opponent_id,
            team_id,
            opponent_id,
            team_id,
            opponent_id,
            team_id,
            season,
        ),
    )
    if not rows or rows[0]["league_rating"] is None:
        raise ValueError("matchup context cannot be computed")
    row = rows[0]
    return {
        key: float(row[key] or 0.0)
        for key in (
            "league_rating",
            "opponent_offense",
            "opponent_defense",
            "direct_offense",
            "direct_offense_n",
            "direct_defense",
            "direct_defense_n",
        )
    }


def _lineup_names(database: Database, lineup_ids: list[str]) -> list[str]:
    names = {
        row["athlete_id"]: row["display_name"]
        for row in database.query(
            """
            SELECT athlete_id, MAX(display_name) AS display_name
            FROM athletes
            GROUP BY athlete_id
            """
        )
    }
    return [str(names.get(player_id, player_id)) for player_id in lineup_ids]


def build_scenarios(
    database: Database,
    *,
    model_run: ModelRun,
    target_game_id: str,
    team_abbreviation: str = "GS",
    opponent_abbreviation: str = "TOR",
    defense_tolerance: float = 2.0,
    minimum_possessions: int = 10,
) -> list[ScenarioPrediction]:
    team_id = _team_id(database, team_abbreviation)
    opponent_id = _team_id(database, opponent_abbreviation)
    season = model_run.cutoff_at.year
    baseline_offense, baseline_defense = _team_baseline(
        database, team_id, season=season
    )
    matchup = _matchup_context(
        database,
        team_id=team_id,
        opponent_id=opponent_id,
        season=season,
    )
    style_weight = 0.35
    direct_offense_weight = min(matchup["direct_offense_n"] / 300.0, 0.35)
    direct_defense_weight = min(matchup["direct_defense_n"] / 300.0, 0.35)
    matchup_baseline_offense = baseline_offense + style_weight * (
        matchup["opponent_defense"] - matchup["league_rating"]
    )
    matchup_baseline_defense = baseline_defense + style_weight * (
        matchup["opponent_offense"] - matchup["league_rating"]
    )
    if matchup["direct_offense_n"]:
        matchup_baseline_offense += direct_offense_weight * (
            matchup["direct_offense"] - matchup_baseline_offense
        )
    if matchup["direct_defense_n"]:
        matchup_baseline_defense += direct_defense_weight * (
            matchup["direct_defense"] - matchup_baseline_defense
        )
    recent_start = (model_run.cutoff_at - timedelta(days=45)).isoformat()
    p = database.placeholder
    rows = database.query(
        f"""
        WITH recent_lineups AS (
            SELECT DISTINCT
                CASE
                    WHEN ls.home_team_id = {p} THEN ls.home_lineup
                    ELSE ls.away_lineup
                END AS lineup_key
            FROM lineup_stints ls
            JOIN games g ON g.game_id = ls.game_id
            WHERE (ls.home_team_id = {p} OR ls.away_team_id = {p})
              AND g.game_date >= {p}
              AND g.game_date <= {p}
        )
        SELECT lf.*
        FROM lineup_features lf
        JOIN recent_lineups rl ON rl.lineup_key = lf.lineup_key
        WHERE lf.team_id = {p}
          AND lf.half_court_possessions_for >= {p}
          AND lf.half_court_possessions_against >= {p}
        """,
        (
            team_id,
            team_id,
            team_id,
            recent_start,
            model_run.cutoff_at.isoformat(),
            team_id,
            minimum_possessions,
            minimum_possessions,
        ),
    )
    if not rows:
        raise ValueError("no Golden State lineups have enough validated possessions")
    prior_strength = 25.0
    normal = NormalDist()
    scenarios: list[ScenarioPrediction] = []
    for row in rows:
        offense_n = int(row["half_court_possessions_for"])
        defense_n = int(row["half_court_possessions_against"])
        offense_points = float(row["half_court_points_for"])
        defense_points = float(row["half_court_points_against"])
        lineup_offense_rate = (
            100.0
            * (offense_points + prior_strength * baseline_offense / 100.0)
            / (offense_n + prior_strength)
        )
        lineup_defense_rate = (
            100.0
            * (defense_points + prior_strength * baseline_defense / 100.0)
            / (defense_n + prior_strength)
        )
        offense_rate = lineup_offense_rate + (
            matchup_baseline_offense - baseline_offense
        )
        defense_rate = lineup_defense_rate + (
            matchup_baseline_defense - baseline_defense
        )
        offense_se = 100.0 * math.sqrt(
            max(offense_rate / 100.0, 0.01) / (offense_n + prior_strength)
        )
        defense_se = 100.0 * math.sqrt(
            max(defense_rate / 100.0, 0.01) / (defense_n + prior_strength)
        )
        guardrail_limit = matchup_baseline_defense + defense_tolerance
        probability = normal.cdf((guardrail_limit - defense_rate) / defense_se)
        lineup_ids = str(row["lineup_key"]).split("|")
        if len(lineup_ids) != 5:
            continue
        prediction_id = _stable_id(
            model_run.model_run_id, target_game_id, row["lineup_key"]
        )
        scenarios.append(
            ScenarioPrediction(
                prediction_id=prediction_id,
                model_run_id=model_run.model_run_id,
                target_game_id=target_game_id,
                lineup_ids=lineup_ids,
                lineup_names=_lineup_names(database, lineup_ids),
                expected_offense_pp100=round(offense_rate, 1),
                offense_interval_80=(
                    round(max(offense_rate - 1.2816 * offense_se, 0), 1),
                    round(offense_rate + 1.2816 * offense_se, 1),
                ),
                offensive_lift_pp100=round(offense_rate - matchup_baseline_offense, 1),
                expected_defense_pp100=round(defense_rate, 1),
                defense_interval_80=(
                    round(max(defense_rate - 1.2816 * defense_se, 0), 1),
                    round(defense_rate + 1.2816 * defense_se, 1),
                ),
                defensive_change_pp100=round(
                    defense_rate - matchup_baseline_defense, 1
                ),
                guardrail_probability=round(probability, 4),
                sample_possessions=min(offense_n, defense_n),
                meets_guardrail=probability >= 0.75,
            )
        )
    return sorted(
        scenarios,
        key=lambda scenario: (
            scenario.meets_guardrail,
            scenario.offensive_lift_pp100,
            scenario.guardrail_probability,
        ),
        reverse=True,
    )


def build_recommendations(
    scenarios: list[ScenarioPrediction],
    *,
    limit: int = 3,
) -> list[Recommendation]:
    selected = [scenario for scenario in scenarios if scenario.meets_guardrail][:limit]
    if len(selected) < limit:
        selected_ids = {scenario.prediction_id for scenario in selected}
        selected.extend(
            scenario
            for scenario in scenarios
            if scenario.prediction_id not in selected_ids
        )
        selected = selected[:limit]
    recommendations: list[Recommendation] = []
    for rank, scenario in enumerate(selected, start=1):
        confidence = (
            "moderate"
            if scenario.meets_guardrail and scenario.sample_possessions >= 20
            else "directional"
        )
        recommendations.append(
            Recommendation(
                recommendation_id=_stable_id(scenario.prediction_id, rank),
                rank=rank,
                prediction_id=scenario.prediction_id,
                adjustment=(
                    "Test the observed five-player group of "
                    + ", ".join(scenario.lineup_names)
                    + " in a bounded stint."
                ),
                evidence=(
                    f"Toronto-adjusted, shrunk half-court estimate: "
                    f"{scenario.expected_offense_pp100:.1f} "
                    f"points scored and {scenario.expected_defense_pp100:.1f} points "
                    f"allowed per 100 possessions; {scenario.sample_possessions} "
                    "validated lineup possessions support both sides, with the July 8 "
                    "and August 2 matchups included in the opponent adjustment."
                ),
                confidence=confidence,
                caveat=(
                    "This is a partial-pooling observational estimate, not a causal "
                    "claim about changing the rotation. Opponent assignments and "
                    "unobserved tactical context may explain part of the difference."
                ),
            )
        )
    return recommendations


def persist_scenarios(
    database: Database,
    scenarios: list[ScenarioPrediction],
    recommendations: list[Recommendation],
) -> None:
    if not scenarios:
        return
    p = database.placeholder
    model_run_id = scenarios[0].model_run_id
    target_game_id = scenarios[0].target_game_id
    database.execute(
        f"DELETE FROM recommendations WHERE model_run_id = {p} AND target_game_id = {p}",
        (model_run_id, target_game_id),
    )
    database.execute(
        f"DELETE FROM predictions WHERE model_run_id = {p} AND target_game_id = {p}",
        (model_run_id, target_game_id),
    )
    database.executemany(
        f"INSERT INTO predictions VALUES ({','.join([p] * 13)})",
        [
            (
                scenario.prediction_id,
                scenario.model_run_id,
                scenario.target_game_id,
                "|".join(scenario.lineup_ids),
                "|".join(scenario.lineup_names),
                scenario.expected_offense_pp100,
                scenario.offense_interval_80[0],
                scenario.offense_interval_80[1],
                scenario.expected_defense_pp100,
                scenario.defense_interval_80[0],
                scenario.defense_interval_80[1],
                scenario.guardrail_probability,
                scenario.sample_possessions,
            )
            for scenario in scenarios
        ],
    )
    database.executemany(
        f"INSERT INTO recommendations VALUES ({','.join([p] * 9)})",
        [
            (
                recommendation.recommendation_id,
                model_run_id,
                target_game_id,
                recommendation.rank,
                recommendation.prediction_id,
                recommendation.adjustment,
                recommendation.evidence,
                recommendation.confidence,
                recommendation.caveat,
            )
            for recommendation in recommendations
        ],
    )
