from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from valkyries import __version__
from valkyries.api_models import Brief, HealthStatus, ScenarioPrediction
from valkyries.artifacts import load_brief
from valkyries.config import Settings

PACKAGE_DIR = Path(__file__).resolve().parent


class ArtifactStore:
    def __init__(self, path: Path | None = None) -> None:
        settings = Settings.from_environment()
        requested = path or settings.artifact_path
        fallback = PACKAGE_DIR / "published" / "aug4_toronto.json"
        self.path = requested if requested.exists() else fallback

    def brief(self) -> Brief:
        if not self.path.exists():
            raise FileNotFoundError(
                "No frozen brief is available. Run `valkyries recommend` first."
            )
        return load_brief(self.path)


store = ArtifactStore()
app = FastAPI(
    title="Valkyries Matchup Intelligence",
    version=__version__,
    description="Frozen, uncertainty-aware lineup scenarios for the August 4 rematch.",
)
app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
PACIFIC = ZoneInfo("America/Los_Angeles")


def _load_or_503() -> Brief:
    try:
        return store.brief()
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _scenarios_for_tolerance(
    brief: Brief, defense_tolerance: float
) -> list[ScenarioPrediction]:
    from statistics import NormalDist

    normal = NormalDist()
    scenarios: list[ScenarioPrediction] = []
    for scenario in brief.scenarios:
        low, high = scenario.defense_interval_80
        standard_error = max((high - low) / (2 * 1.2816), 0.01)
        probability = normal.cdf(
            (defense_tolerance - scenario.defensive_change_pp100) / standard_error
        )
        scenarios.append(
            scenario.model_copy(
                update={
                    "guardrail_probability": round(probability, 4),
                    "meets_guardrail": probability >= 0.75,
                }
            )
        )
    return sorted(
        scenarios,
        key=lambda value: (
            value.meets_guardrail,
            value.offensive_lift_pp100,
            value.guardrail_probability,
        ),
        reverse=True,
    )


@app.get("/api/brief/{game_id}", response_model=Brief)
def api_brief(game_id: str) -> Brief:
    brief = _load_or_503()
    if game_id != brief.target_game_id:
        raise HTTPException(status_code=404, detail="Unknown target game")
    return brief


@app.get("/api/scenarios/{game_id}", response_model=list[ScenarioPrediction])
def api_scenarios(
    game_id: str,
    defense_tolerance: float = Query(default=2.0, ge=0, le=5),
) -> list[ScenarioPrediction]:
    brief = _load_or_503()
    if game_id != brief.target_game_id:
        raise HTTPException(status_code=404, detail="Unknown target game")
    return _scenarios_for_tolerance(brief, defense_tolerance)


@app.get("/api/model-card")
def api_model_card() -> dict[str, object]:
    brief = _load_or_503()
    return {
        "model_run": brief.model_run.model_dump(mode="json"),
        "decision_rule": (
            "Rank offensive lift after requiring at least 75% probability that "
            "defensive degradation stays within the selected tolerance."
        ),
        "half_court_proxy": (
            "Terminal action occurs more than seven seconds after possession start; "
            "five- and nine-second sensitivity checks are retained."
        ),
        "deferred": {
            "keras": (
                "Deferred until a sequence model beats the rolling-origin benchmark "
                "with enough event-sequence data to justify the complexity."
            )
        },
        "caveats": brief.caveats,
    }


@app.get("/api/health", response_model=HealthStatus)
def api_health() -> HealthStatus:
    brief = _load_or_503()
    return HealthStatus(
        status="ok",
        source_freshness_at=brief.data_cutoff_at,
        last_successful_pipeline_at=brief.model_run.created_at,
        published_model_version=brief.model_run.model_run_id,
        target_game_id=brief.target_game_id,
        artifact_frozen_at=brief.frozen_at,
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    brief = _load_or_503()
    return templates.TemplateResponse(
        request=request,
        name="brief.html",
        context={
            "brief": brief,
            "scheduled_local": brief.scheduled_at.astimezone(PACIFIC),
            "active": "brief",
        },
    )


@app.get("/scenarios", response_class=HTMLResponse)
def scenarios(request: Request) -> HTMLResponse:
    brief = _load_or_503()
    return templates.TemplateResponse(
        request=request,
        name="scenarios.html",
        context={"brief": brief, "active": "scenarios"},
    )


@app.get("/model-data", response_class=HTMLResponse)
def model_data(request: Request) -> HTMLResponse:
    brief = _load_or_503()
    return templates.TemplateResponse(
        request=request,
        name="model_data.html",
        context={"brief": brief, "active": "model"},
    )
