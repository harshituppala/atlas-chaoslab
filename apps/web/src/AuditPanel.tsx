import type { Assessment } from "./workbench";

type Props = {
  audit: Array<Record<string, unknown>>;
  items: Assessment[];
};

export function AuditPanel({ audit, items }: Props) {
  return (
    <section className="benchmark-panel">
      <h2>Review history</h2>
      {audit.map((event) => {
        const action = String(event.action);
        const label =
          (
            {
              "analysis.created": "Analysis created",
              "review.approved": "Evidence review approved",
              "review.rejected": "Evidence review rejected",
              "review.pending": "Review returned to pending",
            } as Record<string, string>
          )[action] ?? "Recorded event";
        const details =
          event.details &&
          typeof event.details === "object" &&
          !Array.isArray(event.details)
            ? (event.details as Record<string, unknown>)
            : {};
        const subject = items.find(
          (assessment) => assessment.requirement.id === details.requirement_id,
        );
        return (
          <article className="audit-event" key={String(event.id)}>
            <div className="audit-heading">
              <h3>{label}</h3>
              <small>{new Date(String(event.time)).toLocaleString()}</small>
            </div>
            <p className="audit-actor">By {String(event.actor)}</p>
            {subject && (
              <p className="audit-subject">{subject.requirement.text}</p>
            )}
            {typeof details.note === "string" && (
              <blockquote className="audit-note">{details.note}</blockquote>
            )}
            {typeof details.version === "number" && (
              <p className="fine">Saved review version {details.version}</p>
            )}
            <details>
              <summary>Technical details</summary>
              <pre>{JSON.stringify({ action, details }, null, 2)}</pre>
            </details>
          </article>
        );
      })}
      {!audit.length && (
        <p>
          No events loaded. Open an analysis before viewing its audit trail.
        </p>
      )}
    </section>
  );
}
