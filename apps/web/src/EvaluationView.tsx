import {
  LiveReasoningPanel,
  type LiveReasoningReport,
} from "./LiveReasoningPanel";
import { ScenarioPanel, type ScenarioReport } from "./ScenarioPanel";
import { ReasoningPanel, type ReasoningReport } from "./ReasoningPanel";
import {
  AdversarialPanel,
  failureDescription,
  type AdversarialReport,
} from "./AdversarialPanel";
import { RetrievalPanel, type RetrievalReport } from "./RetrievalPanel";

type RecoveryReport = {
  unique_cases: number;
  cases_passed: number;
  scope: string;
  results: Array<{
    id: string;
    passed: boolean;
    latency_ms: number;
    observations: Record<string, unknown>;
  }>;
};
type IngestionReport = {
  unique_cases: number;
  cases_passed: number;
  scope: string;
  results: Array<{
    id: string;
    passed: boolean;
    latency_ms: number;
    checks: Record<string, boolean>;
  }>;
};
type PostgresReport = {
  groups_passed: number;
  server_version: string;
  pgvector_available_version: string;
  scope: string;
  results: Array<{ id: string; passed: boolean; duration_seconds: number }>;
};
export type Benchmark = {
  scenario_baseline?: ScenarioReport;
  scenario_live?: ScenarioReport;
  reasoning?: ReasoningReport;
  live_reasoning?: LiveReasoningReport[];
  case_outcomes?: Record<string, boolean>;
  adversarial?: AdversarialReport;
  latency_scope?: string;
  postgres?: PostgresReport;
  ingestion?: IngestionReport;
  retrieval?: RetrievalReport;
  persistent_retrieval?: RetrievalReport;
  recovery?: RecoveryReport;
  unique_cases: number;
  case_pass_rate: number;
  extraction_precision: number | null;
  extraction_recall: number | null;
  citation_integrity: number | null;
  latency_median_ms: number;
  scope: string;
  results: Array<{
    id: string;
    repeat: number;
    passed: boolean;
    checks: Record<string, boolean>;
    latency_ms: number;
  }>;
};
function percentage(value: number | null) {
  return value === null ? "Not measured" : (value * 100).toFixed(1) + "%";
}

export function EvaluationView({
  benchmark,
  evaluationDetails,
  onDetailsChange,
}: {
  benchmark: Benchmark | null;
  evaluationDetails: boolean;
  onDetailsChange: (open: boolean) => void;
}) {
  return benchmark ? (
    <>
      <section
        className="benchmark-panel evaluation-guide"
        aria-label="Understanding CHAOSLAB"
      >
        <h2>How do we know the review is right?</h2>
        <p>
          CHAOSLAB checks a system’s answers against cases with known
          expectations. It also tests misleading source text and interrupted
          jobs. A correct citation can still accompany a wrong answer, so those
          checks are measured separately.
        </p>
        <p>
          This page shows saved test runs. Opening it does not call a model or
          run a new experiment. Start with the baseline/model comparison, then
          inspect a failure and the recovery checks.
        </p>
        <nav aria-label="Evaluation sections">
          {(benchmark.scenario_baseline || benchmark.scenario_live) && (
            <a href="#scenario-comparison">Compare baseline and model</a>
          )}
          {benchmark.adversarial && (
            <a href="#hostile-evidence" onClick={() => onDetailsChange(true)}>
              Inspect misleading evidence
            </a>
          )}
          {benchmark.recovery && (
            <a href="#workflow-recovery" onClick={() => onDetailsChange(true)}>
              Check interrupted jobs
            </a>
          )}
        </nav>
        <details>
          <summary>What do the measurements mean?</summary>
          <dl>
            <dt>Cases passed</dt>
            <dd>
              Cases that met every authored check. This is a result on this test
              set, not a probability of being right on a new document.
            </dd>
            <dt>Extraction recall</dt>
            <dd>
              How many expected requirements were found. It does not tell you
              whether the assessments were correct.
            </dd>
            <dt>Citation integrity</dt>
            <dd>
              Whether the cited text matches its source location. It does not
              establish that the text supports the answer.
            </dd>
          </dl>
        </details>
      </section>
      <div className="stats">
        {[
          ["Test cases", benchmark.unique_cases],
          ["Cases passed", (benchmark.case_pass_rate * 100).toFixed(1) + "%"],
          ["Extraction recall", percentage(benchmark.extraction_recall)],
          ["Citation integrity", percentage(benchmark.citation_integrity)],
        ].map(([label, value]) => (
          <div className="stat" key={String(label)}>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>Measured synthetic baseline</small>
          </div>
        ))}
      </div>
      <ScenarioPanel
        baseline={benchmark.scenario_baseline}
        live={benchmark.scenario_live}
      />
      {benchmark.live_reasoning && (
        <LiveReasoningPanel reports={benchmark.live_reasoning} />
      )}
      <details
        className="evaluation-details"
        open={evaluationDetails}
        onToggle={(event) => onDetailsChange(event.currentTarget.open)}
      >
        <summary>View failed cases and technical checks</summary>
        <section className="benchmark-panel">
          <h2>Fault & quality scenarios</h2>
          <p className="fine">{benchmark.scope}</p>
          <p className="fine">{benchmark.latency_scope}</p>
          <table>
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Result</th>
                <th>Duration</th>
                <th>Failed checks</th>
              </tr>
            </thead>
            <tbody>
              {benchmark.results
                .filter((r) => r.repeat === 0)
                .map((r) => (
                  <tr key={r.id}>
                    <td>{r.id}</td>
                    <td>
                      <span
                        className={
                          "badge " +
                          ((benchmark.case_outcomes?.[r.id] ?? r.passed)
                            ? "evidence_found"
                            : "conflicting_evidence")
                        }
                      >
                        {(benchmark.case_outcomes?.[r.id] ?? r.passed)
                          ? "Passed"
                          : "Failed"}
                      </span>
                    </td>
                    <td>{r.latency_ms.toFixed(2)} ms</td>
                    <td>{failureDescription(benchmark.results, r.id)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
          <p className="fine">
            Case results require every repetition to pass. Duration shows the
            first repetition; repeated runs do not increase the number of
            independent quality cases.
          </p>
        </section>
        {benchmark.reasoning && <ReasoningPanel report={benchmark.reasoning} />}
        {benchmark.adversarial && (
          <AdversarialPanel report={benchmark.adversarial} />
        )}
        {benchmark.recovery && (
          <section
            id="workflow-recovery"
            tabIndex={-1}
            className="benchmark-panel recovery-panel"
          >
            <div className="panel-title">
              <h2>Workflow recovery</h2>
              <span className="badge evidence_found">
                {benchmark.recovery.cases_passed} /{" "}
                {benchmark.recovery.unique_cases} scenarios passed
              </span>
            </div>
            <p className="fine">{benchmark.recovery.scope}</p>
            <table>
              <thead>
                <tr>
                  <th>Scenario</th>
                  <th>Result</th>
                  <th>Observed outcome</th>
                </tr>
              </thead>
              <tbody>
                {benchmark.recovery.results.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id.replaceAll("_", " ")}</td>
                    <td>
                      <span
                        className={
                          "badge " +
                          (r.passed ? "evidence_found" : "conflicting_evidence")
                        }
                      >
                        {r.passed ? "Passed" : "Failed"}
                      </span>
                    </td>
                    <td>
                      <code>
                        {String(r.observations.status)} ·{" "}
                        {String(r.observations.attempts)} attempts ·{" "}
                        {String(r.observations.results)} saved results
                      </code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="fine">
              These scenarios exercise queue correctness. They do not measure AI
              answer quality.
            </p>
          </section>
        )}
        {benchmark.postgres && (
          <section className="benchmark-panel recovery-panel">
            <div className="panel-title">
              <h2>PostgreSQL integration</h2>
              <span className="badge evidence_found">
                {benchmark.postgres.groups_passed} /{" "}
                {benchmark.postgres.results.length} integration groups passed
              </span>
            </div>
            <p className="fine">
              PostgreSQL {benchmark.postgres.server_version} · pgvector{" "}
              {benchmark.postgres.pgvector_available_version} · Local execution
            </p>
            <p className="fine">{benchmark.postgres.scope}</p>
            <table>
              <thead>
                <tr>
                  <th>Test group</th>
                  <th>Result</th>
                  <th>Duration</th>
                </tr>
              </thead>
              <tbody>
                {benchmark.postgres.results.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id.replace(/^test_/, "").replaceAll("_", " ")}</td>
                    <td>
                      <span
                        className={
                          "badge " +
                          (r.passed ? "evidence_found" : "conflicting_evidence")
                        }
                      >
                        {r.passed ? "Passed" : "Failed"}
                      </span>
                    </td>
                    <td>{r.duration_seconds.toFixed(3)} s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
        {benchmark.ingestion && (
          <section className="benchmark-panel recovery-panel">
            <div className="panel-title">
              <h2>Document ingestion</h2>
              <span className="badge evidence_found">
                {benchmark.ingestion.cases_passed} /{" "}
                {benchmark.ingestion.unique_cases} authored cases passed
              </span>
            </div>
            <p className="fine">{benchmark.ingestion.scope}</p>
            <table>
              <thead>
                <tr>
                  <th>Scenario</th>
                  <th>Result</th>
                  <th>Extraction time</th>
                  <th>Failed checks</th>
                </tr>
              </thead>
              <tbody>
                {benchmark.ingestion.results.map((r) => (
                  <tr key={r.id}>
                    <td>{r.id.replaceAll("-", " ")}</td>
                    <td>
                      <span
                        className={
                          "badge " +
                          (r.passed ? "evidence_found" : "conflicting_evidence")
                        }
                      >
                        {r.passed ? "Passed" : "Failed"}
                      </span>
                    </td>
                    <td>{r.latency_ms.toFixed(2)} ms</td>
                    <td>
                      {Object.entries(r.checks || {})
                        .filter(([, pass]) => !pass)
                        .map(([key]) => key)
                        .join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="fine">
              These cases check text provenance and safe failure, independently
              of AI answer quality.
            </p>
          </section>
        )}
        {benchmark.retrieval && <RetrievalPanel report={benchmark.retrieval} />}
        {benchmark.persistent_retrieval && (
          <RetrievalPanel report={benchmark.persistent_retrieval} persistent />
        )}
      </details>
    </>
  ) : (
    <section className="empty">
      <h2>Benchmark report unavailable</h2>
      <p>
        Connect the workspace and run the CHAOSLAB evaluator to populate this
        view.
      </p>
    </section>
  );
}
