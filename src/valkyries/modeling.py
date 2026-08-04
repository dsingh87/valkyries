from __future__ import annotations

import hashlib
import json
import math
import pickle
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from valkyries.api_models import ModelRun
from valkyries.database import Database

FEATURE_COLUMNS = (
    "offense_team_id",
    "defense_team_id",
    "offense_lineup",
    "defense_lineup",
    "is_home_offense",
    "offense_rolling_off_rating",
    "offense_rolling_def_rating",
    "defense_rolling_off_rating",
    "defense_rolling_def_rating",
    "offense_rest_days",
    "defense_rest_days",
)
CATEGORICAL_COLUMNS = (
    "offense_team_id",
    "defense_team_id",
    "offense_lineup",
    "defense_lineup",
)
NUMERIC_COLUMNS = (
    "is_home_offense",
    "offense_rolling_off_rating",
    "offense_rolling_def_rating",
    "defense_rolling_off_rating",
    "defense_rolling_def_rating",
    "offense_rest_days",
    "defense_rest_days",
)


class ModelingDependencyError(RuntimeError):
    """Raised when the optional modeling environment is not installed."""


@dataclass(frozen=True)
class TrainingResult:
    model_run: ModelRun
    metrics: dict[str, Any]
    champion_path: Path
    bayesian_path: Path | None


def _hash_values(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _calibration_error(actual: Any, predicted: Any) -> float:
    import numpy as np

    predicted_array = np.asarray(predicted, dtype=float)
    actual_array = np.asarray(actual, dtype=float)
    if len(predicted_array) < 10:
        return float(np.mean(np.abs(actual_array - predicted_array)))
    boundaries = np.quantile(predicted_array, np.linspace(0, 1, 11))
    bucket = np.digitize(predicted_array, boundaries[1:-1], right=True)
    errors: list[float] = []
    weights: list[int] = []
    for index in range(10):
        mask = bucket == index
        if not mask.any():
            continue
        errors.append(
            float(abs(actual_array[mask].mean() - predicted_array[mask].mean()))
        )
        weights.append(int(mask.sum()))
    return float(np.average(errors, weights=weights))


def _regression_metrics(actual: Any, predicted: Any) -> dict[str, float]:
    import numpy as np

    residual = np.asarray(actual, dtype=float) - np.asarray(predicted, dtype=float)
    return {
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(math.sqrt(float(np.mean(residual**2)))),
        "calibration_error": _calibration_error(actual, predicted),
    }


def _game_rating_mae(frame: Any, predicted: Any) -> float:
    import numpy as np

    evaluation = frame[["game_id", "points"]].copy()
    evaluation["predicted"] = np.asarray(predicted, dtype=float)
    grouped = evaluation.groupby("game_id", as_index=False).agg(
        actual_points=("points", "sum"),
        predicted_points=("predicted", "sum"),
        possessions=("points", "size"),
    )
    actual_rating = 100.0 * grouped["actual_points"] / grouped["possessions"]
    predicted_rating = 100.0 * grouped["predicted_points"] / grouped["possessions"]
    return float(np.mean(np.abs(actual_rating - predicted_rating)))


def _calibration_deciles(actual: Any, predicted: Any) -> list[dict[str, float | int]]:
    import numpy as np

    predicted_array = np.asarray(predicted, dtype=float)
    actual_array = np.asarray(actual, dtype=float)
    boundaries = np.quantile(predicted_array, np.linspace(0, 1, 11))
    bucket = np.digitize(predicted_array, boundaries[1:-1], right=True)
    result: list[dict[str, float | int]] = []
    for index in range(10):
        mask = bucket == index
        if not mask.any():
            continue
        result.append(
            {
                "decile": index + 1,
                "possessions": int(mask.sum()),
                "mean_prediction": float(predicted_array[mask].mean()),
                "mean_actual": float(actual_array[mask].mean()),
            }
        )
    return result


def _load_training_frame(database: Database, cutoff: datetime) -> Any:
    try:
        import pandas as pd
    except ImportError as error:
        raise ModelingDependencyError(
            "training requires the 'modeling' optional dependency"
        ) from error
    p = database.placeholder
    rows = database.query(
        f"""
        SELECT
            p.game_id,
            g.game_date,
            p.offense_team_id,
            p.defense_team_id,
            p.offense_lineup,
            p.defense_lineup,
            p.is_home_offense,
            offense_features.rolling_half_court_off_rating AS offense_rolling_off_rating,
            offense_features.rolling_half_court_def_rating AS offense_rolling_def_rating,
            defense_features.rolling_half_court_off_rating AS defense_rolling_off_rating,
            defense_features.rolling_half_court_def_rating AS defense_rolling_def_rating,
            offense_features.rest_days AS offense_rest_days,
            defense_features.rest_days AS defense_rest_days,
            p.points
        FROM possessions p
        JOIN games g ON g.game_id = p.game_id
        LEFT JOIN pregame_matchups offense_features
            ON offense_features.game_id = p.game_id
            AND offense_features.team_id = p.offense_team_id
        LEFT JOIN pregame_matchups defense_features
            ON defense_features.game_id = p.game_id
            AND defense_features.team_id = p.defense_team_id
        WHERE p.is_half_court_7 = 1
          AND p.score_correction = 0
          AND g.game_date <= {p}
        ORDER BY g.game_date, p.game_id, p.possession_number
        """,
        (cutoff.isoformat(),),
    )
    frame = pd.DataFrame(rows)
    if len(frame) < 100:
        raise ValueError("at least 100 half-court possessions are required to train")
    return frame


def _fit_pymc_player_effects(frame: Any, output_path: Path) -> dict[str, float]:
    try:
        import numpy as np
        import pymc as pm
    except ImportError as error:
        raise ModelingDependencyError(
            "PyMC training requires the 'modeling' optional dependency"
        ) from error

    grouped = (
        frame.groupby(["offense_lineup", "defense_lineup"], as_index=False)
        .agg(points=("points", "sum"), possessions=("points", "size"))
        .query("possessions >= 2")
    )
    player_ids = sorted(
        {
            player
            for value in (
                grouped["offense_lineup"].tolist() + grouped["defense_lineup"].tolist()
            )
            for player in value.split("|")
        }
    )
    player_index = {player_id: index for index, player_id in enumerate(player_ids)}
    offense_players = np.asarray(
        [
            [player_index[player] for player in lineup.split("|")]
            for lineup in grouped["offense_lineup"]
        ],
        dtype=int,
    )
    defense_players = np.asarray(
        [
            [player_index[player] for player in lineup.split("|")]
            for lineup in grouped["defense_lineup"]
        ],
        dtype=int,
    )
    exposure = grouped["possessions"].to_numpy(dtype=float)
    observed = grouped["points"].to_numpy(dtype=int)
    base_rate = max(observed.sum() / exposure.sum(), 0.01)

    with pm.Model(coords={"player": player_ids}):
        sigma_offense = pm.HalfNormal("sigma_offense", sigma=0.25)
        sigma_defense = pm.HalfNormal("sigma_defense", sigma=0.25)
        offense_effect = pm.Normal("offense_effect", 0, sigma_offense, dims="player")
        defense_effect = pm.Normal("defense_effect", 0, sigma_defense, dims="player")
        intercept = pm.Normal("intercept", mu=math.log(base_rate), sigma=0.4)
        log_rate = (
            intercept
            + offense_effect[offense_players].mean(axis=1)
            + defense_effect[defense_players].mean(axis=1)
        )
        expected_points = pm.Deterministic(
            "expected_points", exposure * pm.math.exp(log_rate)
        )
        pm.Poisson("points", mu=expected_points, observed=observed)
        approximation = pm.fit(
            n=3_000,
            method="advi",
            random_seed=87,
            progressbar=False,
        )
        posterior = approximation.sample(800, random_seed=87)

    expected = posterior.posterior["expected_points"].values.reshape(-1, len(grouped))
    low, high = np.quantile(expected, [0.1, 0.9], axis=0)
    coverage = float(np.mean((observed >= low) & (observed <= high)))
    offense_mean = posterior.posterior["offense_effect"].mean(("chain", "draw")).values
    offense_sd = posterior.posterior["offense_effect"].std(("chain", "draw")).values
    defense_mean = posterior.posterior["defense_effect"].mean(("chain", "draw")).values
    defense_sd = posterior.posterior["defense_effect"].std(("chain", "draw")).values
    result = {
        "method": "PyMC ADVI hierarchical player effects",
        "interval_coverage_80": coverage,
        "players": {
            player_id: {
                "offense_mean": float(offense_mean[index]),
                "offense_sd": float(offense_sd[index]),
                "defense_mean": float(defense_mean[index]),
                "defense_sd": float(defense_sd[index]),
            }
            for index, player_id in enumerate(player_ids)
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    return {"interval_coverage_80": coverage, "players": float(len(player_ids))}


def train_models(
    database: Database,
    *,
    cutoff: datetime,
    output_dir: Path,
    fit_bayesian: bool = True,
) -> TrainingResult:
    try:
        import numpy as np
        from sklearn.compose import ColumnTransformer
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import TweedieRegressor
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder, StandardScaler
        from xgboost import XGBRegressor
    except ImportError as error:
        raise ModelingDependencyError(
            "training requires scikit-learn and XGBoost; install .[modeling]"
        ) from error

    frame = _load_training_frame(database, cutoff)
    game_dates = frame.groupby("game_id")["game_date"].first().sort_values()
    split_index = max(int(len(game_dates) * 0.8), 1)
    train_games = set(game_dates.index[:split_index])
    test_games = set(game_dates.index[split_index:])
    if not test_games:
        raise ValueError("training requires at least two distinct games")
    train = frame[frame["game_id"].isin(train_games)]
    test = frame[frame["game_id"].isin(test_games)]

    def tweedie_pipeline(categorical: tuple[str, ...], numeric: tuple[str, ...]) -> Any:
        return Pipeline(
            [
                (
                    "features",
                    ColumnTransformer(
                        [
                            (
                                "categorical",
                                OneHotEncoder(handle_unknown="ignore", min_frequency=3),
                                list(categorical),
                            ),
                            (
                                "numeric",
                                Pipeline(
                                    [
                                        (
                                            "impute",
                                            SimpleImputer(strategy="median"),
                                        ),
                                        ("scale", StandardScaler(with_mean=False)),
                                    ]
                                ),
                                list(numeric),
                            ),
                        ]
                    ),
                ),
                (
                    "model",
                    TweedieRegressor(
                        power=1.2,
                        alpha=1.0,
                        link="log",
                        max_iter=500,
                    ),
                ),
            ]
        )

    baseline = tweedie_pipeline(CATEGORICAL_COLUMNS, NUMERIC_COLUMNS)
    baseline.fit(train[list(FEATURE_COLUMNS)], train["points"])
    baseline_prediction = np.clip(baseline.predict(test[list(FEATURE_COLUMNS)]), 0, 5)
    baseline_metrics = _regression_metrics(test["points"], baseline_prediction)
    baseline_metrics["game_rating_mae"] = _game_rating_mae(test, baseline_prediction)

    ablation_specs = {
        "without_lineup": (
            ("offense_team_id", "defense_team_id"),
            NUMERIC_COLUMNS,
        ),
        "without_opponent_style": (
            CATEGORICAL_COLUMNS,
            ("is_home_offense", "offense_rest_days", "defense_rest_days"),
        ),
        "without_rest": (
            CATEGORICAL_COLUMNS,
            tuple(
                column for column in NUMERIC_COLUMNS if not column.endswith("rest_days")
            ),
        ),
    }
    ablations: dict[str, dict[str, float]] = {}
    for name, (categorical, numeric) in ablation_specs.items():
        features = list(categorical + numeric)
        ablation = tweedie_pipeline(categorical, numeric)
        ablation.fit(train[features], train["points"])
        prediction = np.clip(ablation.predict(test[features]), 0, 5)
        ablation_mae = _regression_metrics(test["points"], prediction)["mae"]
        ablations[name] = {
            "mae": ablation_mae,
            "mae_delta_vs_full": ablation_mae - baseline_metrics["mae"],
        }

    xgb_preprocessor = ColumnTransformer(
        [
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", min_frequency=3),
                list(CATEGORICAL_COLUMNS),
            ),
            ("numeric", "passthrough", list(NUMERIC_COLUMNS)),
        ]
    )
    xgboost = Pipeline(
        [
            ("features", xgb_preprocessor),
            (
                "model",
                XGBRegressor(
                    objective="count:poisson",
                    n_estimators=250,
                    max_depth=4,
                    learning_rate=0.04,
                    subsample=0.85,
                    colsample_bytree=0.85,
                    reg_lambda=4.0,
                    random_state=87,
                    n_jobs=4,
                ),
            ),
        ]
    )
    xgboost.fit(train[list(FEATURE_COLUMNS)], train["points"])
    xgb_prediction = np.clip(xgboost.predict(test[list(FEATURE_COLUMNS)]), 0, 5)
    xgb_metrics = _regression_metrics(test["points"], xgb_prediction)
    xgb_metrics["game_rating_mae"] = _game_rating_mae(test, xgb_prediction)
    xgb_wins = (
        xgb_metrics["mae"] <= baseline_metrics["mae"] * 0.99
        and xgb_metrics["calibration_error"]
        <= baseline_metrics["calibration_error"] * 1.05
    )
    champion_name = "xgboost" if xgb_wins else "sklearn_tweedie"
    champion = xgboost if xgb_wins else baseline

    output_dir.mkdir(parents=True, exist_ok=True)
    champion_path = output_dir / "champion.pkl"
    with champion_path.open("wb") as handle:
        pickle.dump(champion, handle)

    bayesian_path: Path | None = None
    bayesian_metrics: dict[str, float | str | None] = {
        "status": "not_requested",
        "interval_coverage_80": None,
    }
    if fit_bayesian:
        bayesian_path = output_dir / "pymc_player_effects.json"
        bayesian_result = _fit_pymc_player_effects(frame, bayesian_path)
        bayesian_metrics = {"status": "complete", **bayesian_result}

    data_hash_rows = database.query("SELECT source_hash FROM games ORDER BY game_id")
    data_hash = _hash_values([row["source_hash"] for row in data_hash_rows])
    feature_schema_hash = _hash_values(list(FEATURE_COLUMNS))
    created = datetime.now(UTC)
    model_run_id = hashlib.sha256(
        (
            f"{cutoff.isoformat()}:{data_hash}:{feature_schema_hash}:{champion_name}"
        ).encode()
    ).hexdigest()[:24]
    metrics: dict[str, Any] = {
        "split": "rolling game-date 80/20 holdout",
        "train_games": len(train_games),
        "test_games": len(test_games),
        "train_possessions": len(train),
        "test_possessions": len(test),
        "baseline": baseline_metrics,
        "calibration_deciles": {
            "baseline": _calibration_deciles(test["points"], baseline_prediction),
            "xgboost": _calibration_deciles(test["points"], xgb_prediction),
        },
        "ablations": ablations,
        "xgboost": xgb_metrics,
        "xgboost_wins_gate": xgb_wins,
        "pymc": bayesian_metrics,
    }
    model_run = ModelRun(
        model_run_id=model_run_id,
        cutoff_at=cutoff,
        data_hash=data_hash,
        feature_schema_hash=feature_schema_hash,
        algorithm=champion_name,
        metrics={
            "baseline_mae": baseline_metrics["mae"],
            "baseline_rmse": baseline_metrics["rmse"],
            "baseline_calibration_error": baseline_metrics["calibration_error"],
            "baseline_game_rating_mae": baseline_metrics["game_rating_mae"],
            "xgboost_mae": xgb_metrics["mae"],
            "xgboost_rmse": xgb_metrics["rmse"],
            "xgboost_calibration_error": xgb_metrics["calibration_error"],
            "xgboost_game_rating_mae": xgb_metrics["game_rating_mae"],
            "xgboost_wins_gate": xgb_wins,
            "pymc_interval_coverage_80": bayesian_metrics.get("interval_coverage_80"),
        },
        status="complete",
        created_at=created,
    )
    p = database.placeholder
    database.execute(
        f"DELETE FROM model_runs WHERE model_run_id = {p}", (model_run_id,)
    )
    database.execute(
        f"INSERT INTO model_runs VALUES ({','.join([p] * 8)})",
        (
            model_run_id,
            cutoff.isoformat(),
            data_hash,
            feature_schema_hash,
            champion_name,
            json.dumps(metrics, sort_keys=True),
            "complete",
            created.isoformat(),
        ),
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True)
    )
    return TrainingResult(
        model_run=model_run,
        metrics=metrics,
        champion_path=champion_path,
        bayesian_path=bayesian_path,
    )
