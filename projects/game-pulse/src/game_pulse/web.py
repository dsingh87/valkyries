from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from game_pulse import __version__
from game_pulse.artifact import DEFAULT_ARTIFACT_PATH, load_artifact
from game_pulse.contracts import (
    GameDetail,
    GamePulseArtifact,
    GameSummary,
    HealthStatus,
    ModelCard,
)
from game_pulse.view import calibration_chart, timeline_chart

PACKAGE_DIR = Path(__file__).resolve().parent


class ArtifactStore:
    def __init__(self, path: Path | None = None) -> None:
        configured = os.environ.get("GAME_PULSE_ARTIFACT_PATH")
        self.path = path or (Path(configured) if configured else DEFAULT_ARTIFACT_PATH)

    def load(self) -> GamePulseArtifact:
        return load_artifact(self.path)


store = ArtifactStore()
app = FastAPI(
    title="Valkyries Game Pulse",
    version=__version__,
    description="Out-of-time possession win probability for the 2026 Valkyries.",
)
app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
PACIFIC = ZoneInfo("America/Los_Angeles")


def _artifact() -> GamePulseArtifact:
    try:
        return store.load()
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _game(game_id: str) -> GameDetail:
    artifact = _artifact()
    for game in artifact.games:
        if game.game_id == game_id:
            return game
    raise HTTPException(status_code=404, detail="Unknown Game Pulse game")


@app.get("/api/games", response_model=list[GameSummary])
def api_games() -> list[GameDetail]:
    return _artifact().games


@app.get("/api/games/{game_id}", response_model=GameDetail)
def api_game(game_id: str) -> GameDetail:
    return _game(game_id)


@app.get("/api/model-card", response_model=ModelCard)
def api_model_card() -> ModelCard:
    return _artifact().model_card


@app.get("/api/health", response_model=HealthStatus)
def api_health() -> HealthStatus:
    artifact = _artifact()
    return HealthStatus(
        status="ok",
        schema_version=artifact.schema_version,
        artifact_frozen_at=artifact.frozen_at,
        data_cutoff_at=artifact.data_cutoff_at,
        model_run_id=artifact.model_card.model_run_id,
        champion=artifact.model_card.champion,
        default_game_id=artifact.default_game_id,
        games_available=len(artifact.games),
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    game_id: str | None = Query(default=None),
) -> HTMLResponse:
    artifact = _artifact()
    selected_id = game_id or artifact.default_game_id
    game = _game(selected_id)
    champion_result = next(
        model
        for model in artifact.model_card.models
        if model.name == artifact.model_card.champion
    )
    best_test_result = min(
        (model for model in artifact.model_card.models if model.name != "prior"),
        key=lambda model: model.test.game_balanced_brier,
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "artifact": artifact,
            "game": game,
            "game_date_local": game.game_date.astimezone(PACIFIC),
            "game_options": [
                {"game": option, "date": option.game_date.astimezone(PACIFIC)}
                for option in artifact.games
            ],
            "timeline_chart": timeline_chart(game),
            "calibration_chart": calibration_chart(artifact.model_card.calibration),
            "champion_result": champion_result,
            "best_test_result": best_test_result,
            "selection_reversal": best_test_result.name != champion_result.name,
        },
    )
