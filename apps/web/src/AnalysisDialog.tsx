import { Dialog } from "./Dialog";
import type { Document, ExecutionOptions } from "./workbench";

type Kind = "rfp" | "knowledge";
type Props = {
  busy: boolean;
  error: string;
  executionMode: string;
  executionOptions: ExecutionOptions;
  rfp: string;
  knowledge: string;
  uploadedRfp: Document | null;
  uploadedKnowledge: Document | null;
  onClose: () => void;
  onExecutionModeChange: (mode: string) => void;
  onUpload: (file: File | undefined, kind: Kind) => Promise<void>;
  onRemoveFile: (kind: Kind) => void;
  onTextChange: (kind: Kind, text: string) => void;
  onAnalyze: () => Promise<void>;
};

export function AnalysisDialog({
  busy,
  error,
  executionMode,
  executionOptions,
  rfp,
  knowledge,
  uploadedRfp,
  uploadedKnowledge,
  onClose,
  onExecutionModeChange,
  onUpload,
  onRemoveFile,
  onTextChange,
  onAnalyze,
}: Props) {
  return (
    <Dialog
      name="New analysis"
      className="modal compose-modal"
      canClose={!busy}
      onClose={onClose}
    >
      <button
        className="close"
        aria-label="Close"
        disabled={busy}
        onClick={onClose}
      >
        ×
      </button>
      <p className="eyebrow">NEW ANALYSIS</p>
      <h2>Bring your requirements and evidence.</h2>
      <p>
        Upload text-bearing PDF or DOCX files up to 1 MB, or paste text. Keep
        confidential material out of the demonstration.
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
          onChange={(event) => onExecutionModeChange(event.target.value)}
        >
          <option value="baseline">Extractive baseline · no model calls</option>
          {executionOptions.model.enabled && (
            <option value="bedrock">AI-assisted review · AWS Bedrock</option>
          )}
        </select>
      </label>
      {executionMode === "bedrock" ? (
        <p role="note">
          Source text will be sent to AWS Bedrock for provisional assessment.
          Model: {executionOptions.model.model_id} ·{" "}
          {executionOptions.model.region}. Up to US$
          {Number(
            executionOptions.model.maximum_reserved_inference_usd,
          ).toFixed(4)}{" "}
          is reserved from the configured test allowance for this job. Actual
          token cost may be lower or unknown; this is not an invoice. A
          configured model worker and valid credentials are required. Human
          review remains mandatory.
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
            ["knowledge", "Capability register", uploadedKnowledge, knowledge],
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
                  void onUpload(e.target.files?.[0], kind);
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
                    onRemoveFile(kind);
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
                onChange={(e) => onTextChange(kind, e.target.value)}
                rows={5}
              />
            </label>
          </section>
        ))}
      </div>
      <button
        className="primary"
        disabled={!rfp.trim() || !knowledge.trim() || busy}
        onClick={onAnalyze}
      >
        Analyze documents
      </button>
    </Dialog>
  );
}
