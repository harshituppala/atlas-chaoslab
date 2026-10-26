export type Citation = {
  document_id: string;
  digest: string;
  start: number;
  end: number;
  quote: string;
};
export type Assessment = {
  requirement: { id: string; text: string; category: string; source: Citation };
  status: string;
  evidence: Citation[];
  draft: string;
  review_state: string;
  version: number;
  review_note?: string;
};
export type SourceMap = {
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
export type Document = {
  id: string;
  title: string;
  text: string;
  kind: "rfp" | "knowledge";
  source_map?: SourceMap | null;
};
export function unicodeSlice(text: string, start: number, end?: number) {
  return Array.from(text).slice(start, end).join("");
}
export function sourceLocation(
  document: Document | undefined,
  citation: Citation,
) {
  return (
    document?.source_map?.segments
      .filter((s) => s.start < citation.end && s.end > citation.start)
      .map((s) => (s.unit === "page" ? "Page " : "Paragraph ") + s.number)
      .join(" · ") || "Pasted source"
  );
}
export type ExecutionOptions = {
  model: {
    enabled: boolean;
    model_id?: string;
    region?: string;
    model_config_sha256?: string;
    maximum_reserved_inference_usd?: string;
  };
};
