from pathlib import Path

import pytest

from game_pulse.artifact import DEFAULT_ARTIFACT_PATH, load_artifact


def test_checksum_verified_round_trip(artifact_path: Path) -> None:
    artifact = load_artifact(artifact_path)
    assert artifact.schema_version == "1.0"
    assert artifact.default_game_id == "401857098"


def test_checksum_tampering_is_rejected(artifact_path: Path) -> None:
    artifact_path.write_text(artifact_path.read_text() + "\n")
    with pytest.raises(ValueError, match="checksum"):
        load_artifact(artifact_path)


def test_published_artifact_contract() -> None:
    artifact = load_artifact(DEFAULT_ARTIFACT_PATH)
    assert len(artifact.games) == 29
    assert artifact.default_game_id == "401857098"
    assert artifact.model_card.champion == "keras_gru"
    for game in artifact.games:
        assert len(game.turning_points) == 5
        assert game.timeline[-1].synthetic is True
        assert game.timeline[-1].win_probability in {0.0, 1.0}
        possession_numbers = [point.possession_number for point in game.timeline]
        assert possession_numbers == sorted(possession_numbers)
        assert all(0 <= point.win_probability <= 1 for point in game.timeline)
