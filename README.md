# Valkyries–Toronto Matchup Intelligence

A reproducible basketball decision-support case study for Golden State's August 4, 2026 Toronto rematch. The project turns public play-by-play into validated possessions and lineup stints, benchmarks three modeling approaches, and publishes an uncertainty-aware analyst brief.

> Which feasible Golden State lineup adjustments project to improve half-court offense against Toronto without materially weakening the defense?

The frozen answer uses only games completed by `2026-08-03T08:00:00Z`. It is a scenario comparison—not a causal claim or a proposed coaching rotation.

## Decision snapshot

The published screen considers 38 Golden State lineups used in the 45 days before the cutoff with at least 10 validated half-court possessions. Eight clear the default guardrail: at least a 75% modeled probability that defense declines by no more than 2 points per 100 possessions.

The three bounded-stint candidates are:

1. Kayla Thornton · Gabby Williams · Cecilia Zandalasini · Veronica Burton · Janelle Salaun
2. Gabby Williams · Kaila Charles · Veronica Burton · Laeticia Amihere · Janelle Salaun
3. Tiffany Hayes · Kayla Thornton · Kaila Charles · Veronica Burton · Laeticia Amihere

Read the intervals and evidence counts in the [frozen brief](artifacts/aug4_toronto.json). These estimates are observational, partially pooled, and adjusted toward Toronto's 2026 style and the July 8/August 2 direct matchups.

## What this demonstrates

- **Python:** typed ingestion contracts, event normalization, lineup replay, possession construction, model training, API schemas, and CLI orchestration.
- **SQL and relational data:** normalized raw, event, possession, lineup, pipeline, model, prediction, and recommendation tables plus reviewed analytical marts.
- **scikit-learn:** a leakage-safe `Pipeline`/`ColumnTransformer` Tweedie benchmark.
- **XGBoost:** a nonlinear Poisson benchmark with a predeclared promotion gate.
- **PyMC:** hierarchical offensive/defensive player effects fit with ADVI and posterior-predictive coverage checks.
- **Decision integration:** feasible recent lineups, opponent adjustment, uncertainty guardrails, frozen predictions, and a postgame audit path.
- **Deployment:** a server-rendered FastAPI analyst app designed for Vercel's Python runtime; training remains offline.

Keras is deliberately deferred. A sequence model must first have adequate sequence-level data and beat the rolling-origin benchmark.

## Results

The holdout is separated by game date; possessions from future games never enter training.

| Model | MAE | RMSE | Calibration error | Decision |
|---|---:|---:|---:|---|
| scikit-learn Tweedie | 1.085 | 1.150 | 0.048 | Champion |
| XGBoost Poisson | 1.086 | 1.150 | 0.041 | Not promoted: no MAE improvement |
| PyMC hierarchy | — | — | 67.1% coverage of nominal 80% intervals | Used to diagnose sparse-lineup uncertainty |

Game-level half-court rating MAE is 10.02 for Tweedie and 9.98 for XGBoost. Feature ablations show no material incremental holdout signal from lineup identity, opponent style, or rest in this public-data sample. Those null results and the lower-than-nominal PyMC coverage are published as limitations, not hidden. See [the model card](docs/model-card.md).

## Architecture

```text
ESPN scoreboard + summaries          WNBA HTML contract
             │                         (cross-check)
             └──────────┬──────────────────┘
                        ▼
              immutable raw payloads
          URL · retrieval time · SHA-256
                        ▼
             GameBundle validation
       score · ordering · starters · subs
                        ▼
       events → lineup stints → possessions
                        ▼
              SQL analytical marts
   team_game_features · lineup_features · pregame_matchups
                        ▼
      Tweedie · XGBoost · PyMC benchmarks
                        ▼
         frozen JSON + FastAPI/Vercel app
                        ▼
                 postgame audit
```

SQLite is the zero-configuration local and CI backend. The same schema supports pooled SSL Postgres connections through `psycopg`, suitable for Neon provisioned in Vercel. The deployed request path reads the frozen JSON artifact and does not bundle training dependencies.

## Reproduce locally

Python 3.12 is required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,database,modeling]'

valkyries ingest --start-season 2024 --cutoff 2026-08-03T08:00:00Z
valkyries build
valkyries train --cutoff 2026-08-03T08:00:00Z
valkyries recommend --game-id 401857114

fastapi dev src/valkyries/web.py
```

The first four `valkyries` commands are the end-to-end reproduction path. The checked-in frozen artifact lets the web app run without re-downloading or retraining.

### CLI

```text
valkyries ingest --start-season 2024 --cutoff <timestamp>
valkyries build
valkyries train --cutoff <timestamp>
valkyries recommend --game-id <id>
valkyries audit --game-id <id>
```

Set `DATABASE_URL` to a Postgres URL for Neon; otherwise `data/valkyries.sqlite3` is used. `VALKYRIES_ARTIFACT_PATH` overrides the published JSON location.

## Analyst app and API

The app has three views:

- **Pregame brief:** direct answer, recommendations, intervals, and caveats.
- **Scenario explorer:** browser-side comparison across defensive-risk tolerances.
- **Model & data:** rolling benchmark, uncertainty coverage, lineage, hashes, and limitations.

Public interfaces:

```text
GET /api/brief/401857114
GET /api/scenarios/401857114?defense_tolerance=2
GET /api/model-card
GET /api/health
```

Deploy to Vercel after linking the repository:

```bash
npx vercel
npx vercel --prod
```

`vercel.json` routes requests to `api/index.py`. If Neon is not configured, the app intentionally serves the same versioned frozen artifact while SQLite remains the demonstrated local/CI relational backend.

## Data quality contract

The backfill discovered 753 completed 2024–2026 games before the cutoff. It published 739 (98.1%) and quarantined 14 rather than silently accepting incomplete lineage. The database contains:

- 291,552 normalized events
- 21,276 reconstructed lineup stints
- 120,514 possessions
- 172 bounded score-attribution corrections (0.14%), excluded from model marts

Validation covers empty actions, event identity/order, final-score reconciliation, starters and substitutions, five-player lineups, minutes, overtime, cutoff compliance, and idempotent reruns. Details are in [the data-quality report](docs/data-quality.md).

“Half-court” is a documented public-data proxy: the terminal scoring attempt, foul, or turnover occurs more than seven seconds after possession start. Five- and nine-second flags are retained for sensitivity. It is not tracking-derived transition classification.

## Verification

```bash
ruff check .
ruff format --check .
mypy src
pytest
```

CI also imports the Vercel entrypoint and runs a small SQL/end-to-end fixture. Model training is intentionally offline because PyMC and XGBoost do not belong in a serverless request.

## Five-minute interview walkthrough

1. Start with the basketball question and defensive guardrail.
2. Show one quarantined game and one validated `GameBundle` flowing through the SQL schema.
3. Compare the Tweedie and XGBoost holdout results; explain why the simpler model wins the gate.
4. Move the defensive tolerance slider and discuss posterior uncertainty and sample size.
5. Open the frozen hash and postgame audit command to show the system cannot rewrite its pregame prediction.

## Limitations

- Public events do not identify coverage, screening actions, off-ball responsibility, health, or tactical intent.
- Lineup results are observational and cannot establish a causal rotation effect.
- The opponent adjustment is transparent shrinkage, not a tracking-based matchup model.
- The PyMC nominal 80% interval covered 67.1% on the holdout and needs recalibration.
- Availability is inferred from recently used lineups; a private team system should use authoritative active-roster and medical inputs.
- Direct WNBA HTML requests can be blocked, so ESPN is operational and the WNBA adapter is retained as a source contract/cross-check.

## Repository map

```text
api/                         Vercel FastAPI entrypoint
artifacts/                   frozen Toronto brief and checksum
docs/                        model card, data quality, source contract
models/                      shareable metrics and PyMC summaries
src/valkyries/               ingestion, transforms, SQL, models, API, UI
tests/                       contracts, transformations, SQL, API
.github/workflows/ci.yml     quality and deployment-entrypoint checks
```
