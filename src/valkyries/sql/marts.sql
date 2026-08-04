DROP VIEW IF EXISTS team_game_features;
CREATE VIEW team_game_features AS
WITH team_games AS (
    SELECT game_id, home_team_id AS team_id FROM games
    UNION ALL
    SELECT game_id, away_team_id AS team_id FROM games
),
offense AS (
    SELECT
        game_id,
        offense_team_id AS team_id,
        COUNT(*) AS possessions_for,
        SUM(points) AS points_for,
        SUM(is_half_court_5) AS half_court_possessions_5,
        SUM(CASE WHEN is_half_court_5 = 1 THEN points ELSE 0 END) AS half_court_points_5,
        SUM(is_half_court_7) AS half_court_possessions_7,
        SUM(CASE WHEN is_half_court_7 = 1 THEN points ELSE 0 END) AS half_court_points_7,
        SUM(is_half_court_9) AS half_court_possessions_9,
        SUM(CASE WHEN is_half_court_9 = 1 THEN points ELSE 0 END) AS half_court_points_9,
        SUM(CASE WHEN LOWER(terminal_action) LIKE '%turnover%' THEN 1 ELSE 0 END) AS turnovers
    FROM possessions
    WHERE score_correction = 0
    GROUP BY game_id, offense_team_id
),
defense AS (
    SELECT
        game_id,
        defense_team_id AS team_id,
        COUNT(*) AS possessions_against,
        SUM(points) AS points_against,
        SUM(is_half_court_7) AS half_court_possessions_against,
        SUM(CASE WHEN is_half_court_7 = 1 THEN points ELSE 0 END) AS half_court_points_against
    FROM possessions
    WHERE score_correction = 0
    GROUP BY game_id, defense_team_id
)
SELECT
    tg.game_id,
    tg.team_id,
    g.game_date,
    CASE WHEN g.home_team_id = tg.team_id THEN 1 ELSE 0 END AS is_home,
    o.possessions_for,
    o.points_for,
    o.half_court_possessions_5,
    o.half_court_points_5,
    o.half_court_possessions_7,
    o.half_court_points_7,
    o.half_court_possessions_9,
    o.half_court_points_9,
    o.turnovers,
    d.possessions_against,
    d.points_against,
    d.half_court_possessions_against,
    d.half_court_points_against,
    100.0 * o.half_court_points_7 / NULLIF(o.half_court_possessions_7, 0) AS half_court_off_rating,
    100.0 * d.half_court_points_against / NULLIF(d.half_court_possessions_against, 0) AS half_court_def_rating
FROM team_games tg
JOIN games g ON g.game_id = tg.game_id
JOIN offense o ON o.game_id = tg.game_id AND o.team_id = tg.team_id
JOIN defense d ON d.game_id = tg.game_id AND d.team_id = tg.team_id;

DROP VIEW IF EXISTS lineup_features;
CREATE VIEW lineup_features AS
WITH lineup_keys AS (
    SELECT offense_team_id AS team_id, offense_lineup AS lineup_key FROM possessions
    UNION
    SELECT defense_team_id AS team_id, defense_lineup AS lineup_key FROM possessions
),
offense AS (
    SELECT
        offense_team_id AS team_id,
        offense_lineup AS lineup_key,
        COUNT(*) AS possessions_for,
        SUM(points) AS points_for,
        SUM(CASE WHEN is_half_court_7 = 1 THEN 1 ELSE 0 END) AS half_court_possessions_for,
        SUM(CASE WHEN is_half_court_7 = 1 THEN points ELSE 0 END) AS half_court_points_for
    FROM possessions
    WHERE score_correction = 0
    GROUP BY offense_team_id, offense_lineup
),
defense AS (
    SELECT
        defense_team_id AS team_id,
        defense_lineup AS lineup_key,
        COUNT(*) AS possessions_against,
        SUM(points) AS points_against,
        SUM(CASE WHEN is_half_court_7 = 1 THEN 1 ELSE 0 END) AS half_court_possessions_against,
        SUM(CASE WHEN is_half_court_7 = 1 THEN points ELSE 0 END) AS half_court_points_against
    FROM possessions
    WHERE score_correction = 0
    GROUP BY defense_team_id, defense_lineup
)
SELECT
    lk.team_id,
    lk.lineup_key,
    COALESCE(o.possessions_for, 0) AS possessions_for,
    COALESCE(o.points_for, 0) AS points_for,
    COALESCE(o.half_court_possessions_for, 0) AS half_court_possessions_for,
    COALESCE(o.half_court_points_for, 0) AS half_court_points_for,
    COALESCE(d.possessions_against, 0) AS possessions_against,
    COALESCE(d.points_against, 0) AS points_against,
    COALESCE(d.half_court_possessions_against, 0) AS half_court_possessions_against,
    COALESCE(d.half_court_points_against, 0) AS half_court_points_against,
    100.0 * COALESCE(o.half_court_points_for, 0) / NULLIF(o.half_court_possessions_for, 0) AS half_court_off_rating,
    100.0 * COALESCE(d.half_court_points_against, 0) / NULLIF(d.half_court_possessions_against, 0) AS half_court_def_rating
FROM lineup_keys lk
LEFT JOIN offense o ON o.team_id = lk.team_id AND o.lineup_key = lk.lineup_key
LEFT JOIN defense d ON d.team_id = lk.team_id AND d.lineup_key = lk.lineup_key;

DROP VIEW IF EXISTS pregame_matchups;
CREATE VIEW pregame_matchups AS
SELECT
    game_id,
    team_id,
    game_date,
    is_home,
    AVG(half_court_off_rating) OVER (
        PARTITION BY team_id ORDER BY game_date
        ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
    ) AS rolling_half_court_off_rating,
    AVG(half_court_def_rating) OVER (
        PARTITION BY team_id ORDER BY game_date
        ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
    ) AS rolling_half_court_def_rating,
    AVG(turnovers) OVER (
        PARTITION BY team_id ORDER BY game_date
        ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
    ) AS rolling_turnovers,
    CAST(
        julianday(game_date) - julianday(
            LAG(game_date) OVER (PARTITION BY team_id ORDER BY game_date)
        ) AS INTEGER
    ) AS rest_days
FROM team_game_features;
