from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import TypeAlias

from valkyries.contracts import DataContractError, Event, GameBundle

LineupSnapshot: TypeAlias = dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class LineupStint:
    stint_id: str
    game_id: str
    start_event_id: str
    end_event_id: str
    start_elapsed_seconds: int
    end_elapsed_seconds: int
    duration_seconds: int
    home_team_id: str
    away_team_id: str
    home_lineup: tuple[str, ...]
    away_lineup: tuple[str, ...]


@dataclass(frozen=True)
class Possession:
    possession_id: str
    game_id: str
    possession_number: int
    period: int
    offense_team_id: str
    defense_team_id: str
    offense_lineup: tuple[str, ...]
    defense_lineup: tuple[str, ...]
    start_elapsed_seconds: int
    end_elapsed_seconds: int
    duration_seconds: int
    points: int
    score_correction: int
    margin_before: int
    is_home_offense: bool
    is_half_court_5: bool
    is_half_court_7: bool
    is_half_court_9: bool
    terminal_action: str
    terminal_event_id: str


def lineup_key(players: tuple[str, ...]) -> str:
    return "|".join(sorted(players))


def _stable_id(*parts: object) -> str:
    value = ":".join(str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _snapshot(lineups: dict[str, set[str]]) -> LineupSnapshot:
    return {team_id: tuple(sorted(players)) for team_id, players in lineups.items()}


def _apply_substitution(event: Event, lineups: dict[str, set[str]]) -> None:
    if event.team_id is None or event.team_id not in lineups:
        raise DataContractError(
            f"substitution {event.event_id} does not identify a valid team"
        )
    if len(event.participant_ids) < 2:
        raise DataContractError(
            f"substitution {event.event_id} must identify entering and leaving players"
        )
    entering, leaving = event.participant_ids[:2]
    lineup = lineups[event.team_id]
    if leaving not in lineup:
        raise DataContractError(
            f"substitution {event.event_id} removes player {leaving} "
            f"who is not on court"
        )
    if entering in lineup and entering != leaving:
        raise DataContractError(
            f"substitution {event.event_id} adds player {entering} "
            f"who is already on court"
        )
    lineup.remove(leaving)
    lineup.add(entering)
    if len(lineup) != 5:
        raise DataContractError(
            f"substitution {event.event_id} leaves team {event.team_id} "
            f"with {len(lineup)} players"
        )


def reconstruct_lineups(
    bundle: GameBundle,
) -> tuple[list[LineupStint], dict[str, LineupSnapshot]]:
    bundle.validate()
    lineups = {team_id: set(starters) for team_id, starters in bundle.starters.items()}
    event_lineups: dict[str, LineupSnapshot] = {}
    stints: list[LineupStint] = []
    stint_start = 0
    stint_start_event = bundle.events[0].event_id
    previous_event = bundle.events[0]
    current_stint_lineups = _snapshot(lineups)
    home_id = bundle.home_team.team_id
    away_id = bundle.away_team.team_id

    for event in bundle.events:
        event_lineups[event.event_id] = _snapshot(lineups)
        if event.is_substitution:
            if event.elapsed_seconds > stint_start:
                stints.append(
                    LineupStint(
                        stint_id=_stable_id(
                            bundle.game_id,
                            stint_start,
                            event.elapsed_seconds,
                            lineup_key(current_stint_lineups[home_id]),
                            lineup_key(current_stint_lineups[away_id]),
                        ),
                        game_id=bundle.game_id,
                        start_event_id=stint_start_event,
                        end_event_id=event.event_id,
                        start_elapsed_seconds=stint_start,
                        end_elapsed_seconds=event.elapsed_seconds,
                        duration_seconds=event.elapsed_seconds - stint_start,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        home_lineup=current_stint_lineups[home_id],
                        away_lineup=current_stint_lineups[away_id],
                    )
                )
                stint_start = event.elapsed_seconds
                stint_start_event = event.event_id
            _apply_substitution(event, lineups)
            current_stint_lineups = _snapshot(lineups)
        previous_event = event

    game_end = previous_event.elapsed_seconds
    if game_end > stint_start:
        stints.append(
            LineupStint(
                stint_id=_stable_id(
                    bundle.game_id,
                    stint_start,
                    game_end,
                    lineup_key(current_stint_lineups[home_id]),
                    lineup_key(current_stint_lineups[away_id]),
                ),
                game_id=bundle.game_id,
                start_event_id=stint_start_event,
                end_event_id=previous_event.event_id,
                start_elapsed_seconds=stint_start,
                end_elapsed_seconds=game_end,
                duration_seconds=game_end - stint_start,
                home_team_id=home_id,
                away_team_id=away_id,
                home_lineup=current_stint_lineups[home_id],
                away_lineup=current_stint_lineups[away_id],
            )
        )

    if not stints or sum(stint.duration_seconds for stint in stints) != game_end:
        raise DataContractError("lineup stints do not reconcile to game duration")
    for stint in stints:
        if len(stint.home_lineup) != 5 or len(stint.away_lineup) != 5:
            raise DataContractError(
                "every lineup stint must contain five players per team"
            )
    return stints, event_lineups


_FREE_THROW_NUMBER = re.compile(r"Free Throw\s*-\s*(\d+) of (\d+)", re.I)


def _is_last_free_throw(event: Event) -> bool:
    match = _FREE_THROW_NUMBER.search(event.action_type)
    if match is None:
        match = _FREE_THROW_NUMBER.search(event.text)
    return match is not None and match.group(1) == match.group(2)


def _terminal_offense(
    event: Event,
    *,
    team_ids: tuple[str, str],
) -> str | None:
    action = event.action_type.casefold()
    if "defensive rebound" in action and event.team_id is not None:
        return next(team_id for team_id in team_ids if team_id != event.team_id)
    if "turnover" in action and event.team_id is not None:
        return event.team_id
    if event.shooting_play and event.scoring_play and "free throw" not in action:
        return event.team_id
    if _is_last_free_throw(event):
        return event.team_id
    return None


def build_possessions(
    bundle: GameBundle,
    event_lineups: dict[str, LineupSnapshot],
) -> list[Possession]:
    team_ids = (bundle.home_team.team_id, bundle.away_team.team_id)
    previous_scores = {
        bundle.home_team.team_id: 0,
        bundle.away_team.team_id: 0,
    }
    previous_terminal_elapsed = 0
    previous_period = 1
    possessions: list[Possession] = []

    for event in bundle.events:
        offense_id = _terminal_offense(event, team_ids=team_ids)
        if offense_id is None:
            continue
        defense_id = next(team_id for team_id in team_ids if team_id != offense_id)
        if event.period != previous_period:
            previous_terminal_elapsed = (
                (event.period - 1) * 600
                if event.period <= 4
                else 2400 + (event.period - 5) * 300
            )
            previous_period = event.period

        current_scores = {
            bundle.away_team.team_id: event.away_score,
            bundle.home_team.team_id: event.home_score,
        }
        points = max(current_scores[offense_id] - previous_scores[offense_id], 0)
        margin_before = previous_scores[offense_id] - previous_scores[defense_id]
        duration = max(event.elapsed_seconds - previous_terminal_elapsed, 0)
        lineups = event_lineups[event.event_id]
        number = len(possessions) + 1
        possessions.append(
            Possession(
                possession_id=_stable_id(bundle.game_id, number, event.event_id),
                game_id=bundle.game_id,
                possession_number=number,
                period=event.period,
                offense_team_id=offense_id,
                defense_team_id=defense_id,
                offense_lineup=lineups[offense_id],
                defense_lineup=lineups[defense_id],
                start_elapsed_seconds=previous_terminal_elapsed,
                end_elapsed_seconds=event.elapsed_seconds,
                duration_seconds=duration,
                points=points,
                score_correction=0,
                margin_before=margin_before,
                is_home_offense=offense_id == bundle.home_team.team_id,
                is_half_court_5=duration > 5,
                is_half_court_7=duration > 7,
                is_half_court_9=duration > 9,
                terminal_action=event.action_type,
                terminal_event_id=event.event_id,
            )
        )
        previous_scores = current_scores
        previous_terminal_elapsed = event.elapsed_seconds

    if not possessions:
        raise DataContractError("no possessions could be derived from the event stream")
    final_scores = {
        bundle.home_team.team_id: bundle.home_team.score,
        bundle.away_team.team_id: bundle.away_team.score,
    }
    possession_points = {
        team_id: sum(
            possession.points
            for possession in possessions
            if possession.offense_team_id == team_id
        )
        for team_id in team_ids
    }
    for team_id in team_ids:
        difference = final_scores[team_id] - possession_points[team_id]
        if abs(difference) > 3:
            raise DataContractError(
                f"derived possession points {possession_points[team_id]} do not "
                f"reconcile with team {team_id} score {final_scores[team_id]}"
            )
        if difference == 0:
            continue
        candidate_indexes = [
            index
            for index, possession in enumerate(possessions)
            if possession.offense_team_id == team_id
            and possession.points + difference >= 0
        ]
        if not candidate_indexes:
            raise DataContractError(
                f"no possession can safely absorb score correction {difference} "
                f"for team {team_id}"
            )
        index = candidate_indexes[-1]
        possessions[index] = replace(
            possessions[index],
            points=possessions[index].points + difference,
            score_correction=difference,
        )
    return possessions


def validate_player_minutes(
    bundle: GameBundle,
    stints: list[LineupStint],
    *,
    tolerance_seconds: int = 90,
) -> None:
    for athlete in bundle.athletes:
        if athlete.minutes is None:
            continue
        seconds = 0
        for stint in stints:
            lineup = (
                stint.home_lineup
                if athlete.team_id == stint.home_team_id
                else stint.away_lineup
            )
            if athlete.athlete_id in lineup:
                seconds += stint.duration_seconds
        expected = round(athlete.minutes * 60)
        if abs(seconds - expected) > tolerance_seconds:
            raise DataContractError(
                f"player {athlete.athlete_id} reconstructed {seconds} seconds "
                f"does not reconcile with box score {expected} seconds"
            )
