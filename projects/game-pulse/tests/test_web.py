from pathlib import Path

from fastapi.testclient import TestClient

from game_pulse.web import app, store


def test_api_and_dashboard_contracts(artifact_path: Path) -> None:
    original = store.path
    store.path = artifact_path
    try:
        client = TestClient(app)
        games = client.get("/api/games")
        detail = client.get("/api/games/401857098")
        model_card = client.get("/api/model-card")
        health = client.get("/api/health")
        page = client.get("/")
        assert games.status_code == detail.status_code == 200
        assert model_card.status_code == health.status_code == page.status_code == 200
        assert games.json()[0]["game_id"] == "401857098"
        assert detail.json()["timeline"][-1]["synthetic"] is True
        assert health.json()["champion"] == "logistic"
        assert "Valkyries Game Pulse" in page.text
        assert "Win probability timeline" in page.text
        assert '<script defer src="/_vercel/insights/script.js"></script>' in page.text
    finally:
        store.path = original


def test_unknown_game_returns_404(artifact_path: Path) -> None:
    original = store.path
    store.path = artifact_path
    try:
        client = TestClient(app)
        assert client.get("/api/games/not-a-game").status_code == 404
        assert client.get("/", params={"game_id": "not-a-game"}).status_code == 404
    finally:
        store.path = original
