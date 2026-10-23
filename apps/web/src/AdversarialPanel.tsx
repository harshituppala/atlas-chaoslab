export type AdversarialReport = {
  unique_cases: number;
  case_outcomes?: Record<string, boolean>;
  case_pass_rate: number;
  scope: string;
  results: Array<{
    id: string;
    repeat: number;
    passed: boolean;
    checks?: Record<string, boolean>;
    error_type?: string;
  }>;
};

export function failureDescription(
  results: AdversarialReport["results"],
  id: string,
) {
  return (
    [
      ...new Set(
        results
          .filter((result) => result.id === id)
          .flatMap((result) =>
            result.error_type
              ? [result.error_type]
              : Object.entries(result.checks || {})
                  .filter(([, passed]) => !passed)
                  .map(([name]) => name.replaceAll("_", " ")),
          ),
      ),
    ].join(", ") || "—"
  );
}

export function AdversarialPanel({ report }: { report: AdversarialReport }) {
  const passed = Math.round(report.case_pass_rate * report.unique_cases);
  return (
    <section
      id="hostile-evidence"
      tabIndex={-1}
      className="benchmark-panel recovery-panel"
    >
      <div className="panel-title">
        <h2>Adversarial evidence selection</h2>
        <span
          className={
            "badge " +
            (passed === report.unique_cases
              ? "evidence_found"
              : "conflicting_evidence")
          }
        >
          {passed} / {report.unique_cases} authored probes passed
        </span>
      </div>
      <p className="fine">{report.scope}</p>
      <p>
        These probes distinguish evidence contamination from benign discussion.
        Exact citation offsets alone do not establish trustworthy evidence.
      </p>
      <table>
        <thead>
          <tr>
            <th>Probe</th>
            <th>Observed result</th>
            <th>Failed checks</th>
          </tr>
        </thead>
        <tbody>
          {report.results
            .filter((result) => result.repeat === 0)
            .map((result) => (
              <tr key={result.id}>
                <td>{result.id.replaceAll("-", " ")}</td>
                <td>
                  <span
                    className={
                      "badge " +
                      ((report.case_outcomes?.[result.id] ?? result.passed)
                        ? "evidence_found"
                        : "conflicting_evidence")
                    }
                  >
                    {(report.case_outcomes?.[result.id] ?? result.passed)
                      ? "Passed"
                      : "Failed"}
                  </span>
                </td>
                <td>{failureDescription(report.results, result.id)}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </section>
  );
}
