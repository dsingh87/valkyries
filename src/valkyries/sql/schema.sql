CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    cutoff_at TEXT,
    status TEXT NOT NULL,
    games_discovered INTEGER NOT NULL DEFAULT 0,
    games_published INTEGER NOT NULL DEFAULT 0,
    games_quarantined INTEGER NOT NULL DEFAULT 0,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS raw_payloads (
    game_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    local_path TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    validation_error TEXT
);

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    season INTEGER NOT NULL,
    game_date TEXT NOT NULL,
    home_team_id TEXT NOT NULL,
    home_team_abbreviation TEXT NOT NULL,
    home_score INTEGER NOT NULL,
    away_team_id TEXT NOT NULL,
    away_team_abbreviation TEXT NOT NULL,
    away_score INTEGER NOT NULL,
    source_hash TEXT NOT NULL,
    published_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS athletes (
    game_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    team_id TEXT NOT NULL,
    position TEXT,
    starter INTEGER NOT NULL,
    minutes REAL,
    PRIMARY KEY (game_id, athlete_id),
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE TABLE IF NOT EXISTS events (
    game_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    source_sequence_number INTEGER NOT NULL,
    period INTEGER NOT NULL,
    clock TEXT NOT NULL,
    elapsed_seconds INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    description TEXT NOT NULL,
    team_id TEXT,
    participant_ids TEXT NOT NULL,
    away_score INTEGER NOT NULL,
    home_score INTEGER NOT NULL,
    scoring_play INTEGER NOT NULL,
    shooting_play INTEGER NOT NULL,
    score_value INTEGER NOT NULL,
    PRIMARY KEY (game_id, event_id),
    UNIQUE (game_id, sequence_number),
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE TABLE IF NOT EXISTS lineup_stints (
    stint_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    start_event_id TEXT NOT NULL,
    end_event_id TEXT NOT NULL,
    start_elapsed_seconds INTEGER NOT NULL,
    end_elapsed_seconds INTEGER NOT NULL,
    duration_seconds INTEGER NOT NULL,
    home_team_id TEXT NOT NULL,
    away_team_id TEXT NOT NULL,
    home_lineup TEXT NOT NULL,
    away_lineup TEXT NOT NULL,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE TABLE IF NOT EXISTS possessions (
    possession_id TEXT PRIMARY KEY,
    game_id TEXT NOT NULL,
    possession_number INTEGER NOT NULL,
    period INTEGER NOT NULL,
    offense_team_id TEXT NOT NULL,
    defense_team_id TEXT NOT NULL,
    offense_lineup TEXT NOT NULL,
    defense_lineup TEXT NOT NULL,
    start_elapsed_seconds INTEGER NOT NULL,
    end_elapsed_seconds INTEGER NOT NULL,
    duration_seconds INTEGER NOT NULL,
    points INTEGER NOT NULL,
    score_correction INTEGER NOT NULL,
    margin_before INTEGER NOT NULL,
    is_home_offense INTEGER NOT NULL,
    is_half_court_5 INTEGER NOT NULL,
    is_half_court_7 INTEGER NOT NULL,
    is_half_court_9 INTEGER NOT NULL,
    terminal_action TEXT NOT NULL,
    terminal_event_id TEXT NOT NULL,
    UNIQUE (game_id, possession_number),
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE TABLE IF NOT EXISTS model_runs (
    model_run_id TEXT PRIMARY KEY,
    cutoff_at TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    feature_schema_hash TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    model_run_id TEXT NOT NULL,
    target_game_id TEXT NOT NULL,
    lineup_key TEXT NOT NULL,
    lineup_names TEXT NOT NULL,
    expected_offense_pp100 REAL NOT NULL,
    offense_low REAL NOT NULL,
    offense_high REAL NOT NULL,
    expected_defense_pp100 REAL NOT NULL,
    defense_low REAL NOT NULL,
    defense_high REAL NOT NULL,
    guardrail_probability REAL NOT NULL,
    sample_possessions INTEGER NOT NULL,
    FOREIGN KEY (model_run_id) REFERENCES model_runs(model_run_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    model_run_id TEXT NOT NULL,
    target_game_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    prediction_id TEXT NOT NULL,
    adjustment TEXT NOT NULL,
    evidence TEXT NOT NULL,
    confidence TEXT NOT NULL,
    caveat TEXT NOT NULL,
    UNIQUE (model_run_id, target_game_id, rank),
    FOREIGN KEY (model_run_id) REFERENCES model_runs(model_run_id),
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);

CREATE INDEX IF NOT EXISTS idx_games_date ON games(game_date);
CREATE INDEX IF NOT EXISTS idx_events_game_sequence ON events(game_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_possessions_game ON possessions(game_id, possession_number);
CREATE INDEX IF NOT EXISTS idx_possessions_teams ON possessions(offense_team_id, defense_team_id);
