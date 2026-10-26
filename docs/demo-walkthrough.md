# Demonstrating the two projects

Start with the review problem, then show how the evaluator catches mistakes. Keep the application and the experiments distinct: the public ATLAS sample runs rules; the CHAOSLAB page shows saved model results.

## ATLAS: a finding a reviewer can check

1. Open the [review sample](https://atlas-review-lab.onrender.com/?view=review). Explain that the buyer has written requirements and the supplier has supplied capability records. Both documents are fictional.
2. Run the sample analysis. Open the recovery-time example: the requirement is four hours, while the supplier guarantees eight. Show both exact source excerpts rather than reading only the finding label.
3. Explain the difference between conflicting evidence and missing evidence. A missing excerpt does not prove the supplier cannot meet the requirement.
4. Leave the recovery finding rejected, save the review and reload. Show the saved decision. The lab's temporary history survives a page reload but expires or disappears when the service restarts.
5. End the session. Do not describe the public lab as accepting arbitrary uploads, running a paid model or offering durable storage.

The private workbench has a separately rehearsed document-intake flow. Upload `datasets/documents/municipal-rfp.pdf` as the RFP and `datasets/documents/capability-register.docx` as the evidence. They contain two mapped pages and eight mapped paragraphs. Analyze them using the baseline, open the recovery requirement on page two and download the original PDF. The rehearsal checks that the downloaded bytes match the input.

For the conflicting recovery promise, approval stays disabled. Record a rejection with a reason, reload, reconnect and reopen the saved analysis. The rejected version remains available. Open **Audit trail** to see the decision, requirement, actor and note; source identifiers and other technical fields sit behind **Technical details**. Disconnect to clear the displayed history.

This rehearsal uses a fresh local bearer identity and isolated SQLite database. The separate real Cognito acceptance covers one local user; neither establishes deployed managed-service acceptance. Complete sign-in off camera and keep credentials, account menus and external contract text out of the recording.

To reproduce the document workflow with the locked environment, installed Chromium and Node/pnpm available:

```sh
pnpm --dir apps/web build
PYTHONPATH=src .runtime/bin/python scripts/verify_document_review.py
```

The runner starts its own API/worker on loopback port 8136, creates private temporary credentials and a new database under `var/intake-rehearsal`, and stops its processes afterward. It expects Chromium in `.cache/playwright`; install it with that explicit browser-cache path if necessary. `--node` and `--pnpm` accept explicit executable paths. It never modifies the existing workspace database or enables model jobs. Logs and credentials remain private; the public [rehearsal report](../reports/document-review-rehearsal.json) contains only scope, counts and fingerprints.

## CHAOSLAB: inspect a wrong answer, then reproduce a gate

1. Open [Evaluation results](https://atlas-review-lab.onrender.com/?view=evaluation). State that the numbers come from earlier executions, and opening the page starts no model or evaluation request.
2. Compare the baseline and recorded model on the three review scenarios. Explain that all obligations must pass for a complete scenario to pass. Keep this separate from the twelve transfer cases; the denominators describe different experiments.
3. Open the deletion-deadline failure. The supplier promises 24 hours against a 48-hour limit, yet the model recorded a contradiction. Its citation matched the source. This makes the distinction between source integrity and answer correctness concrete.
4. Switch to the availability case. Here extraction failed, so there is no usable citation. Neither failure is hidden from the saved report.
5. Run the [independent comparison example](../examples/review-regression/README.md). First compare the reference with itself, then select the wrong-decision, broken-citation and missing-answer fixtures. These are deliberately authored answers, not additional model experiments. Show the reports and expected exit codes.
6. Explain that the evaluator can be installed without ATLAS. Its adapter process controls are not a sandbox for hostile code.

## Evidence and limits

The public browser acceptance covers both layouts, failure selection and the absence of API calls on the recorded-results page. The independent rehearsal executes all four CLI comparisons in a separate installed environment without ATLAS. See [hosted checks](../reports/public-evaluation-hosted.json) and [CLI rehearsal](../reports/demo-walkthrough.json).

These checks establish the steps above, not audience comprehension or a finished video. No recording has been made. The complete external development-model evaluation and independent replay are now published. The separate frozen test comparison and standalone replay are now published too. Durable managed hosting remains unfinished. Do not substitute small synthetic scores for those results or describe them as representative contract accuracy.


## Recheck the private workbench

After building `apps/web`, an operator can run the connected browser file against a fresh isolated local API, worker and SQLite database:

```sh
PYTHONPATH=src .runtime/bin/python scripts/verify_document_review.py \
  --all-workflows --output reports/workbench-components.json
```

Node and pnpm must be on the operator's path, or supplied with the runner's `--node` and `--pnpm` options. This includes controlled-response cases as well as the real fictional-document flow. It makes no model call and does not replace the separate real Cognito or hosted acceptance checks. Without `--all-workflows`, the runner keeps its original single-intake rehearsal.
