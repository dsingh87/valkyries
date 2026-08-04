from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_CUTOFF = datetime(2026, 8, 3, 8, 0, tzinfo=UTC)
DEFAULT_MATCHUP_GAME_ID = "401857114"
GOLDEN_STATE_ABBREVIATION = "GS"
TORONTO_ABBREVIATION = "TOR"


@dataclass(frozen=True)
class Settings:
    database_url: str
    artifact_path: Path
    raw_data_dir: Path

    @classmethod
    def from_environment(cls) -> Settings:
        root = Path(__file__).resolve().parents[2]
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                f"sqlite:///{root / 'data' / 'valkyries.sqlite3'}",
            ),
            artifact_path=Path(
                os.getenv(
                    "VALKYRIES_ARTIFACT_PATH",
                    root / "artifacts" / "aug4_toronto.json",
                )
            ),
            raw_data_dir=Path(
                os.getenv("VALKYRIES_RAW_DATA_DIR", root / "data" / "raw")
            ),
        )


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)
