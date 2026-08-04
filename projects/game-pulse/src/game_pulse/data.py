from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

CONTEXT_COLUMNS = (
    "home_margin",
    "period",
    "period_seconds_remaining",
    "game_seconds_remaining",
    "is_home_offense",
    "rolling_net_advantage",
    "rest_advantage",
    "rolling_missing",
    "rest_missing",
    "pressure",
)

SEQUENCE_COLUMNS = (
    "valid",
    "home_score_delta",
    "duration_seconds",
    "home_offense",
    "half_court",
    "action_turnover",
    "action_free_throw",
    "action_field_goal",
    "action_rebound",
    "action_other",
)

ELIGIBLE_QUERY = """
SELECT
    p.possession_id,
    p.game_id,
    p.possession_number,
    p.period,
    p.start_elapsed_seconds,
    p.end_elapsed_seconds,
    p.duration_seconds,
    p.points,
    p.margin_before,
    p.is_home_offense,
    p.is_half_court_7,
    p.terminal_action,
    e.description,
    g.season,
    g.game_date,
    g.home_team_id,
    g.home_team_abbreviation,
    g.home_score,
    g.away_team_id,
    g.away_team_abbreviation,
    g.away_score,
    home_features.rolling_half_court_off_rating AS home_rolling_off,
    home_features.rolling_half_court_def_rating AS home_rolling_def,
    home_features.rest_days AS home_rest_days,
    away_features.rolling_half_court_off_rating AS away_rolling_off,
    away_features.rolling_half_court_def_rating AS away_rolling_def,
    away_features.rest_days AS away_rest_days
FROM possessions p
JOIN games g ON g.game_id = p.game_id
JOIN events e
    ON e.game_id = p.game_id
    AND e.event_id = p.terminal_event_id
LEFT JOIN pregame_matchups home_features
    ON home_features.game_id = p.game_id
    AND home_features.team_id = g.home_team_id
LEFT JOIN pregame_matchups away_features
    ON away_features.game_id = p.game_id
    AND away_features.team_id = g.away_team_id
WHERE p.score_correction = 0
  AND g.game_date <= {placeholder}
  AND g.home_team_abbreviation NOT IN ('WNBASTARS', 'COOP')
  AND g.away_team_abbreviation NOT IN ('WNBASTARS', 'COOP')
ORDER BY g.game_date, p.game_id, p.possession_number
"""


class DataDependencyError(RuntimeError):
    """Raised when the offline analytics environment is unavailable."""


@dataclass(frozen=True)
class ChronologicalSplit:
    train_games: tuple[str, ...]
    validation_games: tuple[str, ...]
    calibration_games: tuple[str, ...]
    selection_games: tuple[str, ...]
    test_games: tuple[str, ...]

    def groups(self) -> tuple[tuple[str, ...], ...]:
        return (
            self.train_games,
            self.validation_games,
            self.calibration_games,
            self.selection_games,
            self.test_games,
        )


def _rows(database_url: str, cutoff: datetime) -> list[dict[str, Any]]:
    placeholder = "?"
    query = ELIGIBLE_QUERY.format(placeholder=placeholder)
    if database_url.startswith("sqlite:///"):
        path = database_url.removeprefix("sqlite:///")
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        try:
            return [
                dict(row)
                for row in connection.execute(query, (cutoff.isoformat(),)).fetchall()
            ]
        finally:
            connection.close()
    if database_url.startswith(("postgres://", "postgresql://")):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise DataDependencyError(
                "Postgres training requires the 'database' optional dependency"
            ) from error
        query = ELIGIBLE_QUERY.format(placeholder="%s")
        with psycopg.connect(database_url, row_factory=dict_row) as pg_connection:
            with pg_connection.cursor() as cursor:
                cursor.execute(query, (cutoff.isoformat(),))
                return [dict(row) for row in cursor.fetchall()]
    raise ValueError("database URL must start with sqlite:/// or postgresql://")


def period_seconds_remaining(period: int, elapsed_seconds: int) -> int:
    if period <= 4:
        period_start = (period - 1) * 600
        duration = 600
    else:
        period_start = 2400 + (period - 5) * 300
        duration = 300
    return max(duration - (elapsed_seconds - period_start), 0)


def display_clock(period: int, elapsed_seconds: int) -> str:
    remaining = period_seconds_remaining(period, elapsed_seconds)
    minutes, seconds = divmod(remaining, 60)
    return f"{minutes}:{seconds:02d}"


def period_label(period: int) -> str:
    return f"Q{period}" if period <= 4 else f"OT{period - 4}"


def home_margin_before(margin_before: int, is_home_offense: bool) -> int:
    return margin_before if is_home_offense else -margin_before


def home_score_delta(points: int, is_home_offense: bool) -> int:
    return points if is_home_offense else -points


def action_bucket(action: str, points: int) -> str:
    normalized = action.casefold()
    if "turnover" in normalized or "bad pass" in normalized:
        return "turnover"
    if "free throw" in normalized:
        return "free_throw"
    if "rebound" in normalized:
        return "rebound"
    if points > 0 or any(
        token in normalized for token in ("shot", "layup", "dunk", "jumper", "hook")
    ):
        return "field_goal"
    return "other"


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise DataDependencyError(
            "feature building requires the 'modeling' optional dependency"
        ) from error
    return pd


def load_feature_frame(database_url: str, cutoff: datetime) -> Any:
    pd = _require_pandas()
    frame = pd.DataFrame(_rows(database_url, cutoff))
    if frame.empty:
        raise ValueError("no eligible possessions found before the cutoff")
    frame["game_date"] = pd.to_datetime(frame["game_date"], utc=True)
    frame["home_margin"] = [
        home_margin_before(int(margin), bool(is_home))
        for margin, is_home in zip(
            frame["margin_before"], frame["is_home_offense"], strict=True
        )
    ]
    frame["period_seconds_remaining"] = [
        period_seconds_remaining(int(period), int(elapsed))
        for period, elapsed in zip(
            frame["period"], frame["start_elapsed_seconds"], strict=True
        )
    ]
    frame["game_seconds_remaining"] = frame.apply(
        lambda row: (
            max(2400 - int(row["start_elapsed_seconds"]), 0)
            if int(row["period"]) <= 4
            else int(row["period_seconds_remaining"])
        ),
        axis=1,
    )
    home_net = frame["home_rolling_off"] - frame["home_rolling_def"]
    away_net = frame["away_rolling_off"] - frame["away_rolling_def"]
    frame["rolling_net_advantage"] = home_net - away_net
    frame["rest_advantage"] = frame["home_rest_days"] - frame["away_rest_days"]
    frame["rolling_missing"] = (
        frame[
            [
                "home_rolling_off",
                "home_rolling_def",
                "away_rolling_off",
                "away_rolling_def",
            ]
        ]
        .isna()
        .any(axis=1)
        .astype(int)
    )
    frame["rest_missing"] = (
        frame[["home_rest_days", "away_rest_days"]].isna().any(axis=1).astype(int)
    )
    frame["pressure"] = frame["home_margin"] / frame["game_seconds_remaining"].add(
        30
    ).div(60).pow(0.5)
    frame["home_win"] = (frame["home_score"] > frame["away_score"]).astype(int)
    frame["home_score_delta"] = [
        home_score_delta(int(points), bool(is_home))
        for points, is_home in zip(
            frame["points"], frame["is_home_offense"], strict=True
        )
    ]
    frame["home_offense"] = frame["is_home_offense"].astype(int)
    frame["half_court"] = frame["is_half_court_7"].astype(int)
    buckets = [
        action_bucket(str(action), int(points))
        for action, points in zip(
            frame["terminal_action"], frame["points"], strict=True
        )
    ]
    for name in ("turnover", "free_throw", "field_goal", "rebound", "other"):
        frame[f"action_{name}"] = [int(bucket == name) for bucket in buckets]
    frame["valid"] = 1
    frame = frame.sort_values(
        ["game_date", "game_id", "possession_number"]
    ).reset_index(drop=True)
    return frame


def make_sequences(frame: Any, *, length: int = 10) -> Any:
    try:
        import numpy as np
    except ImportError as error:
        raise DataDependencyError(
            "sequence building requires the 'modeling' optional dependency"
        ) from error
    sequences = np.zeros((len(frame), length, len(SEQUENCE_COLUMNS)), dtype=np.float32)
    for positions in frame.groupby("game_id", sort=False).indices.values():
        ordered = sorted(int(position) for position in positions)
        outcomes = frame.loc[ordered, list(SEQUENCE_COLUMNS)].to_numpy(dtype=float)
        for local_index, global_index in enumerate(ordered):
            start = max(0, local_index - length)
            history = outcomes[start:local_index]
            if len(history):
                sequences[global_index, -len(history) :] = history
    return sequences


def chronological_split(frame: Any, *, test_season: int) -> ChronologicalSplit:
    games = (
        frame[["game_id", "game_date", "season"]]
        .drop_duplicates("game_id")
        .sort_values(["game_date", "game_id"])
    )
    pretest = games[games["season"] < test_season]
    test = games[games["season"] == test_season]
    if len(pretest) < 20 or test.empty:
        raise ValueError("chronological split requires pretest and test-season games")
    count = len(pretest)
    train_end = max(int(count * 0.65), 1)
    validation_end = max(int(count * 0.80), train_end + 1)
    calibration_end = max(int(count * 0.90), validation_end + 1)
    selection_end = count
    ids = pretest["game_id"].astype(str).tolist()
    split = ChronologicalSplit(
        train_games=tuple(ids[:train_end]),
        validation_games=tuple(ids[train_end:validation_end]),
        calibration_games=tuple(ids[validation_end:calibration_end]),
        selection_games=tuple(ids[calibration_end:selection_end]),
        test_games=tuple(test["game_id"].astype(str)),
    )
    flattened = [game for group in split.groups() for game in group]
    if len(flattened) != len(set(flattened)):
        raise AssertionError("a game appears in multiple chronological splits")
    return split


def frame_hash(frame: Any) -> str:
    columns = [
        "possession_id",
        "game_id",
        "game_date",
        *CONTEXT_COLUMNS,
        *SEQUENCE_COLUMNS,
        "home_win",
    ]
    digest = hashlib.sha256()
    for record in frame[columns].to_dict(orient="records"):
        digest.update(
            json.dumps(
                record, default=str, sort_keys=True, separators=(",", ":")
            ).encode()
        )
        digest.update(b"\n")
    return digest.hexdigest()


def feature_schema_hash() -> str:
    payload = {
        "context": CONTEXT_COLUMNS,
        "sequence": SEQUENCE_COLUMNS,
        "sequence_length": 10,
        "pressure": "home_margin / sqrt((game_seconds_remaining + 30) / 60)",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def validate_frame(frame: Any) -> None:
    required = {
        "game_id",
        "game_date",
        "season",
        "home_win",
        *CONTEXT_COLUMNS,
        *SEQUENCE_COLUMNS,
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"feature frame is missing columns: {sorted(missing)}")
    if not frame["home_win"].isin([0, 1]).all():
        raise ValueError("home_win must be binary")
    if frame.duplicated(["game_id", "possession_number"]).any():
        raise ValueError("possession numbers must be unique within a game")
    if (
        not frame.groupby("game_id")["possession_number"]
        .apply(lambda values: values.is_monotonic_increasing)
        .all()
    ):
        raise ValueError("possessions must be ordered within every game")
    if not frame["period_seconds_remaining"].between(0, 600).all():
        raise ValueError("period time remaining is outside the supported range")
    if not frame["pressure"].map(math.isfinite).all():
        raise ValueError("pressure contains non-finite values")
