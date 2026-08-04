from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class DataContractError(ValueError):
    """Raised when a source payload cannot safely enter the analytical model."""


def _as_int(value: Any, *, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(value)


def parse_clock_seconds(value: str) -> int:
    if ":" not in value:
        return math.ceil(float(value))
    minutes, seconds = value.split(":", maxsplit=1)
    return int(minutes) * 60 + math.ceil(float(seconds))


def elapsed_game_seconds(period: int, clock: str) -> int:
    remaining = parse_clock_seconds(clock)
    if period <= 4:
        return (period - 1) * 600 + (600 - remaining)
    return 2400 + (period - 5) * 300 + (300 - remaining)


@dataclass(frozen=True)
class Team:
    team_id: str
    abbreviation: str
    display_name: str
    home_away: str
    score: int


@dataclass(frozen=True)
class Athlete:
    athlete_id: str
    display_name: str
    team_id: str
    position: str | None
    starter: bool
    minutes: float | None


@dataclass(frozen=True)
class Event:
    event_id: str
    sequence_number: int
    source_sequence_number: int
    period: int
    clock: str
    elapsed_seconds: int
    action_type: str
    text: str
    team_id: str | None
    participant_ids: tuple[str, ...]
    away_score: int
    home_score: int
    scoring_play: bool
    shooting_play: bool
    score_value: int

    @property
    def is_substitution(self) -> bool:
        return self.action_type.casefold() == "substitution"


@dataclass(frozen=True)
class GameBundle:
    game_id: str
    season: int
    game_date: datetime
    completed: bool
    teams: tuple[Team, Team]
    athletes: tuple[Athlete, ...]
    events: tuple[Event, ...]
    source_url: str
    retrieved_at: datetime
    source_hash: str
    raw_payload: Mapping[str, Any]

    @property
    def home_team(self) -> Team:
        return next(team for team in self.teams if team.home_away == "home")

    @property
    def away_team(self) -> Team:
        return next(team for team in self.teams if team.home_away == "away")

    @property
    def starters(self) -> dict[str, tuple[str, ...]]:
        return {
            team.team_id: tuple(
                athlete.athlete_id
                for athlete in self.athletes
                if athlete.team_id == team.team_id and athlete.starter
            )
            for team in self.teams
        }

    def validate(self) -> None:
        if not self.completed:
            raise DataContractError(f"game {self.game_id} is not complete")
        if len(self.teams) != 2:
            raise DataContractError("a game must contain exactly two teams")
        for team_id, starters in self.starters.items():
            if len(starters) != 5 or len(set(starters)) != 5:
                raise DataContractError(
                    f"team {team_id} must have exactly five unique starters"
                )
        if not self.events:
            raise DataContractError("events must be a non-empty collection")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise DataContractError("event IDs must be unique within a game")
        sequences = [event.sequence_number for event in self.events]
        if any(
            current <= previous for previous, current in zip(sequences, sequences[1:])
        ):
            raise DataContractError(
                "event sequence numbers must be strictly increasing"
            )
        observed_final = (
            max(event.away_score for event in self.events),
            max(event.home_score for event in self.events),
        )
        if observed_final != (
            self.away_team.score,
            self.home_team.score,
        ):
            raise DataContractError(
                "final event score does not reconcile with the box score"
            )

    @classmethod
    def from_espn(
        cls,
        payload: Mapping[str, Any],
        *,
        source_url: str,
        retrieved_at: datetime | None = None,
    ) -> GameBundle:
        retrieved = retrieved_at or datetime.now(UTC)
        raw_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        source_hash = hashlib.sha256(raw_bytes).hexdigest()

        header = payload["header"]
        competition = header["competitions"][0]
        game_id = str(header.get("id") or competition["id"])
        teams: list[Team] = []
        for competitor in competition["competitors"]:
            team = competitor["team"]
            teams.append(
                Team(
                    team_id=str(team["id"]),
                    abbreviation=str(team["abbreviation"]),
                    display_name=str(team["displayName"]),
                    home_away=str(competitor["homeAway"]),
                    score=_as_int(competitor.get("score")),
                )
            )

        athletes: list[Athlete] = []
        for team_box in payload.get("boxscore", {}).get("players", []):
            team_id = str(team_box["team"]["id"])
            for statistics in team_box.get("statistics", []):
                labels = statistics.get("labels", [])
                minute_index = labels.index("MIN") if "MIN" in labels else None
                for row in statistics.get("athletes", []):
                    athlete = row["athlete"]
                    minutes: float | None = None
                    if minute_index is not None and row.get("stats"):
                        raw_minutes = row["stats"][minute_index]
                        if raw_minutes not in (None, "", "--"):
                            minutes = float(raw_minutes)
                    position = athlete.get("position") or {}
                    athletes.append(
                        Athlete(
                            athlete_id=str(athlete["id"]),
                            display_name=str(athlete["displayName"]),
                            team_id=team_id,
                            position=position.get("abbreviation"),
                            starter=bool(row.get("starter")),
                            minutes=minutes,
                        )
                    )

        events: list[Event] = []
        for source_index, play in enumerate(payload.get("plays", []), start=1):
            period = _as_int(play.get("period", {}).get("number"), default=1)
            clock = str(play.get("clock", {}).get("displayValue", "0:00"))
            events.append(
                Event(
                    event_id=str(play["id"]),
                    sequence_number=source_index,
                    source_sequence_number=_as_int(play.get("sequenceNumber")),
                    period=period,
                    clock=clock,
                    elapsed_seconds=elapsed_game_seconds(period, clock),
                    action_type=str(play.get("type", {}).get("text", "Unknown")),
                    text=str(play.get("text", "")),
                    team_id=(str(play["team"]["id"]) if play.get("team") else None),
                    participant_ids=tuple(
                        str(participant["athlete"]["id"])
                        for participant in play.get("participants", [])
                        if participant.get("athlete", {}).get("id") is not None
                    ),
                    away_score=_as_int(play.get("awayScore")),
                    home_score=_as_int(play.get("homeScore")),
                    scoring_play=bool(play.get("scoringPlay")),
                    shooting_play=bool(play.get("shootingPlay")),
                    score_value=_as_int(play.get("scoreValue")),
                )
            )

        status = competition.get("status", {}).get("type", {})
        completed = bool(status.get("completed"))
        game_date = datetime.fromisoformat(
            str(competition["date"]).replace("Z", "+00:00")
        ).astimezone(UTC)
        season = _as_int(header.get("season", {}).get("year"))
        if not season:
            season = game_date.year

        bundle = cls(
            game_id=game_id,
            season=season,
            game_date=game_date,
            completed=completed,
            teams=(teams[0], teams[1]),
            athletes=tuple(athletes),
            events=tuple(events),
            source_url=source_url,
            retrieved_at=retrieved,
            source_hash=source_hash,
            raw_payload=payload,
        )
        bundle.validate()
        return bundle
