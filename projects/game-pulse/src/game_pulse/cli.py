from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from game_pulse.artifact import (
    DEFAULT_ARTIFACT_PATH,
    DEFAULT_CUTOFF,
    build_artifact,
    load_artifact,
)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("cutoff must include a UTC offset")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="game-pulse")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="train and freeze Game Pulse")
    build.add_argument("--database-url", required=True)
    build.add_argument("--cutoff", type=_parse_datetime, default=DEFAULT_CUTOFF)
    build.add_argument("--team", default="GS")
    build.add_argument("--season", type=int, default=2026)
    build.add_argument("--output", type=Path, default=DEFAULT_ARTIFACT_PATH)
    validate = subparsers.add_parser("validate", help="validate a frozen artifact")
    validate.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "build":
        artifact = build_artifact(
            args.database_url,
            cutoff=args.cutoff,
            target_team=args.team,
            target_season=args.season,
            output_path=args.output,
        )
        print(
            f"Built {len(artifact.games)} games with "
            f"{artifact.model_card.champion} champion "
            f"({artifact.model_card.model_run_id})."
        )
        return 0
    if args.command == "validate":
        artifact = load_artifact(args.artifact)
        print(
            f"Valid schema {artifact.schema_version}: {len(artifact.games)} games, "
            f"champion {artifact.model_card.champion}."
        )
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
