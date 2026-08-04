"use client";

import { useMemo, useState, type CSSProperties } from "react";
import brief from "../artifacts/aug4_toronto.json";

type View = "brief" | "scenarios" | "model";
type Scenario = (typeof brief.scenarios)[number];
type ScenarioWithScreen = Scenario & {
  guardrail_probability: number;
  meets_guardrail: boolean;
};

const viewLabels: Record<View, string> = {
  brief: "Pregame brief",
  scenarios: "Scenario explorer",
  model: "Model & data",
};

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function normalCdf(value: number) {
  const sign = value < 0 ? -1 : 1;
  const x = Math.abs(value) / Math.sqrt(2);
  const t = 1 / (1 + 0.3275911 * x);
  const erf =
    1 -
    (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t -
      0.284496736) *
      t +
      0.254829592) *
      t *
      Math.exp(-x * x));
  return 0.5 * (1 + sign * erf);
}

function screenScenario(scenario: Scenario, tolerance: number): ScenarioWithScreen {
  if (tolerance === brief.defense_tolerance_pp100) {
    return scenario;
  }
  const [low, high] = scenario.defense_interval_80;
  const standardError = Math.max((high - low) / (2 * 1.2816), 0.01);
  const probability = normalCdf(
    (tolerance - scenario.defensive_change_pp100) / standardError,
  );
  return {
    ...scenario,
    guardrail_probability: Math.round(probability * 10000) / 10000,
    meets_guardrail: probability >= 0.75,
  };
}

function MetricTrack({
  label,
  value,
  interval,
  tone,
}: {
  label: string;
  value: number;
  interval: number[];
  tone: "plum" | "gold";
}) {
  const min = 60;
  const max = 170;
  const point = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  const left = Math.max(
    0,
    Math.min(100, ((interval[0] - min) / (max - min)) * 100),
  );
  const right = Math.max(
    left,
    Math.min(100, ((interval[1] - min) / (max - min)) * 100),
  );
  const style = {
    "--point": `${point}%`,
    "--left": `${left}%`,
    "--width": `${right - left}%`,
  } as CSSProperties;

  return (
    <div className="metric-track">
      <span>{label}</span>
      <div className={`track ${tone}`} style={style} aria-hidden="true">
        <i />
        <b />
      </div>
      <strong>{value.toFixed(1)}</strong>
      <small>
        {interval[0].toFixed(1)}–{interval[1].toFixed(1)}
      </small>
    </div>
  );
}

function Header({ active, setActive }: { active: View; setActive: (view: View) => void }) {
  return (
    <header className="site-header">
      <button className="brand" onClick={() => setActive("brief")} aria-label="Open pregame brief">
        <span className="brand-mark" aria-hidden="true">V</span>
        <span>
          <strong>Matchup Intelligence</strong>
          <small>Golden State vs. Toronto · Aug 4</small>
        </span>
      </button>
      <nav aria-label="Primary navigation">
        {(Object.keys(viewLabels) as View[]).map((view) => (
          <button
            key={view}
            className={active === view ? "active" : ""}
            onClick={() => setActive(view)}
            aria-current={active === view ? "page" : undefined}
          >
            {viewLabels[view]}
          </button>
        ))}
      </nav>
    </header>
  );
}

function PregameBrief({ setActive }: { setActive: (view: View) => void }) {
  const defaultQualifiers = brief.scenarios.filter((scenario) => scenario.meets_guardrail).length;

  return (
    <>
      <section className="hero">
        <div className="hero-orbit orbit-one" aria-hidden="true" />
        <div className="hero-orbit orbit-two" aria-hidden="true" />
        <p className="eyebrow gold">Decision brief · frozen before tipoff</p>
        <h1>
          Find more half-court offense.
          <span>Protect the defensive identity.</span>
        </h1>
        <div className="question-block">
          <span>The basketball question</span>
          <p>{brief.question}</p>
        </div>
        <p className="hero-copy">{brief.direct_answer}</p>
        <div className="hero-meta">
          <span>Toronto Tempo at Golden State</span>
          <span>Aug 4 · 7:00 PM PT</span>
          <span>Defense tolerance +{brief.defense_tolerance_pp100.toFixed(1)} / 100</span>
        </div>
      </section>

      <section className="kpi-grid" aria-label="Decision summary">
        <article className="kpi feature">
          <span>Candidate groups</span>
          <strong>{brief.scenarios.length}</strong>
          <small>Observed, five-player lineups</small>
        </article>
        <article className="kpi">
          <span>Clear guardrail</span>
          <strong>{defaultQualifiers}</strong>
          <small>At least 75% probability</small>
        </article>
        <article className="kpi">
          <span>Champion model</span>
          <strong className="text-value">scikit-learn Tweedie</strong>
          <small>Rolling-origin model gate</small>
        </article>
        <article className="kpi">
          <span>Artifact status</span>
          <strong className="text-value">Frozen</strong>
          <small>Aug 4 · 04:19 UTC</small>
        </article>
      </section>

      <section className="section-heading">
        <div>
          <p className="eyebrow">Recommended tests</p>
          <h2>Three bounded lineup experiments</h2>
        </div>
        <p>
          Ranked by offensive lift only after applying the defensive uncertainty screen.
        </p>
      </section>

      <section className="recommendation-grid">
        {brief.recommendations.map((recommendation) => {
          const scenario = brief.scenarios.find(
            (candidate) => candidate.prediction_id === recommendation.prediction_id,
          );
          if (!scenario) return null;
          return (
            <article className="recommendation" key={recommendation.recommendation_id}>
              <div className="card-topline">
                <span className="rank">0{recommendation.rank}</span>
                <span className={`confidence ${recommendation.confidence}`}>
                  {recommendation.confidence} confidence
                </span>
              </div>
              <h3>{scenario.lineup_names.join(" · ")}</h3>
              <div className="rating-pair">
                <div>
                  <span>Projected offense</span>
                  <strong>{scenario.expected_offense_pp100.toFixed(1)}</strong>
                  <small>{signed(scenario.offensive_lift_pp100)} vs. baseline</small>
                </div>
                <div>
                  <span>Projected defense</span>
                  <strong>{scenario.expected_defense_pp100.toFixed(1)}</strong>
                  <small>
                    {Math.round(scenario.guardrail_probability * 100)}% guardrail probability
                  </small>
                </div>
              </div>
              <p className="adjustment">{recommendation.adjustment}</p>
              <p className="evidence">{recommendation.evidence}</p>
              <details>
                <summary>Decision caveat</summary>
                <p>{recommendation.caveat}</p>
              </details>
            </article>
          );
        })}
      </section>

      <section className="callout">
        <div>
          <p className="eyebrow gold-text">Interpretation boundary</p>
          <h2>Scenario comparison, not a coaching prescription</h2>
        </div>
        <div>
          <p>
            The model estimates how observed player combinations performed after shrinkage and
            matchup adjustment. Public play-by-play cannot isolate coverage, assignment, health,
            or causal rotation effects.
          </p>
          <button className="text-link" onClick={() => setActive("model")}>
            Review model & data caveats <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>
    </>
  );
}

function ScenarioExplorer() {
  const [tolerance, setTolerance] = useState(brief.defense_tolerance_pp100);
  const [showAll, setShowAll] = useState(false);
  const screened = useMemo(() => {
    return brief.scenarios
      .map((scenario) => screenScenario(scenario, tolerance))
      .sort(
        (a, b) =>
          Number(b.meets_guardrail) - Number(a.meets_guardrail) ||
          b.offensive_lift_pp100 - a.offensive_lift_pp100 ||
          b.guardrail_probability - a.guardrail_probability,
      );
  }, [tolerance]);
  const qualifying = screened.filter((scenario) => scenario.meets_guardrail).length;
  const visible = showAll ? screened : screened.slice(0, 10);

  return (
    <>
      <section className="page-intro">
        <p className="eyebrow">Analyst view</p>
        <h1>Lineup scenario explorer</h1>
        <p>
          Change the acceptable defensive downside. The ranking updates from the frozen posterior
          summaries; no model is retrained in the browser.
        </p>
      </section>

      <section className="control-panel">
        <div className="control-copy">
          <div>
            <p className="eyebrow">Defensive screen</p>
            <label htmlFor="tolerance">Maximum defensive degradation</label>
          </div>
          <strong>+{tolerance.toFixed(1)} <small>points / 100</small></strong>
        </div>
        <input
          id="tolerance"
          type="range"
          min="0"
          max="5"
          step="0.5"
          value={tolerance}
          onChange={(event) => setTolerance(Number(event.target.value))}
          aria-describedby="tolerance-help"
        />
        <div className="range-labels" aria-hidden="true">
          <span>0.0 · strict</span><span>5.0 · permissive</span>
        </div>
        <p id="tolerance-help">
          A scenario clears when its probability of staying within this limit is at least 75%.
        </p>
      </section>

      <section aria-live="polite" className="scenario-region">
        <div className="chart-heading">
          <div>
            <p className="eyebrow">Comparison & uncertainty</p>
            <h2>Projected half-court ratings</h2>
          </div>
          <div className="screen-summary">
            <strong>{qualifying}</strong>
            <span>of {brief.scenarios.length} clear the screen</span>
          </div>
        </div>
        <div className="chart-legend">
          <span><i className="legend-offense" /> Offense</span>
          <span><i className="legend-defense" /> Defense</span>
          <span>Point estimate + 80% interval</span>
        </div>
        <div className="scenario-chart">
          {visible.map((scenario, index) => (
            <article
              className={`scenario-row ${scenario.meets_guardrail ? "qualifies" : ""}`}
              key={scenario.prediction_id}
            >
              <div className="scenario-label">
                <span className="row-rank">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong>
                    {scenario.lineup_names
                      .map((name) => name.split(" ").slice(-1)[0])
                      .join(" · ")}
                  </strong>
                  <span>{scenario.sample_possessions} validated possessions</span>
                </div>
              </div>
              <div className="track-group">
                <MetricTrack
                  label="OFF"
                  value={scenario.expected_offense_pp100}
                  interval={scenario.offense_interval_80}
                  tone="plum"
                />
                <MetricTrack
                  label="DEF"
                  value={scenario.expected_defense_pp100}
                  interval={scenario.defense_interval_80}
                  tone="gold"
                />
              </div>
              <div className="probability">
                <span className={`guardrail-state ${scenario.meets_guardrail ? "clear" : "outside"}`}>
                  {scenario.meets_guardrail ? "Clears" : "Outside"}
                </span>
                <strong>{Math.round(scenario.guardrail_probability * 100)}%</strong>
                <span>guardrail probability</span>
              </div>
            </article>
          ))}
        </div>
        <button className="secondary-button" onClick={() => setShowAll((value) => !value)}>
          {showAll ? "Show top 10" : `Show all ${brief.scenarios.length} scenarios`}
        </button>
      </section>
    </>
  );
}

function ModelData() {
  const metrics = brief.model_run.metrics;
  return (
    <>
      <section className="page-intro">
        <p className="eyebrow">Evidence & operations</p>
        <h1>Model card and data lineage</h1>
        <p>
          Every displayed estimate is tied to an immutable cutoff, source hash, feature schema,
          and model run.
        </p>
      </section>

      <section className="model-grid">
        <article className="panel wide benchmark">
          <div className="panel-heading">
            <div><p className="eyebrow">Rolling-origin holdout</p><h2>Benchmark results</h2></div>
            <span className="champion-badge">Champion · scikit-learn Tweedie</span>
          </div>
          <div className="metrics-scroll">
            <table>
              <thead><tr><th>Model</th><th>Poss. MAE</th><th>RMSE</th><th>Game rating MAE</th><th>Calibration</th></tr></thead>
              <tbody>
                <tr><th>scikit-learn Tweedie</th><td>{metrics.baseline_mae.toFixed(3)}</td><td>{metrics.baseline_rmse.toFixed(3)}</td><td>{metrics.baseline_game_rating_mae.toFixed(1)}</td><td>{metrics.baseline_calibration_error.toFixed(3)}</td></tr>
                <tr><th>XGBoost</th><td>{metrics.xgboost_mae.toFixed(3)}</td><td>{metrics.xgboost_rmse.toFixed(3)}</td><td>{metrics.xgboost_game_rating_mae.toFixed(1)}</td><td>{metrics.xgboost_calibration_error.toFixed(3)}</td></tr>
              </tbody>
            </table>
          </div>
          <p className="method-note">
            XGBoost is promoted only with at least 1% MAE improvement and no material calibration
            regression. It did not clear that gate.
          </p>
        </article>

        <article className="panel stat-panel">
          <p className="eyebrow">Sparse lineups</p>
          <h2>PyMC uncertainty</h2>
          <div className="big-number">
            {(metrics.pymc_interval_coverage_80 * 100).toFixed(1)}<span>%</span>
          </div>
          <p>Observed coverage of nominal 80% posterior-predictive intervals on holdout aggregates.</p>
        </article>
        <article className="panel stat-panel">
          <p className="eyebrow">Leakage control</p>
          <h2>As-of contract</h2>
          <div className="big-number date">Aug 3</div>
          <p>All games, features, and rolling windows stop at 08:00 UTC.</p>
        </article>
      </section>

      <section className="lineage panel wide">
        <p className="eyebrow">Source to decision</p>
        <h2>Reproducible lineage</h2>
        <ol>
          <li><span>01</span><strong>ESPN game summaries</strong><small>Immutable JSON, URL, retrieval timestamp, SHA-256</small></li>
          <li><span>02</span><strong>Validated events</strong><small>Unique ordering, final score, starters, substitutions</small></li>
          <li><span>03</span><strong>SQL marts</strong><small>Possessions, lineup stints, rolling pregame features</small></li>
          <li><span>04</span><strong>Model registry</strong><small>{brief.model_run.data_hash.slice(0, 12)}… data · {brief.model_run.feature_schema_hash.slice(0, 12)}… schema</small></li>
          <li><span>05</span><strong>Frozen brief</strong><small>Aug 4, 2026 · 04:19 UTC</small></li>
        </ol>
      </section>

      <section className="caveats panel wide">
        <div className="section-heading compact">
          <div><p className="eyebrow">Required caveats</p><h2>What this system does not know</h2></div>
          <span className="caveat-count">{brief.caveats.length} limitations carried into every decision</span>
        </div>
        <ul>
          {brief.caveats.map((caveat, index) => (
            <li key={caveat}><span>{String(index + 1).padStart(2, "0")}</span><p>{caveat}</p></li>
          ))}
        </ul>
      </section>
    </>
  );
}

export default function Home() {
  const [active, setActive] = useState<View>("brief");
  return (
    <div className="app-shell">
      <Header active={active} setActive={setActive} />
      <main>
        {active === "brief" && <PregameBrief setActive={setActive} />}
        {active === "scenarios" && <ScenarioExplorer />}
        {active === "model" && <ModelData />}
      </main>
      <footer>
        <span>Frozen before tipoff · no postgame rewriting</span>
        <span>Model run <code>{brief.model_run.model_run_id}</code></span>
      </footer>
    </div>
  );
}
