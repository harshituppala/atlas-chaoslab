import { useState } from "react";
import { ReasoningPanel, type ReasoningReport } from "./ReasoningPanel";

export type LiveReasoningReport = ReasoningReport & {
  planned_cases: number;
  evaluated_cases: number;
  not_run_cases: number;
  dataset_sha256: string;
  live_execution: {
    pipeline_version: string;
    model_id: string;
    estimated_model_cost_usd: string | null;
    validation_failure_counts: Record<string, number>;
    call_status_counts: Record<string, number>;
    limitations: string[];
  };
};
export function LiveReasoningPanel({
  reports,
}: {
  reports: LiveReasoningReport[];
}) {
  const [selected, setSelected] = useState(0);
  const report = reports[selected] ?? reports[0];
  if (!report) return null;
  const live = report.live_execution;
  return (
    <section className="benchmark-panel" aria-label="Recorded model runs">
      <div className="panel-title">
        <h2>Recorded model runs</h2>
        <span className="badge missing_evidence">
          Synthetic development evidence
        </span>
      </div>
      <p>
        Actual Bedrock runs, scored by CHAOSLAB. These results do not activate
        live inference in the workbench. Different case sets and incomplete runs
        are not direct comparisons.
      </p>
      <label htmlFor="live-diagnostic-run">Recorded model run</label>
      <select
        id="live-diagnostic-run"
        value={selected}
        onChange={(event) => setSelected(Number(event.target.value))}
      >
        {reports.map((item, index) => (
          <option
            key={`${item.dataset_sha256}:${item.live_execution.pipeline_version}`}
            value={index}
          >
            {item.live_execution.pipeline_version} · {item.planned_cases}-case
            set · {item.evaluated_cases} attempted
          </option>
        ))}
      </select>
      <div className="stats">
        <div className="stat">
          <span>Passed / attempted</span>
          <strong>
            {report.summary.cases_passed} / {report.evaluated_cases}
          </strong>
          <small>Failures remain in the denominator</small>
        </div>
        <div className="stat">
          <span>Not run</span>
          <strong>{report.not_run_cases}</strong>
          <small>Of {report.planned_cases} planned cases</small>
        </div>
        <div className="stat">
          <span>Estimated model cost</span>
          <strong>
            {live.estimated_model_cost_usd === null
              ? "Unknown"
              : `$${Number(live.estimated_model_cost_usd).toFixed(4)}`}
          </strong>
          <small>USD token estimate · not an invoice</small>
        </div>
      </div>
      {report.not_run_cases > 0 && (
        <p role="note">
          Incomplete run: {report.not_run_cases} cases were not evaluated. The
          displayed pass rate covers attempted cases only.
        </p>
      )}
      {live.estimated_model_cost_usd === null && (
        <p role="note">
          Billing is uncertain for at least one invocation. Unknown cost is not
          zero; its spending reservation is retained.
        </p>
      )}
      <p className="fine">Model: {live.model_id}</p>
      <details>
        <summary>Execution limits and interpretation</summary>
        <ul>
          {live.limitations.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </details>
      <ReasoningPanel
        report={report}
        title="Selected live run: factual support"
      />
    </section>
  );
}
