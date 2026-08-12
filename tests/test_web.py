from fastapi.testclient import TestClient

from valkyries.web import app

client = TestClient(app)


def test_brief_api_returns_frozen_contract() -> None:
    response = client.get("/api/brief/401857114")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["data_cutoff_at"] == "2026-08-03T08:00:00Z"
    assert len(body["recommendations"]) == 3
    assert all(len(item["lineup_ids"]) == 5 for item in body["scenarios"])


def test_scenario_tolerance_recomputes_guardrail() -> None:
    strict = client.get("/api/scenarios/401857114", params={"defense_tolerance": 0})
    permissive = client.get("/api/scenarios/401857114", params={"defense_tolerance": 5})

    assert strict.status_code == permissive.status_code == 200
    strict_count = sum(item["meets_guardrail"] for item in strict.json())
    permissive_count = sum(item["meets_guardrail"] for item in permissive.json())
    assert permissive_count >= strict_count


def test_unknown_game_and_invalid_threshold() -> None:
    assert client.get("/api/brief/not-a-game").status_code == 404
    assert (
        client.get(
            "/api/scenarios/401857114", params={"defense_tolerance": 6}
        ).status_code
        == 422
    )


def test_health_model_card_and_pages() -> None:
    health = client.get("/api/health")
    model_card = client.get("/api/model-card")

    assert health.status_code == model_card.status_code == 200
    assert health.json()["published_model_version"]
    assert model_card.json()["deferred"]["keras"]
    for path in ("/", "/scenarios", "/model-data"):
        response = client.get(path)
        assert response.status_code == 200
        assert "Valkyries Matchup Intelligence" in response.text
        assert '<script defer src="/_vercel/insights/script.js"></script>' in response.text
