# Demonstrating the two projects

Start with the review problem, then show how the evaluator catches mistakes. Keep the application and the experiments distinct: the public ATLAS sample runs rules; the CHAOSLAB page shows saved model results.

## ATLAS: a finding a reviewer can check

1. Open the [review sample](https://atlas-review-lab.onrender.com/?view=review). Explain that the buyer has written requirements and the supplier has supplied capability records. Both documents are fictional.
2. Run the sample analysis. Open the recovery-time example: the requirement is four hours, while the supplier guarantees eight. Show both exact source excerpts rather than reading only the finding label.
3. Explain the difference between conflicting evidence and missing evidence. A missing excerpt does not prove the supplier cannot meet the requirement.
4. Leave the recovery finding rejected, save the review and reload. Show the saved decision. The lab's temporary history survives a page reload but expires or disappears when the service restarts.
5. End the session. Do not describe the public lab as accepting arbitrary uploads, running a paid model or offering durable storage.

The private workbench also accepts text-bearing PDF/DOCX files and pasted documents. Demonstrating that separate profile requires a prepared fictional file, a running API/worker and a completed off-camera sign-in. The real Cognito acceptance covers one local user with SQLite; it does not establish deployed managed-service acceptance. Keep credentials, account menus and external contract text off camera.

## CHAOSLAB: inspect a wrong answer, then reproduce a gate

1. Open [Evaluation results](https://atlas-review-lab.onrender.com/?view=evaluation). State that the numbers come from earlier executions, and opening the page starts no model or evaluation request.
2. Compare the baseline and recorded model on the three review scenarios. Explain that all obligations must pass for a complete scenario to pass. Keep this separate from the twelve transfer cases; the denominators describe different experiments.
3. Open the deletion-deadline failure. The supplier promises 24 hours against a 48-hour limit, yet the model recorded a contradiction. Its citation matched the source. This makes the distinction between source integrity and answer correctness concrete.
4. Switch to the availability case. Here extraction failed, so there is no usable citation. Neither failure is hidden from the saved report.
5. Run the [independent comparison example](../examples/review-regression/README.md). First compare the reference with itself, then select the wrong-decision, broken-citation and missing-answer fixtures. These are deliberately authored answers, not additional model experiments. Show the reports and expected exit codes.
6. Explain that the evaluator can be installed without ATLAS. Its adapter process controls are not a sandbox for hostile code.

## Evidence and limits

The public browser acceptance covers both layouts, failure selection and the absence of API calls on the recorded-results page. The independent rehearsal executes all four CLI comparisons in a separate installed environment without ATLAS. See [hosted checks](../reports/public-evaluation-hosted.json) and [CLI rehearsal](../reports/demo-walkthrough.json).

These checks establish the steps above, not audience comprehension or a finished video. No recording has been made. The complete external contract-model evaluation, untouched-test comparison and durable managed hosting are still separate unfinished delivery gates. Do not substitute small synthetic scores for those results or describe them as representative contract accuracy.
