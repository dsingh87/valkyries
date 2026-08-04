from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from valkyries.contracts import GameBundle

SCOREBOARD_ENDPOINT = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
)
SUMMARY_ENDPOINT = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary"
)


class EspnRequestError(RuntimeError):
    """Raised after the ESPN client exhausts bounded retries."""


class EspnClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        retries: int = 3,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def _get_json(self, endpoint: str, params: Mapping[str, str]) -> Mapping[str, Any]:
        url = f"{endpoint}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "valkyries-matchup-intelligence/0.1",
            },
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = json.load(response)
                if not isinstance(payload, Mapping):
                    raise EspnRequestError("ESPN response must be a JSON object")
                return payload
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(self.retry_backoff_seconds * (2**attempt))
        raise EspnRequestError(f"failed to fetch {url}") from last_error

    def season_scoreboard(self, season: int) -> Mapping[str, Any]:
        return self._get_json(
            SCOREBOARD_ENDPOINT,
            {"dates": str(season), "limit": "500"},
        )

    def game_summary(self, game_id: str) -> Mapping[str, Any]:
        return self._get_json(SUMMARY_ENDPOINT, {"event": game_id})

    def completed_game_ids(
        self,
        *,
        start_season: int,
        cutoff: datetime,
    ) -> Iterator[str]:
        cutoff_utc = cutoff.astimezone(UTC)
        for season in range(start_season, cutoff_utc.year + 1):
            scoreboard = self.season_scoreboard(season)
            for event in scoreboard.get("events", []):
                competitions = event.get("competitions") or []
                if not competitions:
                    continue
                competition = competitions[0]
                completed = bool(
                    competition.get("status", {}).get("type", {}).get("completed")
                )
                event_date = datetime.fromisoformat(
                    str(event["date"]).replace("Z", "+00:00")
                ).astimezone(UTC)
                season_type = event.get("season", {}).get("type")
                if completed and event_date <= cutoff_utc and season_type == 2:
                    yield str(event["id"])

    def load_bundle(self, game_id: str) -> GameBundle:
        url = f"{SUMMARY_ENDPOINT}?{urlencode({'event': game_id})}"
        return GameBundle.from_espn(
            self.game_summary(game_id),
            source_url=url,
        )
