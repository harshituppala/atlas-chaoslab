export type RetrievalReport = {
  unique_queries: number;
  k: number;
  scope: string;
  model_id: string;
  cache_reused?: boolean;
  corpus_build_ms?: number;
  cache_restore_ms?: number;
  summary: Record<
    string,
    { recall_at_k: number; mrr: number; latency_median_ms: number }
  >;
};

export function RetrievalPanel({
  report,
  persistent = false,
}: {
  report: RetrievalReport;
  persistent?: boolean;
}) {
  return (
    <section className="benchmark-panel recovery-panel">
      <div className="panel-title">
        <h2>{persistent ? "Persistent retrieval" : "Retrieval comparison"}</h2>
        <span className="badge neutral">
          {report.unique_queries}{" "}
          {persistent
            ? "shared fixtures · PostgreSQL"
            : "authored queries · local CPU"}
        </span>
      </div>
      <p className="fine">{report.scope}</p>
      <table>
        <thead>
          <tr>
            <th>Method</th>
            <th>Recall @{report.k}</th>
            <th>Mean reciprocal rank</th>
            <th>Median query time</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(report.summary).map(([method, row]) => (
            <tr key={method}>
              <td>{method}</td>
              <td>{(row.recall_at_k * 100).toFixed(1)}%</td>
              <td>{row.mrr.toFixed(3)}</td>
              <td>{row.latency_median_ms.toFixed(2)} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
      {persistent && (
        <p className="fine">
          Cache {report.cache_reused ? "reused" : "not reused"} · Source corpus
          build {report.corpus_build_ms?.toFixed(2)} ms · Restore{" "}
          {report.cache_restore_ms?.toFixed(2)} ms. Same fixture set; this does
          not add independent quality cases.
        </p>
      )}
      <p className="fine">
        Encoder: {report.model_id}. Retrieval quality is measured separately
        from extraction and answer faithfulness. These short positive fixtures
        do not establish real-world accuracy.
      </p>
    </section>
  );
}
