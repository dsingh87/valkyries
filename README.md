# Valkyries Matchup Intelligence Engine

An end-to-end basketball decision-support system for the Golden State Valkyries. The project updates after every WNBA game, estimates matchup- and lineup-specific outcomes, tests rotation scenarios for upcoming opponents, and produces a concise evidence-grounded scouting brief.

This is deliberately not a generic win predictor, player-ranking exercise, or shot-chart dashboard. Its value is the complete path from unreliable public event data to an evaluated model and a tool a basketball stakeholder could use.

## Current basketball question

As of July 28, 2026, Golden State's statistical identity is unusually clear: the team is playing at the league's slowest pace, with the top defensive rating, the eighth-ranked offense, and the second-best net rating in the recent Basketball Reference snapshot. The current analytical question is therefore:

> Which lineup and matchup adjustments can improve Golden State's half-court offense without degrading the defensive identity that makes the team elite?

The upcoming schedule gives us strong case studies:

- July 29 at Phoenix: first live pregame forecast and subsequent backtest.
- August 2 and August 4 vs. Toronto: a paired-opponent study that measures what changed between Games 1 and 2.
- August 7 at Dallas and August 9 at Los Angeles: a travel/rest and rotation-load stress test.
- August 19 vs. Minnesota and August 24 at Minnesota: contender-level matchup validation.
- August 26 at Connecticut and August 27 at New York: a back-to-back rotation optimization case.

Sources: [official Valkyries 2026 schedule announcement](https://valkyries.wnba.com/news/valkyries-announce-2026-schedule-20260121), [official July 20 recap and next-game note](https://valkyries.wnba.com/news/gameday-recap-20260720), and [2026 team statistical snapshot](https://www.basketball-reference.com/wnba/teams/GSV/2026.html).

## What the finished product does

Given an upcoming game, the system should answer five questions:

1. What possession types and lineup contexts create the opponent's advantages?
2. Which Golden State lineup families project best against those contexts?
3. How uncertain are those estimates, especially for sparse lineup combinations?
4. How do rest, travel, recent workload, and player availability change the recommendation?
5. After the game, what actually happened and which assumptions were wrong?

The output is a two-layer product:

- An analyst view with model diagnostics, uncertainty, data lineage, and scenario controls.
- A two-page basketball brief with three evidence-backed recommendations and explicit caveats.

## System architecture

```text
WNBA schedule + box scores + play-by-play + substitutions + shots
                              |
                    incremental ingestion
                              |
            raw events -> validated possessions -> lineup stints
                              |
       team style marts + player/lineup effects + schedule features
                              |
       possession model + matchup model + rotation optimizer
                              |
       analyst app + generated scouting brief + postgame audit
```

### Data engineering layer

The local-first stack will use Python, SQL, Parquet, DuckDB, and dbt-core. It can later be moved to Postgres or a cloud warehouse without changing the analytical contracts.

Core tables:

- `games`: schedule, venue, result, rest, travel, and opponent.
- `events`: canonical play-by-play events with stable event keys.
- `possessions`: possession boundaries, outcome, context, and sequence features.
- `lineup_stints`: ten players on court, start/end event, possessions, and score margin.
- `shots`: shooter, location/zone when available, shot context, and result.
- `player_game`: minutes, workload proxies, role, availability, and box-score features.
- `team_style_daily`: rolling and opponent-adjusted style estimates as known on each date.

Required quality checks:

- Idempotent reruns and incremental game-level updates.
- Unique game/event keys and monotonic event order.
- Score reconciliation with the official final score.
- Exactly five players per team for valid lineup stints.
- Regulation lineup minutes reconcile to team minutes.
- No future information in a pregame feature row.
- Source freshness and failed-game quarantine rather than silent partial loads.

### Modeling layer

#### 1. Possession outcome model

Estimate expected points for an upcoming possession using only information available before that possession:

- Offensive and defensive lineup components.
- Opponent-adjusted recent form with time decay.
- Shot-creation and possession-sequence proxies.
- Score, quarter, rest, travel, and prior workload.
- Team and player interactions only where the sample supports them.

Start with an interpretable regularized generalized linear model, then compare it with LightGBM or CatBoost. Complexity is earned only if rolling out-of-sample evaluation improves.

#### 2. Dynamic player and lineup impact

Use partial pooling or regularized adjusted plus-minus to estimate offensive and defensive effects while controlling for teammates and opponents. Report intervals, not just point estimates. Sparse lineups inherit information from players, roles, and similar lineup constructions instead of receiving unstable raw plus-minus values.

#### 3. Opponent-style representation

Represent team styles from possession-level features rather than box-score averages. Candidate inputs include transition proxies, early-clock rate, assisted-shot patterns, shot-zone mix, turnover creation, offensive-rebound continuation, foul generation, and lineup size/spacing proxies.

Use PCA/NMF or a small learned embedding to retrieve comparable opponents and historical possessions. This provides matchup evidence when Golden State has little direct history against an expansion team such as Toronto.

#### 4. Rotation scenario optimizer

Use constrained optimization to compare feasible rotation plans:

- Minute floors and ceilings.
- Position/size and ball-handler constraints.
- Maximum continuous stint lengths.
- Rest and recent workload penalties.
- Availability scenarios.
- Robust objective across pessimistic, median, and optimistic model estimates.

The result is a scenario comparison, not a claim that an algorithm should set the coach's rotation.

#### 5. Grounded AI reporting layer

An LLM may translate structured model output and retrieved official game context into a scouting brief. It must:

- Receive only versioned model outputs and approved source excerpts.
- Cite the supporting table or source for every quantitative claim.
- Separate observations, model estimates, and recommendations.
- Refuse unsupported tactical claims that cannot be inferred from public play-by-play.
- Fall back to deterministic templates when grounding checks fail.

The LLM is the interface, not the analytical engine.

## Evaluation contract

All validation is time-aware. Random train/test splits are prohibited.

- Use rolling-origin evaluation: train through date `t`, predict games after `t`.
- Compare against simple rolling team-strength and opponent-adjusted baselines.
- Evaluate possession error, calibration, ranking quality, and interval coverage.
- Evaluate rotation recommendations through historical counterfactual sensitivity, not causal claims.
- Run feature ablations for lineup, rest/travel, and recent-form components.
- Publish failures and prediction revisions after each Valkyries game.
- Freeze a pregame artifact before tipoff so the project cannot rewrite history.

## Project deliverables

1. Reproducible repository with typed Python, SQL models, tests, CI, and one-command updates.
2. Data dictionary and lineage diagram.
3. Model card covering leakage, sparse lineups, uncertainty, drift, and public-data limitations.
4. Analyst application for upcoming-game scenarios.
5. Two-page pregame brief and postgame audit for each featured matchup.
6. Technical article centered on the Toronto two-game adjustment study.
7. Five-minute demo showing ingestion, prediction, scenario analysis, and postgame learning.

## Build sequence

### Phase 1 — trustworthy basketball data

- Ingest 2024-2026 WNBA schedules, box scores, play-by-play, and substitutions.
- Build and validate possession and lineup-stint tables.
- Create as-of-date features and a Phoenix pregame snapshot.

### Phase 2 — first modeling system

- Implement opponent-adjusted possession and lineup baselines.
- Add time-aware evaluation and uncertainty.
- Produce Toronto Game 1 brief, postgame audit, and Game 2 adjustment brief.

### Phase 3 — decision layer

- Add opponent-style retrieval and rotation scenarios.
- Build analyst views for Dallas/Los Angeles schedule stress and Minnesota matchups.
- Add automated data/model monitoring.

### Phase 4 — communication and deployment

- Add the grounded report generator.
- Ship a small deployed app and scheduled update workflow.
- Publish the technical write-up, model card, and case-study briefs.

## Non-goals

- Predicting final scores without a basketball decision attached.
- Claiming play types or defensive coverages that public event data cannot identify.
- Using deep learning solely to make the project sound advanced.
- Treating raw plus-minus as player impact.
- Building a chatbot over box scores.
- Presenting correlation as a causal rotation effect.

## System capabilities

The project brings together the capabilities required for a reliable basketball decision-support system:

- **Data engineering:** ingestion, event modeling, SQL, validation, orchestration, and reproducibility.
- **Applied statistics and ML:** opponent adjustment, partial pooling, sparse-data handling, calibration, and time-aware validation.
- **Decision science:** constrained scenarios and uncertainty-aware recommendations.
- **AI engineering:** retrieval, structured generation, grounding, and evaluation.
- **Basketball communication:** short decision-ready briefs rather than notebook dumps.
