# Model card: August 4 Toronto matchup

## Intended decision

Rank recently used Golden State five-player groups by projected half-court offensive lift against Toronto, conditional on a defensive-risk guardrail. The output supports analyst discussion; it does not set rotations or claim causal player impact.

## Version and training boundary

- Model run: `4bad26019ec2f6aab85f27a9`
- Data cutoff: `2026-08-03T08:00:00Z`
- Data hash: `414eb42e00d146c19407872b5bd7fee441fd89da4bce22a52d614578fa9c4522`
- Feature schema hash: `edb8c9809bcc2f3c9e868ae01f54c8926625fd099b0fb6e8b521101982ad4a2c`
- Target game: ESPN `401857114`, Toronto at Golden State
- Deterministic seed: `87`

## Model layers

### scikit-learn benchmark and champion

A `ColumnTransformer` one-hot encodes team and lineup identifiers and standardizes numeric context. A regularized `TweedieRegressor(power=1.2, link="log")` estimates possession points. It remains champion because the challenger did not clear the predeclared out-of-time gate.

### XGBoost challenger

An `XGBRegressor` uses a Poisson objective, 250 trees, depth 4, shrinkage, row/column subsampling, and L2 regularization. It improved calibration error from 0.0477 to 0.0413 but slightly increased possession MAE from 1.0855 to 1.0861, so it was not promoted.

### PyMC uncertainty model

A hierarchical Poisson model estimates partially pooled offensive and defensive player effects across lineup-pair stints. Exposure is the number of stint possessions. ADVI uses 3,000 iterations and 800 posterior draws for this MVP. Observed coverage of nominal 80% posterior-predictive intervals was 67.1%, so intervals are treated as directional and flagged for recalibration.

## Evaluation

Games are ordered by date. The first 80% form the training set and the final 20% form the holdout; possessions are never randomly split across games.

| Model | Possession MAE | RMSE | Game rating MAE | Decile calibration error |
|---|---:|---:|---:|---:|
| Tweedie | 1.0855 | 1.1497 | 10.02 | 0.0477 |
| XGBoost | 1.0861 | 1.1497 | 9.98 | 0.0413 |

The model registry preserves both results, calibration-decile summaries, and the gate decision. This MVP uses one rolling-origin 80/20 game-date holdout; multiple rolling folds remain future work.

### Feature ablations

| Tweedie feature set | MAE | Change from full model |
|---|---:|---:|
| Full pregame feature set | 1.085496 | — |
| Without lineup identifiers | 1.085497 | +0.0000004 |
| Without opponent-style rolling features | 1.085079 | -0.000418 |
| Without rest | 1.085505 | +0.000009 |

None produces a practically meaningful change. In particular, the public-data opponent-style features do not earn a performance claim. They remain useful as a transparent scenario adjustment, but the recommendations are labeled directional.

## Decision rule

Candidates must:

1. Have been used by Golden State in the 45 days before cutoff.
2. Have at least 10 validated half-court possessions on offense and defense.
3. Be ranked by offensive lift only after the probability of staying within the selected defensive downside is at least 75%.

The default downside is 2 points allowed per 100 possessions. The UI recomputes the guardrail from frozen posterior summaries for tolerances from 0 to 5.

## Opponent adjustment

Lineup rates are shrunk toward Golden State's 2026 baseline with a 25-possession prior. They are then adjusted 35% toward Toronto's 2026 half-court offense/defense relative to league average. The July 8 and August 2 direct matchups receive an additional capped empirical-Bayes weight of 35%. This is an explicit, auditable style adjustment—not a learned tracking-data matchup effect.

## Leakage controls

- Every training query enforces the UTC cutoff.
- The split is performed at game level and ordered by game date.
- Postgame target fields do not appear in the pregame feature schema.
- The brief stores the cutoff, data hash, feature schema hash, model version, and freeze time.
- The audit path writes a separate artifact and never mutates the frozen brief.

## Limitations and prohibited uses

- Do not use estimates as causal player or rotation effects.
- Do not infer defensive coverage, health, role, or tactical intent.
- Do not use public lineup inference for high-stakes personnel decisions without authoritative validation.
- PyMC interval coverage is below nominal and should not be described as calibrated.
- Feature ablations show no practically meaningful holdout contribution from lineup, opponent-style, or rest variables in this sample.
- Recent lineup use is only a proxy for availability.
- Keras is deferred until sequence sample size and an out-of-time improvement test justify it.

## Monitoring

`pipeline_runs` records attempted, published, and quarantined games. `model_runs` stores metrics and hashes. `/api/health` exposes source freshness, last successful model run, model version, target, and freeze timestamp. `valkyries audit` creates a postgame comparison when the target game becomes final.
