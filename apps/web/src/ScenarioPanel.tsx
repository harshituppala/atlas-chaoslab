export type ScenarioReport = {
  scope: string;
  dataset_sha256: string;
  evaluated_scenarios: number;
  not_run_scenarios: number;
  scenarios_passed: number;
  requirements_evaluated: number;
  requirements_passed: number;
  results: Array<{
    id: string;
    passed: boolean;
    unexpected_extractions: number;
    requirements: Array<{
      expected: string;
      predicted: string;
      passed: boolean;
      evidence_record_coverage?: boolean;
    }>;
  }>;
  execution?: {
    pipeline_version: string | null;
    estimated_model_cost_usd: string | null;
    limitations: string;
  };
};
export function ScenarioPanel({
  baseline,
  live,
}: {
  baseline?: ScenarioReport;
  live?: ScenarioReport;
}) {
  if (!baseline && !live) return null;
  const sameCases =
    !baseline || !live || baseline.dataset_sha256 === live.dataset_sha256;
  return (
    <section
      id="scenario-comparison"
      tabIndex={-1}
      className="benchmark-panel"
      aria-label="Complete review scenarios"
    >
      <h2>Complete review scenarios</h2>
      <p>
        Multiple obligations and evidence records, including split support and
        historical distractors. Each obligation must pass extraction, relation,
        source coverage and human-review gates. These are small authored
        synthetic diagnostics.
      </p>
      {!sameCases && (
        <p role="note">
          Different dataset versions: these runs cannot be directly compared.
        </p>
      )}
      <table>
        <caption>Actual executions · no inferred production accuracy</caption>
        <thead>
          <tr>
            <th>Run</th>
            <th>Obligations passed</th>
            <th>Complete scenarios passed</th>
            <th>Not run</th>
            <th>Estimated model cost</th>
          </tr>
        </thead>
        <tbody>
          {(
            [
              ["Extractive baseline", baseline],
              [live?.execution?.pipeline_version ?? "Model run", live],
            ] as const
          ).map(
            ([label, report]) =>
              report && (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  <td>
                    {report.requirements_passed} /{" "}
                    {report.requirements_evaluated}
                  </td>
                  <td>
                    {report.scenarios_passed} / {report.evaluated_scenarios}
                  </td>
                  <td>{report.not_run_scenarios}</td>
                  <td>
                    {report.execution
                      ? report.execution.estimated_model_cost_usd === null
                        ? "Unknown"
                        : `US$${Number(report.execution.estimated_model_cost_usd).toFixed(4)}`
                      : "No model calls"}
                  </td>
                </tr>
              ),
          )}
        </tbody>
      </table>
      <p className="fine">
        Token cost estimates are not invoices. Complete scenarios require every
        obligation to pass, with no unexpected extractions.
      </p>
      {live && (
        <details>
          <summary>Inspect recorded model scenarios</summary>
          <p className="fine">{live.scope}</p>
          <p className="fine">{live.execution?.limitations}</p>
          {live.results.map((result) => (
            <div key={result.id}>
              <h3>{result.id.replaceAll("-", " ")}</h3>
              <p>
                {result.passed ? "Passed" : "Failed"} ·{" "}
                {result.unexpected_extractions} unexpected extractions
              </p>
              <table>
                <thead>
                  <tr>
                    <th>Obligation</th>
                    <th>Expected relation</th>
                    <th>Observed</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {result.requirements.map((row, index) => (
                    <tr key={index}>
                      <th scope="row">{index + 1}</th>
                      <td>{row.expected}</td>
                      <td>{row.predicted}</td>
                      <td>{row.passed ? "Passed" : "Failed"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </details>
      )}
    </section>
  );
}
