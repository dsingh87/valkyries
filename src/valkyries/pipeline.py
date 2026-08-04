from __future__ import annotations

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from valkyries.contracts import GameBundle
from valkyries.database import Database
from valkyries.ingestion.espn import SUMMARY_ENDPOINT, EspnClient
from valkyries.transform import (
    build_possessions,
    reconstruct_lineups,
    validate_player_minutes,
)


@dataclass(frozen=True)
class IngestionSummary:
    run_id: str
    games_discovered: int
    games_published: int
    games_quarantined: int
    quarantined: dict[str, str]


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def ingest_seasons(
    database: Database,
    *,
    client: EspnClient,
    start_season: int,
    cutoff: datetime,
    raw_data_dir: Path,
    workers: int = 8,
    max_games: int | None = None,
) -> IngestionSummary:
    database.initialize()
    run_id = uuid.uuid4().hex
    started = datetime.now(UTC)
    p = database.placeholder
    database.execute(
        f"INSERT INTO pipeline_runs VALUES ({','.join([p] * 10)})",
        (
            run_id,
            "ingest",
            started.isoformat(),
            None,
            cutoff.isoformat(),
            "running",
            0,
            0,
            0,
            None,
        ),
    )
    game_ids = list(client.completed_game_ids(start_season=start_season, cutoff=cutoff))
    if max_games is not None:
        game_ids = game_ids[-max_games:]
    published = 0
    quarantined: dict[str, str] = {}

    def fetch(game_id: str) -> tuple[str, dict[str, Any]]:
        payload = dict(client.game_summary(game_id))
        return game_id, payload

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(fetch, game_id): game_id for game_id in game_ids}
        for future in as_completed(futures):
            game_id = futures[future]
            retrieved = datetime.now(UTC)
            payload: dict[str, Any] | None = None
            source_url = f"{SUMMARY_ENDPOINT}?event={game_id}"
            try:
                _, payload = future.result()
                bundle = GameBundle.from_espn(
                    payload,
                    source_url=source_url,
                    retrieved_at=retrieved,
                )
                raw_path = raw_data_dir / str(bundle.season) / f"{game_id}.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(json.dumps(payload, sort_keys=True))
                stints, event_lineups = reconstruct_lineups(bundle)
                validate_player_minutes(bundle, stints, tolerance_seconds=150)
                possessions = build_possessions(bundle, event_lineups)
                database.replace_game(bundle, stints, possessions)
                database.record_raw_payload(
                    game_id=game_id,
                    source_url=source_url,
                    retrieved_at=retrieved,
                    source_hash=bundle.source_hash,
                    local_path=raw_path,
                    status="published",
                )
                published += 1
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                quarantined[game_id] = message
                raw_path = raw_data_dir / "quarantine" / f"{game_id}.json"
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                if payload is not None:
                    raw_path.write_text(json.dumps(payload, sort_keys=True))
                database.record_raw_payload(
                    game_id=game_id,
                    source_url=source_url,
                    retrieved_at=retrieved,
                    source_hash=_payload_hash(payload or {}),
                    local_path=raw_path,
                    status="quarantined",
                    error=message,
                )

    completed = datetime.now(UTC)
    status = "complete" if published else "failed"
    database.execute(
        f"""
        UPDATE pipeline_runs
        SET completed_at = {p}, status = {p}, games_discovered = {p},
            games_published = {p}, games_quarantined = {p}, detail = {p}
        WHERE run_id = {p}
        """,
        (
            completed.isoformat(),
            status,
            len(game_ids),
            published,
            len(quarantined),
            json.dumps(quarantined, sort_keys=True),
            run_id,
        ),
    )
    return IngestionSummary(
        run_id=run_id,
        games_discovered=len(game_ids),
        games_published=published,
        games_quarantined=len(quarantined),
        quarantined=quarantined,
    )


def ingest_game(
    database: Database,
    *,
    client: EspnClient,
    game_id: str,
    raw_data_dir: Path,
) -> GameBundle:
    database.initialize()
    payload = dict(client.game_summary(game_id))
    bundle = GameBundle.from_espn(
        payload,
        source_url=f"{SUMMARY_ENDPOINT}?event={game_id}",
    )
    raw_path = raw_data_dir / str(bundle.season) / f"{game_id}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(payload, sort_keys=True))
    stints, event_lineups = reconstruct_lineups(bundle)
    validate_player_minutes(bundle, stints, tolerance_seconds=150)
    possessions = build_possessions(bundle, event_lineups)
    database.replace_game(bundle, stints, possessions)
    database.record_raw_payload(
        game_id=game_id,
        source_url=bundle.source_url,
        retrieved_at=bundle.retrieved_at,
        source_hash=bundle.source_hash,
        local_path=raw_path,
        status="published",
    )
    return bundle
