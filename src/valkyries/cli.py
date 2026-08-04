from __future__ import annotations

import argparse
import json
from pathlib import Path

from valkyries.artifacts import freeze_brief, latest_model_run, load_brief
from valkyries.audit import audit_game
from valkyries.config import (
    DEFAULT_CUTOFF,
    DEFAULT_MATCHUP_GAME_ID,
    Settings,
    parse_utc,
)
from valkyries.database import Database
from valkyries.ingestion.espn import EspnClient
from valkyries.modeling import train_models
from valkyries.pipeline import ingest_seasons


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_environment()
    return Settings(
        database_url=args.database_url or settings.database_url,
        artifact_path=Path(args.artifact_path or settings.artifact_path),
        raw_data_dir=Path(args.raw_data_dir or settings.raw_data_dir),
    )


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database-url")
    parser.add_argument("--artifact-path")
    parser.add_argument("--raw-data-dir")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="valkyries")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="ingest completed WNBA games")
    _common(ingest)
    ingest.add_argument("--start-season", type=int, default=2024)
    ingest.add_argument("--cutoff", default=DEFAULT_CUTOFF.isoformat())
    ingest.add_argument("--workers", type=int, default=8)
    ingest.add_argument("--max-games", type=int)

    build = subparsers.add_parser("build", help="build SQL analytical marts")
    _common(build)

    train = subparsers.add_parser("train", help="train and benchmark models")
    _common(train)
    train.add_argument("--cutoff", default=DEFAULT_CUTOFF.isoformat())
    train.add_argument("--output-dir", default="models")
    train.add_argument("--skip-pymc", action="store_true")

    recommend = subparsers.add_parser(
        "recommend", help="freeze the Toronto pregame brief"
    )
    _common(recommend)
    recommend.add_argument("--game-id", default=DEFAULT_MATCHUP_GAME_ID)
    recommend.add_argument("--defense-tolerance", type=float, default=2.0)
    recommend.add_argument("--scheduled-at", default="2026-08-05T02:00:00Z")

    audit = subparsers.add_parser("audit", help="audit a completed target game")
    _common(audit)
    audit.add_argument("--game-id", default=DEFAULT_MATCHUP_GAME_ID)
    audit.add_argument("--output", default="artifacts/aug4_toronto_audit.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = _settings(args)
    database = Database(settings.database_url)
    if args.command == "ingest":
        ingestion = ingest_seasons(
            database,
            client=EspnClient(),
            start_season=args.start_season,
            cutoff=parse_utc(args.cutoff),
            raw_data_dir=settings.raw_data_dir,
            workers=args.workers,
            max_games=args.max_games,
        )
        print(json.dumps(ingestion.__dict__, indent=2, sort_keys=True))
        return 0 if ingestion.games_published else 1
    if args.command == "build":
        database.initialize()
        database.build_marts()
        print("Built team_game_features, lineup_features, and pregame_matchups.")
        return 0
    if args.command == "train":
        training = train_models(
            database,
            cutoff=parse_utc(args.cutoff),
            output_dir=Path(args.output_dir),
            fit_bayesian=not args.skip_pymc,
        )
        print(training.model_run.model_dump_json(indent=2))
        return 0
    if args.command == "recommend":
        brief = freeze_brief(
            database,
            model_run=latest_model_run(database),
            target_game_id=args.game_id,
            scheduled_at=parse_utc(args.scheduled_at),
            output_path=settings.artifact_path,
            defense_tolerance=args.defense_tolerance,
        )
        print(brief.model_dump_json(indent=2))
        return 0
    if args.command == "audit":
        brief = load_brief(settings.artifact_path)
        if args.game_id != brief.target_game_id:
            raise ValueError(
                f"game {args.game_id} does not match frozen brief "
                f"{brief.target_game_id}"
            )
        audit_result = audit_game(
            database,
            brief=brief,
            output_path=Path(args.output),
        )
        print(json.dumps(audit_result, indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
