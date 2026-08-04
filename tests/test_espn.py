from __future__ import annotations

import io
import json
from unittest.mock import patch
from urllib.error import URLError

import pytest

from valkyries.ingestion.espn import EspnClient, EspnRequestError


def _response(payload: dict[str, object]) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def test_client_retries_transient_failure() -> None:
    client = EspnClient(retries=1, retry_backoff_seconds=0)

    with (
        patch(
            "valkyries.ingestion.espn.urlopen",
            side_effect=[URLError("temporary"), _response({"events": []})],
        ) as request,
        patch("valkyries.ingestion.espn.time.sleep") as sleep,
    ):
        payload = client.season_scoreboard(2026)

    assert payload == {"events": []}
    assert request.call_count == 2
    sleep.assert_called_once_with(0)


def test_client_raises_after_retry_budget() -> None:
    client = EspnClient(retries=1, retry_backoff_seconds=0)

    with (
        patch(
            "valkyries.ingestion.espn.urlopen",
            side_effect=URLError("offline"),
        ),
        patch("valkyries.ingestion.espn.time.sleep"),
        pytest.raises(EspnRequestError, match="failed to fetch"),
    ):
        client.game_summary("game-1")
