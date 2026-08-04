# Data-quality report

## Cutoff snapshot

The reproducible backfill covers the 2024, 2025, and 2026 WNBA seasons through `2026-08-03T08:00:00Z`.

| Check | Result |
|---|---:|
| Completed games discovered | 753 |
| Games published | 739 |
| Games quarantined | 14 |
| Publish rate | 98.1% |
| Normalized events | 291,552 |
| Lineup stints | 21,276 |
| Possessions | 120,514 |
| Bounded score-attribution corrections | 172 (0.14%) |

Corrections absorb small technical-free-throw/event-attribution mismatches of at most three points. They are explicit in `possessions.score_correction` and excluded from analytical marts and modeling.

## Source contract

ESPN scoreboard and summary endpoints provide the automated feed. Each payload retains game ID, source URL, retrieval timestamp, SHA-256, raw body, and validation status. The existing WNBA HTML adapter remains an authoritative schema contract and cross-check because automated direct requests may encounter access controls.

## Publish gates

A game is published only when it satisfies:

- completed status and exactly two teams;
- five box-score starters per team;
- nonempty play actions;
- stable unique event IDs and deterministic canonical order;
- observed scoring consistent with the final box score after bounded corrections;
- valid substitution participants and replayable on-court state;
- exactly five players per team in every published stint;
- positive, ordered stint durations;
- reconstructed player seconds within the configured box-score tolerance;
- game date at or before the model cutoff.

Failures are quarantined with an error message. They are not loaded partially.

## Half-court proxy

A possession is marked half-court at threshold `t` when its terminal scoring attempt, foul, or turnover occurs more than `t` seconds after possession start. The database stores flags for 5, 7, and 9 seconds. The 7-second version is the primary metric.

This proxy does not equal tracking-derived transition classification. Delayed transition possessions and quick half-court actions can be misclassified.

## Known quarantine causes

The 14 quarantined games consist of source-side score discrepancies, malformed substitution events, player-minute reconciliation failures, and rare large attribution mismatches that exceed the bounded correction policy. Keeping them out is preferable to silently fabricating lineup state.

## Reconciliation and idempotence

Game replacement runs inside a database transaction. Reprocessing a game deletes its dependent normalized rows and inserts the validated bundle again, producing the same logical keys. SQL tests cover primary keys, foreign keys, five-player lineup strings, score/minute reconciliation, cutoff compliance, and rerun counts.

## Next data improvements

- Add an authenticated official source if available.
- Store authoritative availability and roster-effective dates.
- Add automated source-to-source score and starter comparisons.
- Revisit quarantined games with source-specific parsing rules rather than lowering global validation thresholds.
- Add shot coordinates only after their completeness and coordinate system are validated.
