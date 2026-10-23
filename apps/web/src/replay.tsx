import { useState } from "react";
import { createRoot } from "react-dom/client";
import data from "./replay-data.json";
import { Dialog } from "./Dialog";
import "./replay.css";

type Recording = (typeof data.recordings)[number];
type Citation = Recording["assessments"][number]["requirement"]["source"];
const labels = {
  evidence_found: "Evidence located",
  conflicting_evidence: "Possible conflict",
  missing_evidence: "Evidence gap",
};
const slice = (text: string, start: number, end?: number) =>
  Array.from(text).slice(start, end).join("");

function Replay() {
  const [recordingId, setRecordingId] = useState(data.recordings[0].id);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [citation, setCitation] = useState<Citation | null>(null);
  const [tab, setTab] = useState("register");
  const recording = data.recordings.find((r) => r.id === recordingId)!;
  const assessments = recording.assessments.filter(
    (a) =>
      (filter === "all" || a.status === filter) &&
      a.requirement.text.toLowerCase().includes(query.toLowerCase()),
  );
  const document =
    citation && recording.documents.find((d) => d.id === citation.document_id);
  return (
    <>
      <a className="skip" href="#content">
        Skip to content
      </a>
      <header>
        <a className="brand" href="#content">
          <span className="brand-icon">A</span> ATLAS{" "}
          <small>/ EVIDENCE ROOM</small>
        </a>
        <span className="recorded">
          <i /> RECORDED SYNTHETIC DEMO
        </span>
      </header>
      <main id="content">
        <section className="intro">
          <div>
            <p className="eyebrow">RECORDED REVIEW</p>
            <h1>Recorded requirement reviews</h1>
            <p className="lede">
              Compare each requirement with the capability record. Open a
              citation to read the original text, including the gaps and
              contradictions in this fictional case.
            </p>
          </div>
          <aside className="scope">
            <span className="eyebrow">ABOUT THIS RECORD</span>
            <h2>Fictional documents, saved results.</h2>
            <p>
              This viewer replays synthetic results. It does not run a model,
              accept uploads, or approve requirements.
            </p>
            <p className="scope-foot">
              Source excerpts and evaluation results are recorded separately.
            </p>
          </aside>
        </section>
        <div className="workspace-bar">
          <div>
            <label htmlFor="recording">Recording</label>
            <select
              id="recording"
              value={recordingId}
              onChange={(e) => {
                setRecordingId(e.target.value);
                setQuery("");
                setFilter("all");
              }}
            >
              {data.recordings.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title}
                </option>
              ))}
            </select>
          </div>
          <div className="identity">
            <span>{recording.pipeline_version}</span>
            <small>
              Saved {new Date(recording.recorded_at).toISOString().slice(0, 10)}{" "}
              · {recording.provider}
            </small>
          </div>
        </div>
        <section className="stats" aria-label="Recording totals">
          <div>
            <strong>
              {recording.assessments.length.toString().padStart(2, "0")}
            </strong>
            <span>Extracted requirements</span>
          </div>
          <div>
            <strong>
              {recording.assessments
                .reduce((n, a) => n + a.evidence.length, 0)
                .toString()
                .padStart(2, "0")}
            </strong>
            <span>Inspectable evidence citations</span>
          </div>
          <div>
            <strong>
              {recording.assessments
                .filter((a) => a.status !== "evidence_found")
                .length.toString()
                .padStart(2, "0")}
            </strong>
            <span>Gaps or possible conflicts</span>
          </div>
          <div>
            <strong>Pending</strong>
            <span>Human review · all requirements</span>
          </div>
        </section>
        <nav className="tabs" aria-label="Demo sections">
          {[
            ["register", "Requirements"],
            ["evaluation", "CHAOSLAB results"],
            ["provenance", "Recording provenance"],
          ].map(([id, label]) => (
            <button
              key={id}
              aria-current={tab === id ? "page" : undefined}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        {tab === "register" && (
          <section aria-label="Requirements register">
            <div className="section-heading">
              <div>
                <p className="eyebrow">01 / REQUIREMENT REGISTER</p>
                <h2>From obligation to evidence</h2>
              </div>
              <span className="note">
                Provisional assessments · never compliance decisions
              </span>
            </div>
            <div className="filters">
              <label>
                Find a requirement
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Try Canada, SSO, recovery…"
                />
              </label>
              <label>
                Assessment
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="all">All assessments</option>
                  {Object.entries(labels).map(([v, l]) => (
                    <option value={v} key={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </label>
              <p aria-live="polite">{assessments.length} shown</p>
            </div>
            <div className="cards">
              {assessments.map((a, index) => (
                <article key={a.requirement.id} className="requirement">
                  <div className="requirement-top">
                    <span className="number">
                      {(index + 1).toString().padStart(2, "0")}
                    </span>
                    <span className={`status ${a.status}`}>
                      {labels[a.status as keyof typeof labels]}
                    </span>
                    <span className="pending">Pending human review</span>
                  </div>
                  <h3>{a.requirement.text}</h3>
                  <button
                    className="text-button"
                    onClick={() => setCitation(a.requirement.source)}
                  >
                    Inspect obligation source ↗
                  </button>
                  <div className="evidence">
                    <span className="eyebrow">RETRIEVED EVIDENCE</span>
                    {a.evidence.length ? (
                      a.evidence.map((c, i) => (
                        <button
                          className="quote"
                          key={i}
                          onClick={() => setCitation(c)}
                        >
                          <span>“{c.quote}”</span>
                          <small>
                            {
                              recording.documents.find(
                                (d) => d.id === c.document_id,
                              )?.title
                            }{" "}
                            · Inspect source ↗
                          </small>
                        </button>
                      ))
                    ) : (
                      <p>
                        No evidence located. A reviewer must obtain evidence
                        before responding.
                      </p>
                    )}
                  </div>
                  <details>
                    <summary>View extractive response draft</summary>
                    <pre>{a.draft}</pre>
                  </details>
                </article>
              ))}
            </div>
            {!assessments.length && (
              <p className="empty">
                No matching requirements. Try a different search or assessment.
              </p>
            )}
          </section>
        )}
        {tab === "evaluation" && (
          <section className="evaluation">
            <p className="eyebrow">02 / INDEPENDENT EVALUATION</p>
            <h2>The failures stay in the report.</h2>
            <p className="lede">
              Small authored fixtures expose specific weaknesses. These recorded
              results are neither production accuracy nor a live-model attack
              success rate.
            </p>
            <div className="benchmark-grid">
              {data.benchmarks.map((b) => (
                <article key={b.name}>
                  <h3>{b.name}</h3>
                  <p className="score">
                    {b.passed}
                    <small> / {b.total} strict case contracts passed</small>
                  </p>
                  <p>{b.scope}</p>
                  <ul>
                    {Object.entries(b.cases).map(([id, passed]) => (
                      <li key={id}>
                        <code>{id}</code>
                        <span className={passed ? "pass" : "fail"}>
                          {passed ? "PASS" : "FAIL"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
            <p className="callout">
              Valid source spans establish citation integrity. They do not
              establish that the selected evidence supports the requirement. The
              hostile-evidence baseline cited all six hostile appendices; paired
              regressions alone do not prove successful prompt injection.
            </p>
          </section>
        )}
        {tab === "provenance" && (
          <section className="provenance">
            <p className="eyebrow">03 / RECORDING PROVENANCE</p>
            <h2>Know what was actually executed.</h2>
            <div className="benchmark-grid">
              <article>
                <h3>Municipal RFP recording</h3>
                <p>
                  The deterministic extractive baseline was executed during demo
                  preparation. Its saved output was checked against the original
                  fixture, exact Unicode spans, document hashes, extractive
                  drafts, and pending review state.
                </p>
                <p>
                  Finding an excerpt does not verify support or legal
                  compliance.
                </p>
              </article>
              <article>
                <h3>Historical Bedrock recording</h3>
                <p>{data.model_evidence.scope}</p>
                <p>
                  Model: <code>{data.model_evidence.model_id}</code>
                </p>
                <p>
                  Region: {data.model_evidence.region} · Estimated model cost:
                  USD {data.model_evidence.estimated_model_cost_usd} (not an
                  invoice).
                </p>
                <p>
                  No new provider call is made by this viewer. One functional
                  fixture does not establish model accuracy.
                </p>
              </article>
            </div>
            <h3>Input artifact hashes</h3>
            <p>
              These hashes identify the bundled source artifacts; they are not
              signed attestations.
            </p>
            <dl className="hashes">
              {Object.entries(data.input_sha256).map(([path, hash]) => (
                <div key={path}>
                  <dt>{path}</dt>
                  <dd>
                    <code>{hash}</code>
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        )}
        <footer>
          <span>ATLAS × CHAOSLAB</span>
          <p>
            Recorded evidence. Visible limitations. Human judgment required.
          </p>
        </footer>
      </main>
      {citation && document && (
        <Dialog
          name="Citation source"
          className="source-dialog"
          onClose={() => setCitation(null)}
        >
          <div className="dialog-heading">
            <div>
              <p className="eyebrow">IMMUTABLE SOURCE EXCERPT</p>
              <h2>{document.title}</h2>
            </div>
            <button onClick={() => setCitation(null)}>Close</button>
          </div>
          <p>
            Unicode characters {citation.start}–{citation.end} · end exclusive
          </p>
          <pre className="source-text">
            {slice(document.text, 0, citation.start)}
            <mark>{slice(document.text, citation.start, citation.end)}</mark>
            {slice(document.text, citation.end)}
          </pre>
          <p className="digest">
            SHA-256 <code>{citation.digest}</code>
          </p>
          <p>
            Source identity and exact offsets were validated when this replay
            was prepared. Support remains a human assessment.
          </p>
        </Dialog>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(<Replay />);
