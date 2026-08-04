from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from valkyries.contracts import GameBundle
from valkyries.transform import LineupStint, Possession, lineup_key


class CursorLike(Protocol):
    def execute(self, query: str, params: Sequence[Any] = ()) -> Any: ...

    def executemany(self, query: str, params: Iterable[Sequence[Any]]) -> Any: ...

    def fetchall(self) -> Sequence[Any]: ...


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.is_postgres = url.startswith(("postgres://", "postgresql://"))

    @contextmanager
    def connect(self) -> Iterator[Any]:
        connection: Any
        if self.is_postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as error:
                raise RuntimeError(
                    "Postgres requires the 'database' optional dependency"
                ) from error
            connection = psycopg.connect(self.url, row_factory=dict_row)
        else:
            prefix = "sqlite:///"
            if not self.url.startswith(prefix):
                raise ValueError("database URL must be sqlite:/// or postgresql://")
            path = Path(self.url.removeprefix(prefix))
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @property
    def placeholder(self) -> str:
        return "%s" if self.is_postgres else "?"

    def initialize(self) -> None:
        sql_dir = Path(__file__).with_name("sql")
        self.execute_script((sql_dir / "schema.sql").read_text())
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        if self.is_postgres:
            columns = {
                row["column_name"]
                for row in self.query(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'possessions'
                    """
                )
            }
        else:
            columns = {
                row["name"] for row in self.query("PRAGMA table_info(possessions)")
            }
        if "score_correction" not in columns:
            self.execute(
                "ALTER TABLE possessions ADD COLUMN "
                "score_correction INTEGER NOT NULL DEFAULT 0"
            )

    def build_marts(self) -> None:
        sql_dir = Path(__file__).with_name("sql")
        script = (sql_dir / "marts.sql").read_text()
        if self.is_postgres:
            script = script.replace(
                "julianday(game_date) - julianday(\n            LAG(game_date) OVER (PARTITION BY team_id ORDER BY game_date)\n        )",
                "EXTRACT(EPOCH FROM (CAST(game_date AS TIMESTAMP) - CAST(\n            LAG(game_date) OVER (PARTITION BY team_id ORDER BY game_date) AS TIMESTAMP\n        ))) / 86400.0",
            )
        self.execute_script(script)

    def execute_script(self, script: str) -> None:
        statements = [statement.strip() for statement in script.split(";")]
        with self.connect() as connection:
            if not self.is_postgres:
                connection.executescript(script)
                return
            cursor = connection.cursor()
            for statement in statements:
                if statement:
                    cursor.execute(statement)

    def query(
        self,
        query: str,
        params: Sequence[Any] = (),
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            cursor = connection.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def execute(self, query: str, params: Sequence[Any] = ()) -> None:
        with self.connect() as connection:
            connection.execute(query, params)

    def executemany(
        self,
        query: str,
        params: Iterable[Sequence[Any]],
    ) -> None:
        with self.connect() as connection:
            connection.executemany(query, params)

    def replace_game(
        self,
        bundle: GameBundle,
        stints: list[LineupStint],
        possessions: list[Possession],
    ) -> None:
        p = self.placeholder
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            cursor = connection.cursor()
            for table in ("possessions", "lineup_stints", "events", "athletes"):
                cursor.execute(
                    f"DELETE FROM {table} WHERE game_id = {p}", (bundle.game_id,)
                )
            cursor.execute(f"DELETE FROM games WHERE game_id = {p}", (bundle.game_id,))
            cursor.execute(
                f"INSERT INTO games VALUES ({','.join([p] * 11)})",
                (
                    bundle.game_id,
                    bundle.season,
                    bundle.game_date.isoformat(),
                    bundle.home_team.team_id,
                    bundle.home_team.abbreviation,
                    bundle.home_team.score,
                    bundle.away_team.team_id,
                    bundle.away_team.abbreviation,
                    bundle.away_team.score,
                    bundle.source_hash,
                    now,
                ),
            )
            cursor.executemany(
                f"INSERT INTO athletes VALUES ({','.join([p] * 7)})",
                [
                    (
                        bundle.game_id,
                        athlete.athlete_id,
                        athlete.display_name,
                        athlete.team_id,
                        athlete.position,
                        int(athlete.starter),
                        athlete.minutes,
                    )
                    for athlete in bundle.athletes
                ],
            )
            cursor.executemany(
                f"INSERT INTO events VALUES ({','.join([p] * 16)})",
                [
                    (
                        bundle.game_id,
                        event.event_id,
                        event.sequence_number,
                        event.source_sequence_number,
                        event.period,
                        event.clock,
                        event.elapsed_seconds,
                        event.action_type,
                        event.text,
                        event.team_id,
                        json.dumps(event.participant_ids),
                        event.away_score,
                        event.home_score,
                        int(event.scoring_play),
                        int(event.shooting_play),
                        event.score_value,
                    )
                    for event in bundle.events
                ],
            )
            cursor.executemany(
                f"INSERT INTO lineup_stints VALUES ({','.join([p] * 11)})",
                [
                    (
                        stint.stint_id,
                        stint.game_id,
                        stint.start_event_id,
                        stint.end_event_id,
                        stint.start_elapsed_seconds,
                        stint.end_elapsed_seconds,
                        stint.duration_seconds,
                        stint.home_team_id,
                        stint.away_team_id,
                        lineup_key(stint.home_lineup),
                        lineup_key(stint.away_lineup),
                    )
                    for stint in stints
                ],
            )
            cursor.executemany(
                """
                INSERT INTO possessions (
                    possession_id, game_id, possession_number, period,
                    offense_team_id, defense_team_id, offense_lineup,
                    defense_lineup, start_elapsed_seconds, end_elapsed_seconds,
                    duration_seconds, points, score_correction, margin_before,
                    is_home_offense, is_half_court_5, is_half_court_7,
                    is_half_court_9, terminal_action, terminal_event_id
                ) VALUES (
                """
                + ",".join([p] * 20)
                + ")",
                [
                    (
                        possession.possession_id,
                        possession.game_id,
                        possession.possession_number,
                        possession.period,
                        possession.offense_team_id,
                        possession.defense_team_id,
                        lineup_key(possession.offense_lineup),
                        lineup_key(possession.defense_lineup),
                        possession.start_elapsed_seconds,
                        possession.end_elapsed_seconds,
                        possession.duration_seconds,
                        possession.points,
                        possession.score_correction,
                        possession.margin_before,
                        int(possession.is_home_offense),
                        int(possession.is_half_court_5),
                        int(possession.is_half_court_7),
                        int(possession.is_half_court_9),
                        possession.terminal_action,
                        possession.terminal_event_id,
                    )
                    for possession in possessions
                ],
            )

    def record_raw_payload(
        self,
        *,
        game_id: str,
        source_url: str,
        retrieved_at: datetime,
        source_hash: str,
        local_path: Path,
        status: str,
        error: str | None = None,
    ) -> None:
        p = self.placeholder
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"DELETE FROM raw_payloads WHERE game_id = {p}", (game_id,))
            cursor.execute(
                f"INSERT INTO raw_payloads VALUES ({','.join([p] * 7)})",
                (
                    game_id,
                    source_url,
                    retrieved_at.isoformat(),
                    source_hash,
                    str(local_path),
                    status,
                    error,
                ),
            )
