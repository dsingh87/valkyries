from __future__ import annotations

from collections.abc import Callable
from typing import Any

from valkyries.contracts import GameBundle
from valkyries.database import Database
from valkyries.transform import build_possessions, reconstruct_lineups


def test_database_pipeline_is_idempotent(
    tmp_path: Any,
    espn_payload_factory: Callable[[], dict[str, Any]],
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    database.initialize()
    bundle = GameBundle.from_espn(
        espn_payload_factory(), source_url="https://example.test"
    )
    stints, event_lineups = reconstruct_lineups(bundle)
    possessions = build_possessions(bundle, event_lineups)

    database.replace_game(bundle, stints, possessions)
    database.replace_game(bundle, stints, possessions)
    database.build_marts()

    assert database.query("SELECT COUNT(*) AS count FROM games")[0]["count"] == 1
    assert database.query("SELECT COUNT(*) AS count FROM events")[0]["count"] == 9
    assert (
        database.query("SELECT COUNT(*) AS count FROM lineup_stints")[0]["count"] == 2
    )
    assert database.query("SELECT COUNT(*) AS count FROM possessions")[0][
        "count"
    ] == len(possessions)
    assert (
        database.query("SELECT COUNT(*) AS count FROM lineup_features")[0]["count"] > 0
    )
