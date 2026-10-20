import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Dialog } from "./Dialog";
import "./lab.css";

type Citation = {
  document_id: string;
  digest: string;
  start: number;
  end: number;
  quote: string;
};
type Finding = {
  requirement: { id: string; text: string; source: Citation };
  status: "evidence_found" | "conflicting_evidence" | "missing_evidence";
  evidence: Citation[];
  review_state: string;
  version: number;
  review_note?: string;
};
type Run = {
  id: string;
  documents: { id: string; title: string; text: string }[];
  assessments: Finding[];
};
type Session = { expires_in_seconds: number };
const labels = {
  evidence_found: "Evidence located",
  conflicting_evidence: "Possible conflict",
  missing_evidence: "Evidence gap",
};
class ApiError extends Error {
  constructor(public status: number) {
    super("Synthetic request failed");
  }
}
async function api<T>(
  path: string,
  method = "GET",
  body?: object,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/lab/${path}`, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    signal,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new ApiError(response.status);
  return response.status === 204 ? (undefined as T) : response.json();
}
const chars = (text: string, start: number, end?: number) =>
  Array.from(text).slice(start, end).join("");

function Lab() {
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(true);
  const [deadline, setDeadline] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [decision, setDecision] = useState("rejected");
  const [note, setNote] = useState("needs_followup");
  const clear = () => {
    setRun(null);
    setDeadline(null);
    setSelected(null);
    setCitation(null);
    setQuery("");
    setFilter("all");
  };
  const failure = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) {
      clear();
      setNotice("Your temporary session ended. Run the sample to start again.");
    } else if (error instanceof ApiError && [429, 503].includes(error.status)) {
      setNotice(
        "The lab is at its temporary capacity or activity limit. Please try again later.",
      );
    } else if (error instanceof ApiError && error.status === 409) {
      setNotice(
        "This session is busy or its review changed. Refresh before trying again.",
      );
    } else {
      setNotice("The request could not complete. Please try again.");
    }
  };
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const session = await api<Session>(
          "session",
          "GET",
          undefined,
          controller.signal,
        );
        setDeadline(Date.now() + session.expires_in_seconds * 1000);
        try {
          setRun(await api<Run>("run", "GET", undefined, controller.signal));
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 404)) throw e;
        }
      } catch (e) {
        if (
          !controller.signal.aborted &&
          !(e instanceof ApiError && e.status === 401)
        )
          failure(e);
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    })();
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (deadline === null) return;
    const timer = window.setTimeout(
      () => {
        clear();
        setNotice(
          "Your temporary session ended. Run the sample to start again.",
        );
      },
      Math.max(0, deadline - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [deadline]);
  useEffect(() => {
    if (!selected) return;
    const panel = document.getElementById("review-panel");
    if (window.matchMedia("(max-width: 760px)").matches)
      panel?.scrollIntoView({ block: "start" });
    panel?.focus({ preventScroll: true });
  }, [selected]);
  const analyze = async () => {
    setBusy(true);
    setNotice("");
    try {
      const session = await api<Session>("session", "POST", {});
      setDeadline(Date.now() + session.expires_in_seconds * 1000);
      setRun(await api<Run>("run", "POST", { case_id: "municipal" }));
      setSelected(null);
    } catch (e) {
      failure(e);
    } finally {
      setBusy(false);
    }
  };
  const end = async () => {
    setBusy(true);
    try {
      await api("session", "DELETE");
      clear();
      setNotice("Session cleared. No review history is retained.");
    } catch (e) {
      failure(e);
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    if (!item) return;
    setBusy(true);
    setNotice("");
    try {
      setRun(
        await api<Run>(
          `reviews/${encodeURIComponent(item.requirement.id)}`,
          "POST",
          { version: item.version, decision, note_code: note },
        ),
      );
      setNotice("Review saved in this temporary session.");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        try {
          setRun(await api<Run>("run"));
          setNotice(
            "Another review changed this requirement. The latest version is loaded; inspect it before saving again.",
          );
        } catch (refreshError) {
          failure(refreshError);
        }
      } else failure(e);
    } finally {
      setBusy(false);
    }
  };
  const item = run?.assessments.find((a) => a.requirement.id === selected);
  const visible =
    run?.assessments.filter(
      (a) =>
        (filter === "all" || a.status === filter) &&
        a.requirement.text.toLowerCase().includes(query.toLowerCase()),
    ) || [];
  const sourceDocument = run?.documents.find(
    (d) => d.id === citation?.document_id,
  );
  return (
    <>
      <a className="skip" href="#content">
        Skip to content
      </a>
      <header className="lab-header">
        <a href="#content" className="brand">
          <b>A</b>
          <span>
            ATLAS<small>REQUIREMENTS INTELLIGENCE</small>
          </span>
        </a>
        <span className="profile">Temporary · synthetic</span>
      </header>
      <main id="content">
        <section className="intro">
          <div>
            <p className="eyebrow">AN INSPECTABLE REVIEW WORKFLOW</p>
            <h1>RFP review lab</h1>
            <p>
              Compare a fictional municipal RFP with its capability register.
              Follow the evidence before making a review decision.
            </p>
          </div>
          <aside>
            <strong>Live extractive baseline</strong>
            <p>
              No uploads or paid inference. Sessions expire within ten minutes
              and reset on restart. This is a practice workspace, not a contract
              assessment.
            </p>
          </aside>
        </section>
        <div className="actions">
          <span>
            {run
              ? `${run.assessments.length} requirements · provisional findings`
              : "Municipal services procurement · fictional sample"}
          </span>
          <div>
            {deadline !== null && (
              <button onClick={() => void end()} disabled={busy}>
                End session
              </button>
            )}
            {!run && (
              <button
                className="primary"
                onClick={() => void analyze()}
                disabled={busy}
              >
                {busy ? "Preparing…" : "Run sample analysis"}
              </button>
            )}
          </div>
        </div>
        <p className="notice" role="status" aria-live="polite">
          {notice || (busy ? "Working on the sample. Please wait." : "")}
        </p>
        {!run ? (
          <section className="empty">
            <span className="eyebrow">START WITH THE DISAGREEMENT</span>
            <h2>Four hours required. Eight hours offered.</h2>
            <p>
              The sample includes a recovery-time mismatch, supporting evidence
              and evidence gaps. Run it to inspect the actual baseline findings
              and practice a review.
            </p>
            <ol>
              <li>Run the sample</li>
              <li>Inspect exact source excerpts</li>
              <li>Record a provisional human decision</li>
            </ol>
          </section>
        ) : (
          <>
            <div className="tools">
              <label>
                Find a requirement
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search the RFP…"
                />
              </label>
              <label>
                Finding
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="all">All findings</option>
                  {Object.entries(labels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <span>{visible.length} shown</span>
            </div>
            <div className="workspace">
              <section aria-label="Requirements register">
                {visible.length === 0 && (
                  <p className="empty-results">No matching requirements.</p>
                )}
                {visible.map((a) => (
                  <article
                    className={`requirement ${selected === a.requirement.id ? "selected" : ""}`}
                    key={a.requirement.id}
                    data-status={a.status}
                    data-review-state={a.review_state}
                  >
                    <div className="finding-line">
                      <span className={`badge ${a.status}`}>
                        {labels[a.status]}
                      </span>
                      <small>
                        {a.review_state === "pending"
                          ? "Awaiting human review"
                          : `Review: ${a.review_state}`}{" "}
                        · v{a.version}
                      </small>
                    </div>
                    <h2>
                      <span>
                        {String(run.assessments.indexOf(a) + 1).padStart(
                          2,
                          "0",
                        )}
                      </span>
                      {a.requirement.text}
                    </h2>
                    <div className="row-actions">
                      <button onClick={() => setCitation(a.requirement.source)}>
                        Inspect obligation source
                      </button>
                      <button
                        className="review-button"
                        aria-label={`Review ${a.requirement.text}`}
                        onClick={() => {
                          setSelected(a.requirement.id);
                          setDecision("rejected");
                          setNote("needs_followup");
                        }}
                        disabled={busy}
                      >
                        Review →
                      </button>
                    </div>
                  </article>
                ))}
              </section>
              <aside
                id="review-panel"
                tabIndex={-1}
                className="review-panel"
                aria-label="Human review"
              >
                <p className="eyebrow">HUMAN REVIEW</p>
                {item ? (
                  <>
                    <h2>{item.requirement.text}</h2>
                    <p>
                      <span className={`badge ${item.status}`}>
                        {labels[item.status]}
                      </span>
                    </p>
                    <h3>Capability evidence</h3>
                    {item.evidence.length ? (
                      item.evidence.map((c, i) => (
                        <button
                          className="evidence"
                          key={i}
                          onClick={() => setCitation(c)}
                        >
                          <q>{c.quote}</q>
                          <small>Inspect capability source ↗</small>
                        </button>
                      ))
                    ) : (
                      <p>
                        No supporting evidence located. A reviewer must obtain
                        evidence before responding.
                      </p>
                    )}
                    <p className="review-state">
                      Current review: <strong>{item.review_state}</strong> ·
                      version {item.version}
                    </p>
                    {item.review_note && (
                      <p className="saved-note">{item.review_note}</p>
                    )}
                    <label>
                      Decision
                      <select
                        value={decision}
                        onChange={(e) => setDecision(e.target.value)}
                        disabled={busy}
                      >
                        <option value="rejected">Request follow-up</option>
                        <option
                          value="approved"
                          disabled={item.status !== "evidence_found"}
                        >
                          Approve evidence
                        </option>
                      </select>
                    </label>
                    <label>
                      Review note
                      <select
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        disabled={busy}
                      >
                        <option value="needs_followup">
                          Further evidence is needed
                        </option>
                        <option value="excerpt_checked">
                          I checked the source excerpt
                        </option>
                      </select>
                    </label>
                    <button
                      className="primary save"
                      onClick={() => void save()}
                      disabled={busy}
                    >
                      Save review
                    </button>
                    <p className="hint">
                      Approval records your judgment of this fictional evidence.
                      It does not certify compliance.
                    </p>
                  </>
                ) : (
                  <>
                    <h2>Inspect, then decide.</h2>
                    <p>
                      Select a requirement to compare its capability evidence
                      and record a review. Every finding starts pending.
                    </p>
                    <div className="review-placeholder">
                      Obligation → evidence → decision
                    </div>
                  </>
                )}
              </aside>
            </div>
          </>
        )}
        <details className="limits">
          <summary>What this lab establishes</summary>
          <p>
            Citations bind excerpts to the supplied source; they do not
            establish factual support. The baseline can miss obligations or
            select misleading evidence. CHAOSLAB preserves known extraction and
            retrieval failures. This limited lab does not provide durable
            storage, managed identity or legal compliance judgments.
          </p>
        </details>
        <footer>
          ATLAS surfaces evidence. People assess it.{" "}
          <span>
            Fictional sources · temporary history · no model API calls
          </span>
        </footer>
      </main>
      {citation && sourceDocument && (
        <Dialog
          name="Source excerpt"
          className="source-dialog"
          onClose={() => setCitation(null)}
        >
          <div className="dialog-heading">
            <div>
              <p className="eyebrow">EXACT SOURCE EXCERPT</p>
              <h2>{sourceDocument.title}</h2>
            </div>
            <button onClick={() => setCitation(null)}>Close</button>
          </div>
          <p className="source-meta">
            Unicode characters {citation.start}–{citation.end} · SHA-256{" "}
            <code>{citation.digest}</code>
          </p>
          <pre>
            {chars(sourceDocument.text, 0, citation.start)}
            <mark>
              {chars(sourceDocument.text, citation.start, citation.end)}
            </mark>
            {chars(sourceDocument.text, citation.end)}
          </pre>
          <p className="hint">
            A valid excerpt shows where text came from. It does not prove the
            requirement is satisfied.
          </p>
        </Dialog>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(<Lab />);
