from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, cast

from game_pulse.contracts import (
    CalibrationBin,
    MetricInterval,
    ModelCard,
    ModelMetrics,
    ModelResult,
    SplitSummary,
)
from game_pulse.data import (
    CONTEXT_COLUMNS,
    SEQUENCE_COLUMNS,
    ChronologicalSplit,
    feature_schema_hash,
    frame_hash,
)

RANDOM_SEED = 87


class ModelingDependencyError(RuntimeError):
    """Raised when the optional offline modeling stack is not installed."""


@dataclass(frozen=True)
class Predictor:
    name: str
    algorithm: str
    complexity_rank: int
    predict: Callable[[Any, Any], Any]


@dataclass(frozen=True)
class TrainingOutput:
    model_card: ModelCard
    champion: Predictor
    test_indices: Any
    champion_test_probabilities: Any


def _dependencies() -> tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    try:
        import keras
        import numpy as np
        from sklearn.dummy import DummyClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        from xgboost import XGBClassifier
    except ImportError as error:
        raise ModelingDependencyError(
            "training requires the 'modeling' optional dependency"
        ) from error
    return (
        keras,
        np,
        DummyClassifier,
        SimpleImputer,
        LogisticRegression,
        Pipeline,
        StandardScaler,
        XGBClassifier,
    )


def _indices(frame: Any, games: tuple[str, ...]) -> Any:
    import numpy as np

    return np.flatnonzero(frame["game_id"].astype(str).isin(games).to_numpy())


def _clip(probabilities: Any) -> Any:
    import numpy as np

    return np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)


def _platt_calibrator(probabilities: Any, actual: Any) -> Any:
    from sklearn.linear_model import LogisticRegression

    logits = _logits(probabilities).reshape(-1, 1)
    calibrator = LogisticRegression(C=1_000_000, max_iter=500, random_state=RANDOM_SEED)
    calibrator.fit(logits, actual)
    return calibrator


def _logits(probabilities: Any) -> Any:
    import numpy as np

    values = _clip(probabilities)
    return np.log(values / (1 - values))


def _apply_calibrator(calibrator: Any, probabilities: Any) -> Any:
    return calibrator.predict_proba(_logits(probabilities).reshape(-1, 1))[:, 1]


def _game_balanced_brier(frame: Any, actual: Any, predicted: Any) -> float:
    import numpy as np

    values = frame[["game_id"]].copy()
    values["squared_error"] = (
        np.asarray(actual, dtype=float) - np.asarray(predicted, dtype=float)
    ) ** 2
    return float(values.groupby("game_id")["squared_error"].mean().mean())


def _calibration_error(actual: Any, predicted: Any, bins: int = 10) -> float:
    import numpy as np

    actual_values = np.asarray(actual, dtype=float)
    predicted_values = np.asarray(predicted, dtype=float)
    order = np.argsort(predicted_values)
    errors: list[float] = []
    weights: list[int] = []
    for positions in np.array_split(order, bins):
        if not len(positions):
            continue
        errors.append(
            float(
                abs(
                    predicted_values[positions].mean() - actual_values[positions].mean()
                )
            )
        )
        weights.append(int(len(positions)))
    return float(np.average(errors, weights=weights))


def _bootstrap_interval(
    frame: Any, actual: Any, predicted: Any, *, iterations: int = 1_000
) -> MetricInterval:
    import numpy as np

    values = frame[["game_id"]].copy()
    values["squared_error"] = (
        np.asarray(actual, dtype=float) - np.asarray(predicted, dtype=float)
    ) ** 2
    per_game = values.groupby("game_id")["squared_error"].mean().to_numpy()
    generator = np.random.default_rng(RANDOM_SEED)
    estimates = np.empty(iterations, dtype=float)
    for iteration in range(iterations):
        sample = generator.choice(per_game, size=len(per_game), replace=True)
        estimates[iteration] = sample.mean()
    low, high = np.quantile(estimates, [0.025, 0.975])
    return MetricInterval(low=round(float(low), 6), high=round(float(high), 6))


def calculate_metrics(
    frame: Any,
    actual: Any,
    predicted: Any,
    *,
    include_interval: bool,
) -> ModelMetrics:
    import numpy as np
    from sklearn.metrics import log_loss

    probabilities = _clip(predicted)
    actual_values = np.asarray(actual, dtype=float)
    squared = (actual_values - probabilities) ** 2
    late_mask = frame["period"].to_numpy() >= 4
    late_brier = (
        float(squared[late_mask].mean()) if late_mask.any() else float(squared.mean())
    )
    return ModelMetrics(
        possession_brier=round(float(squared.mean()), 6),
        game_balanced_brier=round(
            _game_balanced_brier(frame, actual_values, probabilities), 6
        ),
        log_loss=round(float(log_loss(actual_values, probabilities)), 6),
        calibration_error=round(_calibration_error(actual_values, probabilities), 6),
        late_game_brier=round(late_brier, 6),
        brier_interval_95=(
            _bootstrap_interval(frame, actual_values, probabilities)
            if include_interval
            else None
        ),
    )


def calibration_bins(
    actual: Any, predicted: Any, bins: int = 10
) -> list[CalibrationBin]:
    import numpy as np

    actual_values = np.asarray(actual, dtype=float)
    predicted_values = _clip(predicted)
    order = np.argsort(predicted_values)
    result: list[CalibrationBin] = []
    for index, positions in enumerate(np.array_split(order, bins), start=1):
        if not len(positions):
            continue
        result.append(
            CalibrationBin(
                bin_number=index,
                observations=int(len(positions)),
                mean_prediction=round(float(predicted_values[positions].mean()), 6),
                observed_win_rate=round(float(actual_values[positions].mean()), 6),
            )
        )
    return result


def _prepare_context(frame: Any, indices: Any) -> Any:
    return frame.iloc[indices][list(CONTEXT_COLUMNS)].to_numpy(dtype=float)


def _fit_tabular_models(
    frame: Any,
    split: ChronologicalSplit,
) -> tuple[list[Predictor], dict[str, Any]]:
    (
        _,
        _,
        DummyClassifier,
        SimpleImputer,
        LogisticRegression,
        Pipeline,
        StandardScaler,
        XGBClassifier,
    ) = _dependencies()
    train_idx = _indices(frame, split.train_games)
    validation_idx = _indices(frame, split.validation_games)
    calibration_idx = _indices(frame, split.calibration_games)
    fit_idx = list(train_idx) + list(validation_idx)
    y = frame["home_win"].to_numpy(dtype=int)

    dummy = DummyClassifier(strategy="prior")
    dummy.fit(_prepare_context(frame, train_idx), y[train_idx])

    logistic = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=0.5,
                    max_iter=1_000,
                    random_state=RANDOM_SEED,
                ),
            ),
        ]
    )
    logistic.fit(_prepare_context(frame, fit_idx), y[fit_idx])

    imputer = SimpleImputer(strategy="median")
    x_train = imputer.fit_transform(_prepare_context(frame, train_idx))
    x_validation = imputer.transform(_prepare_context(frame, validation_idx))
    xgb = XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        n_estimators=800,
        max_depth=3,
        learning_rate=0.035,
        min_child_weight=8,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=4.0,
        early_stopping_rounds=30,
        random_state=RANDOM_SEED,
        n_jobs=4,
    )
    xgb.fit(
        x_train,
        y[train_idx],
        eval_set=[(x_validation, y[validation_idx])],
        verbose=False,
    )

    raw_predictors: list[tuple[str, str, int, Callable[[Any], Any]]] = [
        (
            "prior",
            "Training-set home-win prior",
            0,
            lambda context: dummy.predict_proba(context)[:, 1],
        ),
        (
            "logistic",
            "Scikit-learn regularized logistic regression",
            1,
            lambda context: logistic.predict_proba(context)[:, 1],
        ),
        (
            "xgboost",
            "XGBoost bounded-depth binary classifier",
            2,
            lambda context: xgb.predict_proba(imputer.transform(context))[:, 1],
        ),
    ]
    predictors: list[Predictor] = []
    raw_calibration: dict[str, Any] = {}
    calibration_context = _prepare_context(frame, calibration_idx)
    for name, algorithm, rank, raw_predict in raw_predictors:
        raw_probability = raw_predict(calibration_context)
        calibrator = _platt_calibrator(raw_probability, y[calibration_idx])
        raw_calibration[name] = calibrator

        def calibrated_predict(
            context: Any,
            sequence: Any,
            *,
            _raw: Callable[[Any], Any] = raw_predict,
            _calibrator: Any = calibrator,
        ) -> Any:
            del sequence
            return _apply_calibrator(_calibrator, _raw(context))

        predictors.append(
            Predictor(
                name=name,
                algorithm=algorithm,
                complexity_rank=rank,
                predict=calibrated_predict,
            )
        )
    return predictors, raw_calibration


def _fit_keras_predictor(
    frame: Any,
    sequences: Any,
    split: ChronologicalSplit,
) -> Predictor:
    keras, np, _, SimpleImputer, _, _, StandardScaler, _ = _dependencies()
    keras.utils.set_random_seed(RANDOM_SEED)
    try:
        keras.config.enable_op_determinism()
    except AttributeError:
        pass
    train_idx = _indices(frame, split.train_games)
    validation_idx = _indices(frame, split.validation_games)
    calibration_idx = _indices(frame, split.calibration_games)
    y = frame["home_win"].to_numpy(dtype=np.float32)

    context_imputer = SimpleImputer(strategy="median")
    context_scaler = StandardScaler()
    train_context = context_scaler.fit_transform(
        context_imputer.fit_transform(_prepare_context(frame, train_idx))
    ).astype("float32")
    validation_context = context_scaler.transform(
        context_imputer.transform(_prepare_context(frame, validation_idx))
    ).astype("float32")

    sequence_values = np.asarray(sequences, dtype=np.float32).copy()
    valid_train = sequence_values[train_idx, :, 0] == 1
    train_numeric = sequence_values[train_idx, :, 1:][valid_train]
    sequence_mean = train_numeric.mean(axis=0)
    sequence_std = train_numeric.std(axis=0)
    sequence_std = np.where(sequence_std < 1e-6, 1.0, sequence_std)

    def transform_sequences(values: Any) -> Any:
        transformed = np.asarray(values, dtype=np.float32).copy()
        valid = transformed[:, :, 0:1]
        transformed[:, :, 1:] = (
            (transformed[:, :, 1:] - sequence_mean) / sequence_std
        ) * valid
        return transformed

    train_sequence = transform_sequences(sequence_values[train_idx])
    validation_sequence = transform_sequences(sequence_values[validation_idx])

    sequence_input = keras.Input(
        shape=(sequences.shape[1], sequences.shape[2]), name="possession_history"
    )
    context_input = keras.Input(shape=(len(CONTEXT_COLUMNS),), name="current_state")
    history = keras.layers.Masking(mask_value=0.0)(sequence_input)
    history = keras.layers.GRU(16)(history)
    combined = keras.layers.Concatenate()([history, context_input])
    combined = keras.layers.Dense(16, activation="relu")(combined)
    combined = keras.layers.Dropout(0.10, seed=RANDOM_SEED)(combined)
    output = keras.layers.Dense(1, activation="sigmoid")(combined)
    model = keras.Model(inputs=[sequence_input, context_input], outputs=output)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss="binary_crossentropy",
        metrics=[keras.metrics.MeanSquaredError(name="brier")],
    )
    model.fit(
        [train_sequence, train_context],
        y[train_idx],
        validation_data=(
            [validation_sequence, validation_context],
            y[validation_idx],
        ),
        epochs=50,
        batch_size=512,
        callbacks=[
            keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=5,
                restore_best_weights=True,
            )
        ],
        verbose=0,
    )

    def raw_predict(context: Any, sequence: Any) -> Any:
        transformed_context = context_scaler.transform(
            context_imputer.transform(context)
        ).astype("float32")
        transformed_sequence = transform_sequences(sequence)
        return model.predict(
            [transformed_sequence, transformed_context], verbose=0
        ).reshape(-1)

    calibration_probability = raw_predict(
        _prepare_context(frame, calibration_idx), sequences[calibration_idx]
    )
    calibrator = _platt_calibrator(calibration_probability, y[calibration_idx])

    def calibrated_predict(context: Any, sequence: Any) -> Any:
        return _apply_calibrator(calibrator, raw_predict(context, sequence))

    return Predictor(
        name="keras_gru",
        algorithm="Keras masked 10-possession GRU with current-state context",
        complexity_rank=3,
        predict=calibrated_predict,
    )


def _split_summary(frame: Any, split: ChronologicalSplit) -> SplitSummary:
    def end(games: tuple[str, ...]) -> datetime:
        value = frame[frame["game_id"].astype(str).isin(games)]["game_date"].max()
        return cast(datetime, value.to_pydatetime())

    test_start_value = frame[frame["game_id"].astype(str).isin(split.test_games)][
        "game_date"
    ].min()
    return SplitSummary(
        train_games=len(split.train_games),
        validation_games=len(split.validation_games),
        calibration_games=len(split.calibration_games),
        selection_games=len(split.selection_games),
        test_games=len(split.test_games),
        train_end=end(split.train_games),
        validation_end=end(split.validation_games),
        calibration_end=end(split.calibration_games),
        selection_end=end(split.selection_games),
        test_start=test_start_value.to_pydatetime(),
    )


def train_model_suite(
    frame: Any,
    sequences: Any,
    split: ChronologicalSplit,
    *,
    cutoff: datetime,
) -> TrainingOutput:
    import numpy as np

    predictors, _ = _fit_tabular_models(frame, split)
    predictors.append(_fit_keras_predictor(frame, sequences, split))
    y = frame["home_win"].to_numpy(dtype=int)
    selection_idx = _indices(frame, split.selection_games)
    test_idx = _indices(frame, split.test_games)
    selection_frame = frame.iloc[selection_idx]
    test_frame = frame.iloc[test_idx]
    selection_context = _prepare_context(frame, selection_idx)
    test_context = _prepare_context(frame, test_idx)

    selection_predictions: dict[str, Any] = {}
    test_predictions: dict[str, Any] = {}
    selection_metrics: dict[str, ModelMetrics] = {}
    test_metrics: dict[str, ModelMetrics] = {}
    for predictor in predictors:
        selection_probability = predictor.predict(
            selection_context, sequences[selection_idx]
        )
        test_probability = predictor.predict(test_context, sequences[test_idx])
        selection_predictions[predictor.name] = selection_probability
        test_predictions[predictor.name] = test_probability
        selection_metrics[predictor.name] = calculate_metrics(
            selection_frame,
            y[selection_idx],
            selection_probability,
            include_interval=False,
        )
        test_metrics[predictor.name] = calculate_metrics(
            test_frame,
            y[test_idx],
            test_probability,
            include_interval=True,
        )

    baseline = selection_metrics["logistic"]
    candidates = [
        predictor
        for predictor in predictors
        if predictor.name in {"xgboost", "keras_gru"}
        and selection_metrics[predictor.name].game_balanced_brier
        <= baseline.game_balanced_brier - 0.002
        and selection_metrics[predictor.name].calibration_error
        <= baseline.calibration_error + 0.01
    ]
    champion = next(
        predictor for predictor in predictors if predictor.name == "logistic"
    )
    if candidates:
        ordered = sorted(
            candidates,
            key=lambda predictor: (
                selection_metrics[predictor.name].game_balanced_brier,
                predictor.complexity_rank,
            ),
        )
        champion = ordered[0]
        for contender in ordered[1:]:
            difference = abs(
                selection_metrics[contender.name].game_balanced_brier
                - selection_metrics[champion.name].game_balanced_brier
            )
            if (
                difference <= 0.0005
                and contender.complexity_rank < champion.complexity_rank
            ):
                champion = contender

    results: list[ModelResult] = []
    for predictor in predictors:
        if predictor.name == "prior":
            note = "Reference model only; not eligible for promotion."
        elif predictor.name == champion.name:
            note = "Selected on the pre-2026 selection window; 2026 test results were not used."
        elif predictor.name in {"xgboost", "keras_gru"}:
            note = (
                "Did not clear the 0.002 Brier improvement and calibration guardrail, "
                "or lost the predeclared simplicity tie-break."
            )
        else:
            note = "Default interpretable baseline; replaced only by a qualifying challenger."
        results.append(
            ModelResult(
                name=predictor.name,
                algorithm=predictor.algorithm,
                complexity_rank=predictor.complexity_rank,
                promoted=predictor.name == champion.name,
                promotion_note=note,
                selection=selection_metrics[predictor.name],
                test=test_metrics[predictor.name],
            )
        )

    data_digest = frame_hash(frame)
    schema_digest = feature_schema_hash()
    run_payload = f"{data_digest}:{schema_digest}:{champion.name}:{cutoff.isoformat()}:{RANDOM_SEED}"
    import hashlib

    model_run_id = hashlib.sha256(run_payload.encode()).hexdigest()[:24]
    card = ModelCard(
        model_run_id=model_run_id,
        champion=champion.name,
        built_at=datetime.now(UTC),
        cutoff_at=cutoff,
        data_hash=data_digest,
        feature_schema_hash=schema_digest,
        random_seed=RANDOM_SEED,
        split=_split_summary(frame, split),
        models=results,
        calibration=calibration_bins(y[test_idx], test_predictions[champion.name]),
        promotion_rule=(
            "A challenger must improve game-balanced selection Brier by at least "
            "0.002 without worsening 10-bin calibration error by more than 0.01; "
            "differences within 0.0005 favor the simpler model."
        ),
        features=list(CONTEXT_COLUMNS),
        sequence_features=list(SEQUENCE_COLUMNS),
        caveats=[
            "Every row within a game shares the final outcome; games, never possessions, define data splits.",
            "The test set is the 2026 season and does not influence model selection.",
            "Public play-by-play does not expose timeouts, tactical intent, health, or tracking context.",
            "Win-probability change describes a possession sequence; it is not causal player credit.",
        ],
    )
    champion_test = np.asarray(test_predictions[champion.name], dtype=float)
    return TrainingOutput(
        model_card=card,
        champion=champion,
        test_indices=test_idx,
        champion_test_probabilities=champion_test,
    )
