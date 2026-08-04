# Valkyries Game Pulse

An out-of-time, possession-level win-probability case study for the 2026 Golden State Valkyries. Game Pulse trains exclusively on games completed before 2026, selects and calibrates a champion without touching the test season, and publishes every completed 2026 Valkyries game as a frozen, checksum-verified analyst artifact.

> How did Golden State's probability of winning move from one possession to the next, and which game states carried the most leverage?

The application is descriptive decision support. A possession's win-probability change is not causal player credit, a coaching grade, or a betting recommendation.

## Result

The masked Keras GRU cleared the predeclared selection gate with a `0.1157` game-balanced Brier score versus `0.1213` for logistic regression. On the untouched 2026 test season, however, logistic regression performed better (`0.1677` versus `0.1720`). Game Pulse preserves the frozen selection decision and publishes the reversal as a monitoring signal for the next model cycle.

| Model | Selection Brier | 2026 test Brier | Test calibration error | Decision |
|---|---:|---:|---:|---|
| Prior | 0.2514 | 0.2505 | 0.0841 | Reference only |
| Logistic | 0.1213 | **0.1677** | 0.0419 | Best 2026 test result |
| XGBoost | 0.1244 | 0.1739 | **0.0394** | Did not clear selection gate |
| Keras GRU | **0.1157** | 0.1720 | 0.0398 | Frozen selection winner |

## What this demonstrates

- **Leakage-safe feature engineering:** score, clock, possession, pregame rolling strength, rest, and ten strictly lagged possession outcomes.
- **Model judgment:** a prior reference, regularized scikit-learn logistic model, bounded-depth XGBoost challenger, and masked Keras GRU.
- **Probability validation:** Platt calibration, Brier score, log loss, probability-decile reliability, late-game performance, and game-block bootstrap intervals.
- **Production boundary:** offline training writes a versioned JSON artifact and SHA-256 checksum; FastAPI/Vercel serves no database or ML runtime.
- **Decision interface:** a responsive game selector, win-probability timeline, turning-point ranking, model comparison, and visible interpretation limits.

## Reproduce locally

Python 3.12 is required. From the repository root:

```bash
python3.12 -m venv .venv-game-pulse
source .venv-game-pulse/bin/activate
python -m pip install -e 'projects/game-pulse[dev,modeling]'

game-pulse build \
  --database-url sqlite:///data/valkyries.sqlite3 \
  --cutoff 2026-08-03T08:00:00Z \
  --team GS \
  --season 2026

fastapi dev projects/game-pulse/src/game_pulse/web.py
```

Validate the frozen package without loading modeling dependencies:

```bash
game-pulse validate
```

## Public interfaces

```text
GET /api/games
GET /api/games/{game_id}
GET /api/model-card
GET /api/health
GET /?game_id={game_id}
```

The default showcase is ESPN game `401857098`, Golden State's 89–91 loss at Phoenix on July 29, 2026.

## Deployment

Create a separate Vercel project from this repository and set **Root Directory** to `projects/game-pulse`. The checked-in frozen artifact is package data; the SQLite source and TensorFlow/XGBoost training stack are excluded from deployment.

## Verification

```bash
cd projects/game-pulse
ruff check .
ruff format --check .
mypy src
pytest
```

See [the model card](docs/model-card.md) for the actual champion, holdout metrics, and limitations.
