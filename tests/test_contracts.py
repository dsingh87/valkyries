from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from valkyries.contracts import DataContractError, GameBundle, parse_clock_seconds


def test_espn_bundle_uses_canonical_source_order(
    espn_payload_factory: Callable[[], dict[str, Any]],
) -> None:
    payload = espn_payload_factory()

    bundle = GameBundle.from_espn(
        payload,
        source_url="https://example.test/summary?event=game-1",
        retrieved_at=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert [event.sequence_number for event in bundle.events] == list(range(1, 10))
    assert bundle.events[3].source_sequence_number == 10
    assert bundle.home_team.abbreviation == "GS"
    assert len(bundle.starters["HOME"]) == 5


@pytest.mark.parametrize(
    ("clock", "seconds"),
    [("10:00", 600), ("1:03", 63), ("39.4", 40), ("0.0", 0)],
)
def test_parse_clock_supports_sub_minute_decimal_clock(
    clock: str,
    seconds: int,
) -> None:
    assert parse_clock_seconds(clock) == seconds


def test_rejects_final_score_mismatch(
    espn_payload_factory: Callable[[], dict[str, Any]],
) -> None:
    payload = espn_payload_factory()
    payload["header"]["competitions"][0]["competitors"][0]["score"] = "3"

    with pytest.raises(DataContractError, match="does not reconcile"):
        GameBundle.from_espn(payload, source_url="https://example.test")
