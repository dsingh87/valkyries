from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from game_pulse.contracts import (
    GameDetail,
    GamePulseArtifact,
    SourceRecord,
    TimelinePoint,
    TurningPoint,
)
from game_pulse.data import (
    chronological_split,
    display_clock,
    load_feature_frame,
    make_sequences,
    period_label,
    validate_frame,
)
from game_pulse.modeling import TrainingOutput, train_model_suite

DEFAULT_GAME_ID = "401857098"
DEFAULT_CUTOFF = datetime(2026, 8, 3, 8, 0, tzinfo=UTC)
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_ARTIFACT_PATH = PACKAGE_DIR / "published" / "game_pulse.json"


def _round_probability(value: float) -> float:
    return round(min(max(float(value), 0.0), 1.0), 6)


def _target_game(
    game_frame: Any,
    home_probabilities: Any,
    *,
    target_team: str,
) -> GameDetail:
    rows = game_frame.reset_index(drop=True)
    probabilities = [float(value) for value in home_probabilities]
    target_is_home = str(rows.iloc[0]["home_team_abbreviation"]) == target_team
    home_won = int(rows.iloc[0]["home_score"]) > int(rows.iloc[0]["away_score"])
    target_won = home_won if target_is_home else not home_won
    final_probability = 1.0 if target_won else 0.0
    target_probabilities = [
        probability if target_is_home else 1.0 - probability
        for probability in probabilities
    ]
    timeline: list[TimelinePoint] = []
    for index, row in rows.iterrows():
        current_probability = target_probabilities[index]
        next_probability = (
            target_probabilities[index + 1]
            if index + 1 < len(target_probabilities)
            else final_probability
        )
        change = next_probability - current_probability
        margin = int(row["home_margin"])
        target_margin = margin if target_is_home else -margin
        target_possession = bool(row["is_home_offense"])
        if not target_is_home:
            target_possession = not target_possession
        description = str(row["description"] or row["terminal_action"]).strip()
        timeline.append(
            TimelinePoint(
                possession_number=int(row["possession_number"]),
                period=int(row["period"]),
                period_label=period_label(int(row["period"])),
                clock=display_clock(
                    int(row["period"]), int(row["start_elapsed_seconds"])
                ),
                elapsed_seconds=int(row["start_elapsed_seconds"]),
                valkyries_margin=target_margin,
                valkyries_possession=target_possession,
                win_probability=_round_probability(current_probability),
                next_win_probability=_round_probability(next_probability),
                win_probability_added=round(float(change), 6),
                leverage=round(abs(float(change)), 6),
                description=description,
            )
        )
    last = rows.iloc[-1]
    final_margin = (
        int(last["home_score"]) - int(last["away_score"])
        if target_is_home
        else int(last["away_score"]) - int(last["home_score"])
    )
    timeline.append(
        TimelinePoint(
            possession_number=int(last["possession_number"]) + 1,
            period=int(last["period"]),
            period_label=period_label(int(last["period"])),
            clock="0:00",
            elapsed_seconds=int(last["end_elapsed_seconds"]),
            valkyries_margin=final_margin,
            valkyries_possession=False,
            win_probability=final_probability,
            next_win_probability=final_probability,
            win_probability_added=0.0,
            leverage=0.0,
            description="Final horn",
            synthetic=True,
        )
    )
    ranked = sorted(
        (point for point in timeline if not point.synthetic),
        key=lambda point: (-point.leverage, point.possession_number),
    )[:5]
    turning_points = [
        TurningPoint(
            rank=rank,
            possession_number=point.possession_number,
            period_label=point.period_label,
            clock=point.clock,
            description=point.description,
            win_probability_before=point.win_probability,
            win_probability_after=point.next_win_probability,
            win_probability_added=point.win_probability_added,
        )
        for rank, point in enumerate(ranked, start=1)
    ]
    nonterminal = [point for point in timeline if not point.synthetic]
    home_abbreviation = str(last["home_team_abbreviation"])
    away_abbreviation = str(last["away_team_abbreviation"])
    opponent = away_abbreviation if target_is_home else home_abbreviation
    target_score = int(last["home_score"] if target_is_home else last["away_score"])
    opponent_score = int(last["away_score"] if target_is_home else last["home_score"])
    return GameDetail(
        game_id=str(last["game_id"]),
        game_date=last["game_date"].to_pydatetime(),
        matchup=f"{away_abbreviation} at {home_abbreviation}",
        opponent=opponent,
        location="Home" if target_is_home else "Away",
        valkyries_score=target_score,
        opponent_score=opponent_score,
        result="W" if target_won else "L",
        opening_win_probability=nonterminal[0].win_probability,
        minimum_win_probability=min(point.win_probability for point in nonterminal),
        maximum_win_probability=max(point.win_probability for point in nonterminal),
        largest_swing=max(point.leverage for point in nonterminal),
        timeline=timeline,
        turning_points=turning_points,
    )


def build_artifact(
    database_url: str,
    *,
    cutoff: datetime = DEFAULT_CUTOFF,
    target_team: str = "GS",
    target_season: int = 2026,
    output_path: Path = DEFAULT_ARTIFACT_PATH,
) -> GamePulseArtifact:
    frame = load_feature_frame(database_url, cutoff)
    validate_frame(frame)
    sequences = make_sequences(frame)
    split = chronological_split(frame, test_season=target_season)
    training = train_model_suite(frame, sequences, split, cutoff=cutoff)
    artifact = assemble_artifact(
        frame,
        sequences,
        training,
        cutoff=cutoff,
        target_team=target_team,
        target_season=target_season,
    )
    freeze_artifact(artifact, output_path)
    return artifact


def assemble_artifact(
    frame: Any,
    sequences: Any,
    training: TrainingOutput,
    *,
    cutoff: datetime,
    target_team: str,
    target_season: int,
) -> GamePulseArtifact:
    del sequences
    test_frame = frame.iloc[training.test_indices].copy().reset_index(drop=True)
    test_frame["home_win_probability"] = training.champion_test_probabilities
    target = test_frame[
        (test_frame["season"] == target_season)
        & (
            (test_frame["home_team_abbreviation"] == target_team)
            | (test_frame["away_team_abbreviation"] == target_team)
        )
    ]
    games = [
        _target_game(
            group,
            group["home_win_probability"].to_numpy(),
            target_team=target_team,
        )
        for _, group in target.groupby("game_id", sort=False)
    ]
    games.sort(key=lambda game: (game.game_date, game.game_id), reverse=True)
    game_ids = {game.game_id for game in games}
    if DEFAULT_GAME_ID not in game_ids:
        raise ValueError(f"default showcase game {DEFAULT_GAME_ID} is unavailable")
    return GamePulseArtifact(
        default_game_id=DEFAULT_GAME_ID,
        target_team=target_team,
        target_season=target_season,
        data_cutoff_at=cutoff,
        frozen_at=datetime.now(UTC),
        model_card=training.model_card,
        games=games,
        sources=[
            SourceRecord(
                name="Validated WNBA play-by-play",
                detail=(
                    "ESPN event and score payloads normalized by the parent "
                    "Valkyries analytics pipeline."
                ),
            ),
            SourceRecord(
                name="Pregame matchup mart",
                detail=(
                    "Rolling team offense, defense, and rest features calculated "
                    "strictly from earlier games."
                ),
            ),
        ],
        caveats=[
            "Probabilities are historical, out-of-time estimates for completed games—not live betting forecasts.",
            "The model observes public possession state but not timeouts, tactical intent, injuries, or tracking data.",
            "Possession swings are descriptive and should not be interpreted as causal player value.",
            "The terminal game state is set to the observed 0% or 100% outcome and is excluded from turning-point ranking.",
        ],
    )


def freeze_artifact(artifact: GamePulseArtifact, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        artifact.model_dump(mode="json"),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )
    output_path.write_text(payload + "\n")
    digest = hashlib.sha256((payload + "\n").encode()).hexdigest()
    output_path.with_suffix(output_path.suffix + ".sha256").write_text(digest + "\n")
    return digest


def load_artifact(path: Path = DEFAULT_ARTIFACT_PATH) -> GamePulseArtifact:
    if not path.exists():
        raise FileNotFoundError(f"Game Pulse artifact not found: {path}")
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    if not checksum_path.exists():
        raise ValueError(f"Game Pulse checksum not found: {checksum_path}")
    payload = path.read_bytes()
    expected = checksum_path.read_text().strip()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError("Game Pulse artifact checksum does not match")
    return GamePulseArtifact.model_validate_json(payload)
