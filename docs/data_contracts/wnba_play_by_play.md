# Official WNBA play-by-play source contract

## Pilot game

- Game ID: `1022600195`
- Matchup: Washington Mystics at Golden State Valkyries
- Date: July 20, 2026
- Official final score: Washington 90, Golden State 82
- Source URL: `https://www.wnba.com/game/was-vs-gsv-1022600195/play-by-play`
- Embedded data path: `props.pageProps.playByPlay`
- Reported source system: `hanaV3`

## Grain

One record represents one action recorded in one WNBA game.

## Identity and ordering

- Candidate key: `(game_id, action_id)`
- `action_id` must be unique within a game.
- `action_id` must be strictly increasing in source order.
- `action_number` is retained as source metadata but is not a key.

## Pilot observations

- Action count: 399
- Periods present: 1, 2, 3, and 4
- Final source score: away 90, home 82
- `action_number` contains duplicate values.

These observations describe the pilot game. They are not assumed to be universal rules for every WNBA game.

## Initial quality gate

The game must be quarantined rather than published if:

- the requested game ID differs from the returned game ID;
- the action collection is missing or empty;
- `(game_id, action_id)` is not unique;
- action IDs are not strictly increasing;
- the final play-by-play score does not reconcile with the official result.
