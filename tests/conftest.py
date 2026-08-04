from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest


@pytest.fixture
def espn_payload_factory() -> Callable[[], dict[str, Any]]:
    def factory() -> dict[str, Any]:
        home_players = [
            (f"H{index}", f"Home {index}", index <= 5, 40.0) for index in range(1, 7)
        ]
        home_players[0] = ("H1", "Home 1", True, 5.0)
        home_players[5] = ("H6", "Home 6", False, 35.0)
        away_players = [
            (f"A{index}", f"Away {index}", True, 40.0) for index in range(1, 6)
        ]

        def team_box(
            team_id: str,
            abbreviation: str,
            players: list[tuple[str, str, bool, float]],
        ) -> dict[str, Any]:
            return {
                "team": {"id": team_id, "abbreviation": abbreviation},
                "statistics": [
                    {
                        "labels": ["MIN", "PTS"],
                        "athletes": [
                            {
                                "athlete": {
                                    "id": player_id,
                                    "displayName": name,
                                    "position": {"abbreviation": "G"},
                                },
                                "starter": starter,
                                "stats": [str(minutes), "0"],
                            }
                            for player_id, name, starter, minutes in players
                        ],
                    }
                ],
            }

        def play(
            play_id: str,
            source_sequence: int,
            action: str,
            clock: str,
            *,
            team_id: str | None = None,
            home_score: int = 0,
            away_score: int = 0,
            scoring: bool = False,
            shooting: bool = False,
            score_value: int = 0,
            participants: tuple[str, ...] = (),
            period: int = 1,
        ) -> dict[str, Any]:
            row: dict[str, Any] = {
                "id": play_id,
                "sequenceNumber": str(source_sequence),
                "type": {"text": action},
                "text": action,
                "awayScore": away_score,
                "homeScore": home_score,
                "period": {"number": period},
                "clock": {"displayValue": clock},
                "scoringPlay": scoring,
                "shootingPlay": shooting,
                "scoreValue": score_value,
                "participants": [
                    {"athlete": {"id": participant}} for participant in participants
                ],
            }
            if team_id is not None:
                row["team"] = {"id": team_id}
            return row

        return {
            "header": {
                "id": "game-1",
                "season": {"year": 2026},
                "competitions": [
                    {
                        "id": "game-1",
                        "date": datetime(2026, 8, 1, 2, tzinfo=UTC).isoformat(),
                        "status": {"type": {"completed": True}},
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "2",
                                "team": {
                                    "id": "HOME",
                                    "abbreviation": "GS",
                                    "displayName": "Golden State Valkyries",
                                },
                            },
                            {
                                "homeAway": "away",
                                "score": "0",
                                "team": {
                                    "id": "AWAY",
                                    "abbreviation": "TOR",
                                    "displayName": "Toronto Tempo",
                                },
                            },
                        ],
                    }
                ],
            },
            "boxscore": {
                "players": [
                    team_box("HOME", "GS", home_players),
                    team_box("AWAY", "TOR", away_players),
                ]
            },
            "plays": [
                play("e1", 4, "Jumpball", "10:00", team_id="HOME"),
                play(
                    "e2",
                    8,
                    "Jump Shot",
                    "9:40",
                    team_id="HOME",
                    home_score=2,
                    scoring=True,
                    shooting=True,
                    score_value=2,
                ),
                play(
                    "e3",
                    12,
                    "Bad Pass Turnover",
                    "9:20",
                    team_id="AWAY",
                    home_score=2,
                ),
                # A source correction can have a non-monotonic source sequence.
                play(
                    "e4",
                    10,
                    "Substitution",
                    "5:00",
                    team_id="HOME",
                    home_score=2,
                    participants=("H6", "H1"),
                ),
                play(
                    "e5",
                    20,
                    "Jump Shot",
                    "4:55",
                    team_id="HOME",
                    home_score=2,
                    shooting=True,
                ),
                play(
                    "e6",
                    22,
                    "Defensive Rebound",
                    "4:50",
                    team_id="AWAY",
                    home_score=2,
                ),
                play(
                    "e7",
                    24,
                    "Lost Ball Turnover",
                    "4:30",
                    team_id="AWAY",
                    home_score=2,
                ),
                play("e8", 26, "End Period", "0.0", home_score=2, period=4),
                play("e9", 28, "End Game", "0.0", home_score=2, period=4),
            ],
        }

    return factory
