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
) -> None:
    returned_game_id = play_by_play.get("gameId")

    if returned_game_id != expected_game_id:
        raise PlayByPlayValidationError(
            f"Play-by-play game {returned_game_id!r} "
            f"does not match requested game {expected_game_id}"
        )
