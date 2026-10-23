import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { AuthBoundary, type BrowserAccess } from "./AuthBoundary";
import {
  LiveReasoningPanel,
  type LiveReasoningReport,
} from "./LiveReasoningPanel";
import { ScenarioPanel, type ScenarioReport } from "./ScenarioPanel";
import { Dialog } from "./Dialog";
import { ReasoningPanel, type ReasoningReport } from "./ReasoningPanel";
import {
  AdversarialPanel,
  failureDescription,
  type AdversarialReport,
} from "./AdversarialPanel";
import { RetrievalPanel, type RetrievalReport } from "./RetrievalPanel";

type Citation = {
  document_id: string;
  digest: string;
  start: number;
  end: number;
  quote: string;
};
type Assessment = {
  requirement: { id: string; text: string; category: string; source: Citation };
  status: string;
  evidence: Citation[];
  draft: string;
  review_state: string;
  version: number;
  review_note?: string;
};
type SourceMap = {
  format: "pdf" | "docx";
  raw_sha256: string;
  segments: Array<{
    unit: "page" | "paragraph";
    number: number;
    start: number;
    end: number;
  }>;
  warnings: string[];
};
type Document = {
  id: string;
  title: string;
  text: string;
  kind: "rfp" | "knowledge";
  source_map?: SourceMap | null;
};
function unicodeSlice(text: string, start: number, end?: number) {
  return Array.from(text).slice(start, end).join("");
}
function sourceLocation(document: Document | undefined, citation: Citation) {
  return (
    document?.source_map?.segments
      .filter((s) => s.start < citation.end && s.end > citation.start)
      .map((s) => (s.unit === "page" ? "Page " : "Paragraph ") + s.number)
      .join(" · ") || "Pasted source"
  );
}
type ExecutionOptions = {
  model: {
    enabled: boolean;
    model_id?: string;
    region?: string;
    model_config_sha256?: string;
    maximum_reserved_inference_usd?: string;
  };
};
type Run = {
  provider?: string;
  pipeline_version?: string;
  model_cost_usd?: number | null;
  model_config_sha256?: string | null;
  id: string;
  created: string;
  assessments: Assessment[];
  documents: Document[];
  trace: Array<Record<string, unknown>>;
  limitations: string;
};
type Job = {
  id: string;
  status: string;
  attempts: number;
  max_attempts: number;
  result_id: string | null;
  error_code: string | null;
};
const terminalJobs = new Set(["succeeded", "failed", "cancelled"]);
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
type Benchmark = {
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
const labels: Record<string, string> = {
  evidence_found: "Evidence found",
  conflicting_evidence: "Conflict detected",
  missing_evidence: "Evidence gap",
};

type WorkspaceIdentity = {
  tenant: string;
  actor: string;
  role: "viewer" | "analyst" | "reviewer" | "admin";
  authentication: "local-bearer" | "managed-access-token";
};

function percentage(value: number | null) {
  return value === null ? "Not measured" : (value * 100).toFixed(1) + "%";
}

function App({ access }: { access: BrowserAccess | null }) {
  const lifetime = useRef(new AbortController());
  useEffect(() => {
    lifetime.current = new AbortController();
    return () => lifetime.current.abort();
  }, []);
  function credentials(): HeadersInit {
    return access
      ? { "X-Atlas-CSRF": access.csrf }
      : { Authorization: `Bearer ${token}` };
  }
  const [token, setToken] = useState("");
  const [connected, setConnected] = useState(false);
  const [workspace, setWorkspace] = useState("");
  const [identity, setIdentity] = useState<WorkspaceIdentity | null>(null);
  const canAnalyze = identity !== null && identity.role !== "viewer";
  const canReview = identity?.role === "reviewer" || identity?.role === "admin";
  const [page, setPage] = useState("workbench");
  const [run, setRun] = useState<Run | null>(null);
  const [selected, setSelected] = useState(0);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<
    Array<{ id: string; created: string }>
  >([]);
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null);
  const [audit, setAudit] = useState<Array<Record<string, unknown>>>([]);
  const [compose, setCompose] = useState(false);
  const [executionMode, setExecutionMode] = useState("baseline");
  const [executionOptions, setExecutionOptions] = useState<ExecutionOptions>({
    model: { enabled: false },
  });
  const [rfp, setRfp] = useState("");
  const [knowledge, setKnowledge] = useState("");
  const [uploadedRfp, setUploadedRfp] = useState<Document | null>(null);
  const [uploadedKnowledge, setUploadedKnowledge] = useState<Document | null>(
    null,
  );
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const processing = !!activeJob && !terminalJobs.has(activeJob.status);
  function disconnect() {
    setToken("");
    setWorkspace("");
    setIdentity(null);
    setExecutionMode("baseline");
    setExecutionOptions({ model: { enabled: false } });
    setCompose(false);
    setConnected(false);
    setRun(null);
    setHistory([]);
    setActiveJob(null);
    setUploadedRfp(null);
    setUploadedKnowledge(null);
    setRfp("");
    setKnowledge("");
    setNote("");
    setCitation(null);
    setAudit([]);
    setBenchmark(null);
    setError("");
    setPage("workbench");
  }
  const [note, setNote] = useState("");
  const [citation, setCitation] = useState<Citation | null>(null);
  async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
    const signal = lifetime.current.signal;
    const response = await fetch(path, {
      ...options,
      signal,
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...credentials(),
        ...(workspace ? { "X-Workspace-ID": workspace } : {}),
        ...options.headers,
      },
    });
    if (access && [401, 403].includes(response.status)) {
      access.invalidate();
      throw new Error(
        "Workspace access ended. Sign in again or check your membership.",
      );
    }
    const data = await response.json();
    signal.throwIfAborted();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Request rejected. Check the document format.",
      );
    return data;
  }
  async function task(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  async function receiveJob(job: Job) {
    if (job.status === "succeeded" && job.result_id) {
      setRun(await api("/api/runs/" + job.result_id));
      setHistory(await api("/api/runs"));
      setSelected(0);
    }
    setActiveJob(job);
    setPage("workbench");
  }
  async function connect() {
    await task(async () => {
      const [currentIdentity, runs, jobs, options] = await Promise.all([
        api<WorkspaceIdentity>("/api/me"),
        api<Array<{ id: string; created: string }>>("/api/runs"),
        api<Job[]>("/api/jobs"),
        api<ExecutionOptions>("/api/execution-options"),
      ]);
      setIdentity(currentIdentity);
      setExecutionOptions(options);
      setExecutionMode("baseline");
      setHistory(runs);
      const unfinished = jobs.find((j) => !terminalJobs.has(j.status));
      if (unfinished) setActiveJob(unfinished);
      setConnected(true);
    });
  }
  async function demo() {
    await task(async () => {
      const data = await api<{ rfp: Document; knowledge: Document[] }>(
        "/api/demo",
      );
      await receiveJob(
        await api("/api/jobs", {
          method: "POST",
          headers: { "Idempotency-Key": "demo-v3-municipal-job" },
          body: JSON.stringify(data),
        }),
      );
    });
  }
  async function analyze() {
    await task(async () => {
      const input = {
        execution_mode: executionMode,
        ...(executionMode === "bedrock"
          ? {
              expected_model_config_sha256:
                executionOptions.model.model_config_sha256,
            }
          : {}),
        rfp: uploadedRfp || {
          id: crypto.randomUUID(),
          kind: "rfp",
          title: "Pasted requirements",
          text: rfp,
        },
        knowledge: [
          uploadedKnowledge || {
            id: crypto.randomUUID(),
            kind: "knowledge",
            title: "Capability register",
            text: knowledge,
          },
        ],
      };
      await receiveJob(
        await api("/api/jobs", {
          method: "POST",
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify(input),
        }),
      );
      setCompose(false);
    });
  }
  async function upload(file: File | undefined, kind: "rfp" | "knowledge") {
    if (!file) return;
    await task(async () => {
      const format = file.name.split(".").pop()?.toLowerCase();
      if (!["pdf", "docx"].includes(format || ""))
        throw new Error("Choose a PDF or DOCX file.");
      if (file.size < 1 || file.size > 1000000)
        throw new Error("Files must be smaller than 1 MB.");
      const params = new URLSearchParams({
        format: format!,
        kind,
        title: file.name.slice(0, 200),
      });
      const document = await api<Document>("/api/documents?" + params, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      });
      if (kind === "rfp") {
        setUploadedRfp(document);
        setRfp(document.text);
      } else {
        setUploadedKnowledge(document);
        setKnowledge(document.text);
      }
    });
  }
  async function downloadOriginal(document: Document) {
    await task(async () => {
      const signal = lifetime.current.signal;
      const response = await fetch(
        "/api/documents/" + document.id + "/original",
        {
          signal,
          credentials: "same-origin",
          cache: "no-store",
          headers: {
            ...credentials(),
            ...(workspace ? { "X-Workspace-ID": workspace } : {}),
          },
        },
      );
      if (access && [401, 403].includes(response.status)) access.invalidate();
      if (!response.ok)
        throw new Error("Could not download the original source.");
      const blob = await response.blob();
      signal.throwIfAborted();
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = document.id + "." + document.source_map!.format;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  async function cancelJob() {
    if (!activeJob) return;
    await task(async () => {
      setActiveJob(
        await api(`/api/jobs/${activeJob.id}/cancel`, { method: "POST" }),
      );
    });
  }
  useEffect(() => {
    if (!connected || !activeJob || terminalJobs.has(activeJob.status)) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const identifier = activeJob.id;
    async function poll() {
      try {
        const current = await api<Job>("/api/jobs/" + identifier);
        if (current.status === "succeeded" && current.result_id) {
          const completed = await api<Run>("/api/runs/" + current.result_id);
          const updated =
            await api<Array<{ id: string; created: string }>>("/api/runs");
          if (!stopped) {
            setRun(completed);
            setHistory(updated);
            setSelected(0);
            setActiveJob(current);
            setError("");
          }
        } else if (!stopped) {
          setActiveJob(current);
          if (!terminalJobs.has(current.status)) timer = setTimeout(poll, 1000);
        }
      } catch (e) {
        if (!stopped) {
          setError(
            e instanceof Error
              ? e.message
              : "Could not refresh analysis status",
          );
          timer = setTimeout(poll, 5000);
        }
      }
    }
    timer = setTimeout(poll, 250);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [connected, token, activeJob?.id, activeJob?.status]);
  async function review(decision: string) {
    if (!run || !item) return;
    await task(async () => {
      setRun(
        await api(`/api/runs/${run.id}/reviews/${item.requirement.id}`, {
          method: "POST",
          body: JSON.stringify({ version: item.version, decision, note }),
        }),
      );
      setNote("");
    });
  }
  async function switchPage(value: string) {
    setPage(value);
    if (!connected) return;
    await task(async () => {
      if (value === "benchmarks") setBenchmark(await api("/api/benchmarks"));
      if (value === "audit") {
        const events: Array<Record<string, unknown>> = [];
        if (activeJob)
          events.push(
            ...(await api<Array<Record<string, unknown>>>(
              `/api/jobs/${activeJob.id}/audit`,
            )),
          );
        if (run)
          events.push(
            ...(await api<Array<Record<string, unknown>>>(
              `/api/runs/${run.id}/audit`,
            )),
          );
        setAudit(
          events.sort((a, b) => String(a.time).localeCompare(String(b.time))),
        );
      }
    });
  }
  const items = run?.assessments || [];
  const item = items[selected];
  const visible = items
    .map((value, index) => ({ value, index }))
    .filter(
      ({ value }) =>
        (filter === "all" || value.status === filter) &&
        value.requirement.text.toLowerCase().includes(search.toLowerCase()),
    );
  const counts = (status: string) =>
    items.filter((a) => a.status === status).length;
  const sourceDoc = run?.documents.find((d) => d.id === citation?.document_id);
  return (
    <div className={"shell page-" + page}>
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          aria-label="ATLAS home"
          onClick={() => setPage("workbench")}
        >
          <span className="mark">A</span>
          <span>
            ATLAS<small>REQUIREMENTS REVIEW</small>
          </span>
        </a>
        <div className="workspace">
          <span className="avatar">
            {identity?.tenant.charAt(0).toUpperCase() || "A"}
          </span>
          <div>
            {identity ? identity.tenant + " workspace" : "Workspace"}
            <small>
              {identity
                ? identity.authentication === "local-bearer"
                  ? "Private local access"
                  : "Managed access"
                : "Not connected"}
            </small>
          </div>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav>
          {[
            ["workbench", "Evidence workbench"],
            ["benchmarks", "CHAOSLAB benchmarks"],
            ["audit", "Audit trail"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              aria-current={page === id ? "page" : undefined}
              onClick={() => switchPage(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <p className="nav-label">RECENT ANALYSES</p>
        <div className="history">
          {history.slice(0, 6).map((h, i) => (
            <button
              key={h.id}
              onClick={() =>
                task(async () => {
                  setRun(await api("/api/runs/" + h.id));
                  setSelected(0);
                  setPage("workbench");
                })
              }
            >
              <span>▤</span>
              <div>
                Analysis {history.length - i}
                <small>{new Date(h.created).toLocaleDateString()}</small>
              </div>
            </button>
          ))}
          {!history.length && <small>Your analyses will appear here.</small>}
        </div>
        <div className="sidebar-bottom">
          <span className="dot" />
          {run?.provider === "bedrock"
            ? "Bedrock review"
            : "Extractive baseline"}
          <small>Inspect source excerpts before approval.</small>
        </div>
      </aside>
      <main>
        <header>
          <span>
            Workspace <b>/</b>{" "}
            {page === "workbench"
              ? "Evidence workbench"
              : page === "benchmarks"
                ? "CHAOSLAB"
                : "Audit trail"}
          </span>
          <div className="session-controls">
            <span className="badge neutral">Private workspace</span>
            {identity && (
              <span className="badge neutral">
                {identity.tenant} · {identity.role}
              </span>
            )}
            {(connected || access) && (
              <button
                className="secondary"
                disabled={busy && !access}
                onClick={access ? access.logout : disconnect}
              >
                {access ? "Sign out" : "Disconnect"}
              </button>
            )}
          </div>
        </header>
        <div className="content">
          <div className="heading">
            <div>
              <p className="eyebrow">
                {page === "benchmarks" ? "CHAOSLAB" : "REQUIREMENT RECORDS"}
              </p>
              <h1>
                {page === "workbench"
                  ? "Requirement review"
                  : page === "benchmarks"
                    ? "Evaluation results"
                    : "Audit trail"}
              </h1>
              <p className="subtitle">
                {page === "workbench"
                  ? "Inspect source excerpts and record a review for each requirement."
                  : page === "benchmarks"
                    ? "Recorded test runs, including failed cases and controlled faults."
                    : "Review notes, source references, actors and version history."}
              </p>
            </div>
            {page === "workbench" && (
              <button
                className="primary"
                disabled={!connected || !canAnalyze || busy || processing}
                onClick={() => {
                  setExecutionMode("baseline");
                  setCompose(true);
                }}
              >
                + New analysis
              </button>
            )}
          </div>
          {!connected && (
            <section className="connect">
              <div>
                <h2>
                  {access
                    ? "Open your workspace"
                    : "Connect your local workspace"}
                </h2>
                {access ? (
                  <p>
                    Your sign-in is active. Workspace access is checked by the
                    server.
                  </p>
                ) : (
                  <p>
                    Paste the generated local token from{" "}
                    <code>var/local-credentials.json</code>. Credentials stay in
                    this page’s memory.
                  </p>
                )}
              </div>
              {!access && (
                <label>
                  Workspace token
                  <input
                    aria-label="Workspace token"
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    autoComplete="off"
                  />
                </label>
              )}
              <label>
                Workspace ID (optional)
                <input
                  aria-label="Workspace ID"
                  value={workspace}
                  onChange={(e) => setWorkspace(e.target.value)}
                  maxLength={128}
                  autoComplete="off"
                  placeholder="Select if you belong to several"
                />
              </label>
              <button
                className="primary"
                disabled={(!access && !token) || busy}
                onClick={connect}
              >
                Connect
              </button>
            </section>
          )}
          {error && (
            <div role="alert" className="error">
              {error}
              <button onClick={() => setError("")}>Dismiss</button>
            </div>
          )}
          {busy && (
            <div role="status" className="progress">
              Processing the request…
            </div>
          )}
          {activeJob && (
            <section
              className={"job-banner " + activeJob.status}
              aria-live="polite"
            >
              <div>
                <strong>
                  {processing
                    ? "Analysis in progress"
                    : activeJob.status === "succeeded"
                      ? "Analysis complete"
                      : activeJob.status === "cancelled"
                        ? "Analysis cancelled"
                        : "Analysis needs attention"}
                </strong>
                <p>
                  {activeJob.status === "queued"
                    ? "Queued for processing. You can leave this page and reconnect later."
                    : activeJob.status === "running"
                      ? "Checking requirements and evidence."
                      : activeJob.status === "retry_wait"
                        ? "A temporary failure occurred. The worker will retry automatically."
                        : activeJob.status === "failed"
                          ? "Processing stopped safely. " + activeJob.error_code
                          : activeJob.status === "cancelled"
                            ? "No result will be published by this job."
                            : "The result is saved and ready for review."}
                </p>
              </div>
              {processing ? (
                <button
                  className="secondary"
                  disabled={busy || !canAnalyze}
                  onClick={cancelJob}
                >
                  Cancel analysis
                </button>
              ) : (
                <button
                  className="secondary"
                  onClick={() => setActiveJob(null)}
                >
                  Dismiss
                </button>
              )}
            </section>
          )}
          {page === "workbench" && (
            <>
              <div className="stats">
                {[
                  ["Requirements", items.length, "Extracted from source"],
                  [
                    "Evidence found",
                    counts("evidence_found"),
                    "Human assessment required",
                  ],
                  [
                    "Conflicts",
                    counts("conflicting_evidence"),
                    "Compare with the requirement",
                  ],
                  [
                    "Evidence gaps",
                    counts("missing_evidence"),
                    "Missing supporting excerpts",
                  ],
                ].map(([label, value, sub], i) => (
                  <div className={"stat stat-" + i} key={String(label)}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                    <small>{sub}</small>
                  </div>
                ))}
              </div>
              {!run ? (
                <section className="empty">
                  <h2>Sample municipal RFP</h2>
                  <p>
                    Eight mandatory requirements. A capability register with
                    deliberate gaps and contradictions. All synthetic, all
                    inspectable.
                  </p>
                  <button
                    className="primary"
                    onClick={demo}
                    disabled={!connected || !canAnalyze || busy || processing}
                  >
                    Run seeded demonstration →
                  </button>
                  <p className="fine">
                    {identity?.role === "viewer"
                      ? "Viewer access: open a saved analysis from the sidebar to inspect its sources."
                      : "No external model calls. No cloud resources."}
                  </p>
                </section>
              ) : (
                <>
                  <section
                    className="benchmark-panel"
                    aria-label="Analysis execution"
                  >
                    <strong>
                      {run.provider === "bedrock"
                        ? "AI-assisted review · AWS Bedrock"
                        : "Extractive baseline"}
                    </strong>
                    <p className="fine">
                      {run.pipeline_version} ·{" "}
                      {run.provider === "bedrock"
                        ? run.model_cost_usd == null
                          ? "Model cost unknown"
                          : `Estimated model cost US$${run.model_cost_usd.toFixed(4)}`
                        : "No model calls"}
                    </p>
                    {run.model_config_sha256 && (
                      <details>
                        <summary>Execution configuration identity</summary>
                        <code>{run.model_config_sha256}</code>
                      </details>
                    )}
                  </section>
                  <section className="document-bar">
                    <span className="doc-icon">▤</span>
                    <div>
                      <strong>{run.documents[0].title}</strong>
                      <small>
                        Immutable source · {run.documents.length} documents ·{" "}
                        {
                          items.filter((a) => a.review_state === "approved")
                            .length
                        }{" "}
                        approved
                      </small>
                    </div>
                    <button
                      className="secondary"
                      disabled={!canAnalyze || busy || processing}
                      onClick={demo}
                    >
                      Reload demo
                    </button>
                  </section>
                  <div className="workbench">
                    <section className="requirement-panel">
                      <div className="panel-title">
                        <h2>Requirement register</h2>
                        <span>{visible.length}</span>
                      </div>
                      <input
                        className="search"
                        aria-label="Search requirements"
                        placeholder="Search requirements…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                      <select
                        aria-label="Filter status"
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                      >
                        <option value="all">All assessments</option>
                        {Object.entries(labels).map(([value, label]) => (
                          <option value={value} key={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                      <div className="requirement-list">
                        {visible.map(({ value: a, index }) => (
                          <button
                            key={a.requirement.id}
                            className={
                              selected === index
                                ? "requirement selected"
                                : "requirement"
                            }
                            onClick={() => {
                              setSelected(index);
                              setNote("");
                            }}
                          >
                            <div>
                              <span className="req-id">
                                REQ-{String(index + 1).padStart(3, "0")}
                              </span>
                              <span className={"badge " + a.status}>
                                {labels[a.status]}
                              </span>
                            </div>
                            <p>{a.requirement.text}</p>
                            <small>
                              {a.requirement.category}{" "}
                              <span>· {a.review_state}</span>
                            </small>
                          </button>
                        ))}
                        {!visible.length && (
                          <p className="fine">No matching requirements.</p>
                        )}
                      </div>
                    </section>
                    <section className="evidence-panel">
                      {item ? (
                        <>
                          <div className="panel-title">
                            <h2>Evidence & decision</h2>
                            <span className={"badge " + item.status}>
                              {labels[item.status]}
                            </span>
                          </div>
                          <div className="detail">
                            <p className="eyebrow">SOURCE REQUIREMENT</p>
                            <h3>{item.requirement.text}</h3>
                            <button
                              className="source-link"
                              onClick={() =>
                                setCitation(item.requirement.source)
                              }
                            >
                              ↗ Inspect requirement source
                            </button>
                            <p className="eyebrow">
                              SUPPORTING EXCERPTS · {item.evidence.length}
                            </p>
                            {item.evidence.map((c, i) => (
                              <button
                                className="citation"
                                key={c.document_id + ":" + c.start}
                                onClick={() => setCitation(c)}
                              >
                                <div>
                                  <span className="citation-num">{i + 1}</span>
                                  <strong>
                                    {
                                      run.documents.find(
                                        (d) => d.id === c.document_id,
                                      )?.title
                                    }
                                  </strong>
                                  <span>↗</span>
                                </div>
                                <blockquote>{c.quote}</blockquote>
                                <small>
                                  {sourceLocation(
                                    run.documents.find(
                                      (d) => d.id === c.document_id,
                                    ),
                                    c,
                                  )}{" "}
                                  · Verified text excerpt
                                </small>
                              </button>
                            ))}
                            {!item.evidence.length && (
                              <div className="gap">
                                <strong>Evidence is missing</strong>
                                <p>
                                  Obtain a source that demonstrates the
                                  capability. Approval is blocked until
                                  supporting evidence is available.
                                </p>
                              </div>
                            )}
                            <div className="draft">
                              <p className="eyebrow">EXTRACTIVE DRAFT</p>
                              <p>{item.draft}</p>
                            </div>
                            <div className="review">
                              <h3>
                                Human decision{" "}
                                <span className="badge neutral">
                                  v{item.version} · {item.review_state}
                                </span>
                              </h3>
                              {!canReview && (
                                <p className="fine">
                                  A reviewer or administrator must record this
                                  decision. Your role can inspect the sources.
                                </p>
                              )}
                              <label>
                                Review note
                                <textarea
                                  aria-label="Review note"
                                  value={note}
                                  disabled={!canReview}
                                  onChange={(e) => setNote(e.target.value)}
                                  placeholder="Explain what you checked and why."
                                />
                              </label>
                              <div className="review-actions">
                                <button
                                  className="secondary"
                                  disabled={busy || !canReview || !note.trim()}
                                  onClick={() => review("rejected")}
                                >
                                  Reject
                                </button>
                                <button
                                  className="primary"
                                  disabled={
                                    busy ||
                                    !canReview ||
                                    !note.trim() ||
                                    item.status !== "evidence_found"
                                  }
                                  onClick={() => review("approved")}
                                >
                                  Approve evidence review
                                </button>
                              </div>
                              <p className="fine">
                                Evidence found indicates lexical relevance; it
                                does not establish contractual compliance.
                              </p>
                            </div>
                          </div>
                        </>
                      ) : (
                        <div className="empty">
                          <h2>No mandatory lines found.</h2>
                          <p>
                            The baseline recognizes must, shall, and required.
                            Other drafting conventions need the next extraction
                            milestone.
                          </p>
                        </div>
                      )}
                    </section>
                  </div>
                  <section className="trace">
                    <h2>Workflow trace</h2>
                    {run.trace.map((s, i) => (
                      <div key={i}>
                        <span className="dot" />
                        <strong>{String(s.stage)}</strong>
                        <code>
                          {"duration_ms" in s
                            ? Number(s.duration_ms).toFixed(2) + " ms"
                            : "Citations validated"}
                        </code>
                        {"attempts" in s && (
                          <small>
                            {String(s.attempts)} attempts · {String(s.failures)}{" "}
                            failures
                          </small>
                        )}
                      </div>
                    ))}
                  </section>
                </>
              )}
            </>
          )}
          {page === "benchmarks" &&
            (benchmark ? (
              <>
                <div className="stats">
                  {[
                    ["Golden cases", benchmark.unique_cases],
                    [
                      "Cases passed",
                      (benchmark.case_pass_rate * 100).toFixed(1) + "%",
                    ],
                    [
                      "Extraction recall",
                      percentage(benchmark.extraction_recall),
                    ],
                    [
                      "Citation integrity",
                      percentage(benchmark.citation_integrity),
                    ],
                  ].map(([label, value]) => (
                    <div className="stat" key={String(label)}>
                      <span>{label}</span>
                      <strong>{value}</strong>
                      <small>Measured synthetic baseline</small>
                    </div>
                  ))}
                </div>
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
                            <td>
                              {failureDescription(benchmark.results, r.id)}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                  <p className="fine">
                    Case results require every repetition to pass. Duration
                    shows the first repetition; repeated runs do not increase
                    the number of independent quality cases.
                  </p>
                </section>
                <ScenarioPanel
                  baseline={benchmark.scenario_baseline}
                  live={benchmark.scenario_live}
                />
                {benchmark.live_reasoning && (
                  <LiveReasoningPanel reports={benchmark.live_reasoning} />
                )}
                {benchmark.reasoning && (
                  <ReasoningPanel report={benchmark.reasoning} />
                )}
                {benchmark.adversarial && (
                  <AdversarialPanel report={benchmark.adversarial} />
                )}
                {benchmark.recovery && (
                  <section className="benchmark-panel recovery-panel">
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
                                  (r.passed
                                    ? "evidence_found"
                                    : "conflicting_evidence")
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
                      These scenarios exercise queue correctness. They do not
                      measure AI answer quality.
                    </p>
                  </section>
                )}
                {benchmark.postgres && (
                  <section className="benchmark-panel recovery-panel">
                    <div className="panel-title">
                      <h2>PostgreSQL integration</h2>
                      <span className="badge evidence_found">
                        {benchmark.postgres.groups_passed} /{" "}
                        {benchmark.postgres.results.length} integration groups
                        passed
                      </span>
                    </div>
                    <p className="fine">
                      PostgreSQL {benchmark.postgres.server_version} · pgvector{" "}
                      {benchmark.postgres.pgvector_available_version} · Local
                      execution
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
                            <td>
                              {r.id.replace(/^test_/, "").replaceAll("_", " ")}
                            </td>
                            <td>
                              <span
                                className={
                                  "badge " +
                                  (r.passed
                                    ? "evidence_found"
                                    : "conflicting_evidence")
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
                                  (r.passed
                                    ? "evidence_found"
                                    : "conflicting_evidence")
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
                      These cases check text provenance and safe failure,
                      independently of AI answer quality.
                    </p>
                  </section>
                )}
                {benchmark.retrieval && (
                  <RetrievalPanel report={benchmark.retrieval} />
                )}
                {benchmark.persistent_retrieval && (
                  <RetrievalPanel
                    report={benchmark.persistent_retrieval}
                    persistent
                  />
                )}
              </>
            ) : (
              <section className="empty">
                <h2>Benchmark report unavailable</h2>
                <p>
                  Connect the workspace and run the CHAOSLAB evaluator to
                  populate this view.
                </p>
              </section>
            ))}
          {page === "audit" && (
            <section className="benchmark-panel">
              <h2>Review history</h2>
              {audit.map((event) => (
                <div className="audit-event" key={String(event.id)}>
                  <strong>{String(event.action)}</strong>
                  <span>{String(event.actor)}</span>
                  <small>{new Date(String(event.time)).toLocaleString()}</small>
                  <pre>{JSON.stringify(event.details, null, 2)}</pre>
                </div>
              ))}
              {!audit.length && (
                <p>
                  No events loaded. Open an analysis before viewing its audit
                  trail.
                </p>
              )}
            </section>
          )}
          <footer>
            <span>ATLAS · Requirements review</span>
            <span>CHAOSLAB · Evaluation</span>
          </footer>
        </div>
      </main>
      {compose && (
        <Dialog
          name="New analysis"
          className="modal compose-modal"
          canClose={!busy}
          onClose={() => setCompose(false)}
        >
          <button
            className="close"
            aria-label="Close"
            disabled={busy}
            onClick={() => setCompose(false)}
          >
            ×
          </button>
          <p className="eyebrow">NEW ANALYSIS</p>
          <h2>Bring your requirements and evidence.</h2>
          <p>
            Upload text-bearing PDF or DOCX files up to 1 MB, or paste text.
            Keep confidential material out of the demonstration.
          </p>
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
          {busy && <p role="status">Preparing your documents…</p>}
          <label>
            Analysis mode
            <select
              aria-label="Analysis mode"
              value={executionMode}
              disabled={busy}
              onChange={(event) => setExecutionMode(event.target.value)}
            >
              <option value="baseline">
                Extractive baseline · no model calls
              </option>
              {executionOptions.model.enabled && (
                <option value="bedrock">
                  AI-assisted review · AWS Bedrock
                </option>
              )}
            </select>
          </label>
          {executionMode === "bedrock" ? (
            <p role="note">
              Source text will be sent to AWS Bedrock for provisional
              assessment. Model: {executionOptions.model.model_id} ·{" "}
              {executionOptions.model.region}. Up to US$
              {Number(
                executionOptions.model.maximum_reserved_inference_usd,
              ).toFixed(4)}{" "}
              is reserved from the configured test allowance for this job.
              Actual token cost may be lower or unknown; this is not an invoice.
              A configured model worker and valid credentials are required.
              Human review remains mandatory.
            </p>
          ) : (
            <p className="fine">
              Local extraction and retrieval. No source text is sent to a model.
            </p>
          )}
          <div className="upload-grid">
            {(
              [
                ["rfp", "RFP / requirements", uploadedRfp, rfp],
                [
                  "knowledge",
                  "Capability register",
                  uploadedKnowledge,
                  knowledge,
                ],
              ] as const
            ).map(([kind, title, uploaded, text]) => (
              <section className="upload-card" key={kind}>
                <h3>{title}</h3>
                <label className="file-label">
                  {kind === "rfp" ? "RFP file" : "Knowledge file"}
                  <input
                    type="file"
                    accept=".pdf,.docx"
                    disabled={busy}
                    onChange={(e) => {
                      void upload(e.target.files?.[0], kind);
                      e.target.value = "";
                    }}
                  />
                </label>
                {uploaded && (
                  <div className="upload-summary">
                    <strong>{uploaded.title}</strong>
                    <small>
                      {uploaded.source_map?.segments.length} mapped{" "}
                      {uploaded.source_map?.format === "pdf"
                        ? "pages"
                        : "paragraphs"}{" "}
                      · Immutable source
                    </small>
                    {uploaded.source_map?.warnings.map((w) => (
                      <p className="fine" key={w}>
                        {w}
                      </p>
                    ))}
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() => {
                        if (kind === "rfp") {
                          setUploadedRfp(null);
                          setRfp("");
                        } else {
                          setUploadedKnowledge(null);
                          setKnowledge("");
                        }
                      }}
                    >
                      Remove {kind === "rfp" ? "RFP" : "knowledge"} file
                    </button>
                  </div>
                )}
                <label>
                  {uploaded
                    ? "Extracted text preview"
                    : kind === "rfp"
                      ? "RFP text"
                      : "Knowledge text"}
                  <textarea
                    readOnly={!!uploaded}
                    disabled={busy}
                    value={text}
                    onChange={(e) =>
                      kind === "rfp"
                        ? setRfp(e.target.value)
                        : setKnowledge(e.target.value)
                    }
                    rows={5}
                  />
                </label>
              </section>
            ))}
          </div>
          <button
            className="primary"
            disabled={!rfp.trim() || !knowledge.trim() || busy}
            onClick={analyze}
          >
            Analyze documents
          </button>
        </Dialog>
      )}
      {citation && sourceDoc && (
        <Dialog
          name="Source document"
          className="modal source-modal"
          onClose={() => setCitation(null)}
        >
          <button
            className="close"
            aria-label="Close source"
            onClick={() => setCitation(null)}
          >
            ×
          </button>
          <p className="eyebrow">IMMUTABLE SOURCE</p>
          <h2>{sourceDoc.title}</h2>
          <p className="source-location">
            {sourceLocation(sourceDoc, citation)}
          </p>
          {sourceDoc.source_map && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() => downloadOriginal(sourceDoc)}
            >
              Download original source
            </button>
          )}
          <p className="fine">Text identity: {citation.digest}</p>
          {sourceDoc.source_map?.warnings.map((w) => (
            <p className="fine" key={w}>
              {w}
            </p>
          ))}
          <pre className="source-text">
            {unicodeSlice(sourceDoc.text, 0, citation.start)}
            <mark>
              {unicodeSlice(sourceDoc.text, citation.start, citation.end)}
            </mark>
            {unicodeSlice(sourceDoc.text, citation.end)}
          </pre>
        </Dialog>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthBoundary>{(access) => <App access={access} />}</AuthBoundary>
  </React.StrictMode>,
);
