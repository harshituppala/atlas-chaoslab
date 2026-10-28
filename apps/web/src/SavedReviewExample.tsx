import { Dialog } from "./Dialog";

export function SavedReviewExample({ close }: { close: () => void }) {
  return (
    <Dialog
      name="Saved worked example"
      className="source-dialog saved-example"
      onClose={close}
    >
      <button onClick={close}>Close saved example</button>
      <p className="eyebrow">Saved worked example · fictional · read-only</p>
      <h2>A four-hour requirement, an eight-hour promise</h2>
      <p>
        This authored walkthrough uses excerpts from the sample documents. It
        runs no analysis and saves no review. Your live session stays separate.
      </p>
      <h3>What the buyer requires</h3>
      <p>Northstar municipal services RFP · section 5.2</p>
      <blockquote>5.2 Recovery time must be at most 4 hours.</blockquote>
      <h3>What the supplier promises</h3>
      <p>Northstar Cloud capability register</p>
      <blockquote>Recovery time is only guaranteed within 8 hours.</blockquote>
      <h3>Why a reviewer would request follow-up</h3>
      <p>
        An eight-hour guarantee does not meet a four-hour limit. Ask the
        supplier for evidence of a four-hour commitment before accepting this
        requirement. Finding the right passage does not make the promise
        sufficient.
      </p>
      <a href="?view=evaluation">Inspect recorded evaluation results</a>
    </Dialog>
  );
}
