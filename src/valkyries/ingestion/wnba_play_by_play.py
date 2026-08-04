import json
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any


class PlayByPlayValidationError(ValueError):
    """Raised when play-by-play data violates the ingestion contract."""


class _NextDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_next_data = False
        self.next_data_chunks: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)

        if tag == "script" and attributes.get("id") == "__NEXT_DATA__":
            self._inside_next_data = True

    def handle_data(self, data: str) -> None:
        if self._inside_next_data:
            self.next_data_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._inside_next_data:
            self._inside_next_data = False


def extract_play_by_play(html: str) -> dict[str, Any]:
    parser = _NextDataParser()
    parser.feed(html)

    if not parser.next_data_chunks:
        raise ValueError("HTML does not contain __NEXT_DATA__")

    page_data = json.loads("".join(parser.next_data_chunks))

    try:
        play_by_play = page_data["props"]["pageProps"]["playByPlay"]
    except (KeyError, TypeError) as error:
        raise ValueError("JSON does not contain play-by-play data") from error

    if not isinstance(play_by_play, dict):
        raise ValueError("Play-by-play data must be an object")

    return play_by_play


def validate_play_by_play(
    play_by_play: Mapping[str, Any],
    *,
    expected_game_id: str,
    expected_final_score: tuple[int, int] | None = None,
) -> None:
    returned_game_id = play_by_play.get("gameId")

    if returned_game_id != expected_game_id:
        raise PlayByPlayValidationError(
            f"Play-by-play game {returned_game_id!r} "
            f"does not match requested game {expected_game_id}"
        )

    actions = play_by_play.get("actions")
    if not isinstance(actions, list) or not actions:
        raise PlayByPlayValidationError("actions must be a non-empty list")

    action_ids: list[int] = []
    for index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            raise PlayByPlayValidationError(
                f"action at source index {index} must be an object"
            )
        action_id = action.get("actionId")
        if not isinstance(action_id, int):
            raise PlayByPlayValidationError(
                f"action at source index {index} has an invalid actionId"
            )
        action_ids.append(action_id)

    if len(action_ids) != len(set(action_ids)):
        raise PlayByPlayValidationError("actionId must be unique within a game")

    if any(
        current <= previous for previous, current in zip(action_ids, action_ids[1:])
    ):
        raise PlayByPlayValidationError(
            "actionId must be strictly increasing in source order"
        )

    if expected_final_score is not None:
        last_action = actions[-1]
        away_score = last_action.get("scoreAway")
        home_score = last_action.get("scoreHome")
        returned_score = (away_score, home_score)
        if returned_score != expected_final_score:
            raise PlayByPlayValidationError(
                f"final play-by-play score {returned_score!r} "
                f"does not match expected score {expected_final_score!r}"
            )
