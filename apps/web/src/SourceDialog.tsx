import { Dialog } from "./Dialog";
import {
  sourceLocation,
  unicodeSlice,
  type Citation,
  type Document,
} from "./workbench";

type Props = {
  citation: Citation;
  sourceDoc: Document;
  busy: boolean;
  onClose: () => void;
  onDownload: (document: Document) => Promise<void>;
};

export function SourceDialog({
  citation,
  sourceDoc,
  busy,
  onClose,
  onDownload,
}: Props) {
  return (
    <Dialog
      name="Source document"
      className="modal source-modal"
      onClose={onClose}
    >
      <button className="close" aria-label="Close source" onClick={onClose}>
        ×
      </button>
      <p className="eyebrow">IMMUTABLE SOURCE</p>
      <h2>{sourceDoc.title}</h2>
      <p className="source-location">{sourceLocation(sourceDoc, citation)}</p>
      {sourceDoc.source_map && (
        <button
          className="secondary"
          disabled={busy}
          onClick={() => onDownload(sourceDoc)}
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
  );
}
