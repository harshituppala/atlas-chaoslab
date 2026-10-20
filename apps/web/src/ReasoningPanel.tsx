type Relation = "supported" | "contradicted" | "insufficient";
export type ReasoningReport = {
  scope: string;
  adapter_scope: string;
  summary: {
    cases: number;
    cases_passed: number;
    extraction_coverage: number;
    end_to_end_relation_accuracy: number;
    supported_precision: number | null;
    insufficient_recall: number | null;
    confusion_matrix: Record<Relation, Record<string, number>>;
  };
  results: Array<{
    id: string;
    expected: string;
    predicted: string;
    passed: boolean;
    extracted: boolean;
    relation_correct: boolean;
    citation_integrity?: boolean | null;
    source_scope?: boolean | null;
    evidence_gate?: boolean | null;
    complete_reference?: boolean;
    human_review_pending?: boolean;
    extractive_draft?: boolean;
    error_type?: string;
  }>;
};
const percent = (value: number | null) =>
  value === null ? "Not measured" : `${(value * 100).toFixed(1)}%`;
const predictions = [
  "supported",
  "contradicted",
  "insufficient",
  "omitted",
  "invalid_extraction",
  "invalid",
  "error",
];

export function ReasoningPanel({
  report,
  title = "Factual support evaluation",
}: {
  report: ReasoningReport;
  title?: string;
}) {
  const summary = report.summary;
  return (
    <section className="benchmark-panel recovery-panel">
      <div className="panel-title">
        <h2>{title}</h2>
        <span
          className={
            "badge " +
            (summary.cases_passed === summary.cases
              ? "evidence_found"
              : "conflicting_evidence")
          }
        >
          {summary.cases_passed} / {summary.cases} grounded cases passed
        </span>
      </div>
      <p className="fine">{report.scope}</p>
      <p className="fine">{report.adapter_scope}</p>
      <div className="stats">
        {[
          ["Relation accuracy", summary.end_to_end_relation_accuracy],
          ["Supported precision", summary.supported_precision],
          ["Insufficient recall", summary.insufficient_recall],
          ["Extraction coverage", summary.extraction_coverage],
        ].map(([label, value]) => (
          <div className="stat" key={String(label)}>
            <span>{label}</span>
            <strong>{percent(value as number | null)}</strong>
            <small>On these authored cases</small>
          </div>
        ))}
      </div>
      <p>
        Matching words and valid source offsets do not establish complete
        support. Missing extraction counts as a failure, rather than a
        successful abstention.
      </p>
      <div className="reasoning-table-scroll">
        <table>
          <caption>
            Expected relation by observed prediction · counts, not percentages
          </caption>
          <thead>
            <tr>
              <th scope="col">Expected</th>
              {predictions.map((label) => (
                <th scope="col" key={label}>
                  {label.replaceAll("_", " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(summary.confusion_matrix).map(([expected, row]) => (
              <tr key={expected}>
                <th scope="row">{expected}</th>
                {predictions.map((label) => (
                  <td key={label}>{row[label]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Inspect {summary.cases} labelled cases</summary>
        <table>
          <thead>
            <tr>
              <th>Case</th>
              <th>Expected</th>
              <th>Observed</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {report.results.map((result) => (
              <tr key={result.id}>
                <td>{result.id.replaceAll("-", " ")}</td>
                <td>{result.expected}</td>
                <td>{result.predicted.replaceAll("_", " ")}</td>
                <td>
                  <span
                    className={
                      "badge " +
                      (result.passed
                        ? "evidence_found"
                        : "conflicting_evidence")
                    }
                  >
                    {result.passed ? "Passed" : "Failed"}
                  </span>
                  {result.error_type && <small>{result.error_type}</small>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
