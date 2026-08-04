from __future__ import annotations

from collections.abc import Callable
from typing import Any

from valkyries.contracts import GameBundle
from valkyries.transform import (
    build_possessions,
    reconstruct_lineups,
    validate_player_minutes,
)


def test_reconstructs_lineups_and_possessions(
    espn_payload_factory: Callable[[], dict[str, Any]],
) -> None:
    bundle = GameBundle.from_espn(
        espn_payload_factory(), source_url="https://example.test"
    )

    stints, event_lineups = reconstruct_lineups(bundle)
    possessions = build_possessions(bundle, event_lineups)
    validate_player_minutes(bundle, stints, tolerance_seconds=0)

    assert len(stints) == 2
    assert stints[0].duration_seconds == 300
    assert "H1" in stints[0].home_lineup
    assert "H6" in stints[1].home_lineup
    assert all(len(possession.offense_lineup) == 5 for possession in possessions)
    assert (
        sum(
            possession.points
            for possession in possessions
            if possession.offense_team_id == "HOME"
        )
        == 2
    )
    assert any(possession.is_half_court_7 for possession in possessions)
