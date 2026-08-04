# Game Pulse model card

## Intended decision

Estimate the probability that the home team wins at the start of each possession, translate that estimate to the Valkyries' perspective for completed 2026 games, and rank absolute possession-to-possession changes as descriptive turning points.

The model is a historical decision-support case study. It is not a betting product, a causal player-value model, or a coaching grade.

## Version and data boundary

- Model run: `0849aae3668fb1449cff8a5b`
- Data cutoff: `2026-08-03T08:00:00Z`
- Eligible games: 737
- Eligible possession states: 119,931
- 2026 Valkyries games published: 29
- Deterministic seed: `87`

The 518 eligible pre-2026 games are split chronologically into 336 training, 78 validation, 52 calibration, and 52 selection games. All 219 eligible 2026 league games form the untouched test season.

## Models

- **Prior reference:** calibrated training-set home-win rate.
- **Logistic baseline:** median imputation, standardization, regularized logistic regression, and Platt calibration.
- **XGBoost challenger:** bounded-depth trees with shrinkage, row/column subsampling, early stopping, and Platt calibration.
- **Keras challenger:** masked ten-possession sequence, 16-unit GRU, current score-and-clock context, a 16-unit dense head, dropout, early stopping, and Platt calibration.

All models use the same game-level chronological partitions. Sequence values contain only possessions completed before the prediction state.

## Evaluation

Lower values are better. Brier confidence intervals use 1,000 game-block bootstrap samples.

| Model | Selection Brier | Test Brier | Test 95% interval | Test log loss | Test calibration error | Q4/OT Brier |
|---|---:|---:|---:|---:|---:|---:|
| Prior | 0.2514 | 0.2505 | 0.2496–0.2516 | 0.6942 | 0.0841 | 0.2505 |
| Logistic | 0.1213 | **0.1677** | 0.1491–0.1885 | 0.4984 | 0.0419 | **0.1096** |
| XGBoost | 0.1244 | 0.1739 | 0.1580–0.1940 | 0.5174 | **0.0394** | 0.1142 |
| Keras GRU | **0.1157** | 0.1720 | 0.1541–0.1936 | 0.5087 | 0.0398 | 0.1124 |

## Promotion and monitoring decision

A challenger must improve selection-window game-balanced Brier by at least `0.002` without worsening ten-bin calibration error by more than `0.01`. Differences within `0.0005` favor the simpler model.

The Keras GRU cleared that selection rule and remains the frozen winner. The 2026 test season does not rewrite the decision. Logistic regression subsequently produced the best test Brier and late-game Brier, so the monitoring outcome is a model-review trigger: the next cycle should favor the simpler benchmark unless the sequence model demonstrates stable improvement across additional rolling-origin folds.

## Features

Current state includes home-perspective margin, period, period and regulation time remaining, possession, rolling pregame net-rating advantage, rest advantage, explicit missingness flags, and a margin/time pressure interaction.

The ten-possession history includes signed home scoring, duration, offense identity, half-court classification, and terminal-action buckets. Padding is masked. Games—not possession rows—define every split.

## Limitations and prohibited uses

- Do not treat a possession swing as causal player value or coaching quality.
- Do not use the estimates for wagering or live operational decisions.
- Public play-by-play omits timeouts, tactical intent, injuries, assignments, and tracking context.
- Expansion-team early-season rolling features can be missing; the models retain explicit missingness indicators and training-window median imputation.
- The selection result is based on one chronological partition. Additional rolling-origin folds are required before claiming stable sequence-model superiority.
- The terminal game state is set to the observed 0% or 100% outcome and excluded from the turning-point ranking.
