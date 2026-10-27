# A short route through the projects

ATLAS compares requirements with supplier evidence and lets a person check the sources and record a decision. CHAOSLAB evaluates those answers and failure behavior. They share a repository; the evaluator also has an independently installable package.

1. **Try the task.** Open the [fictional review sample](https://atlas-review-lab.onrender.com/?view=review). The buyer needs recovery within four hours; the supplier promises eight. Inspect the actual passages and save a review. This public sample runs rules and keeps only temporary history.
2. **Inspect a model mistake.** Open [recorded evaluation results](https://atlas-review-lab.onrender.com/?view=evaluation). A model misread a deletion threshold despite citing the right text. The displayed counts are from small development sets, not general contract accuracy.
3. **Reproduce the evaluator.** The [four-answer example](../examples/review-regression/README.md) shows how a wrong answer, broken citation and missing attempt affect the gate. The saved answers are deliberately authored controls, not fresh model outputs.
4. **Check the implementation.** Begin with [durable job ownership](adr/003-durable-jobs.md), [database role boundaries](adr/012-database-tenant-policies.md) and [paired failure analysis](adr/030-live-paired-injection-diagnostic.md). Follow another decision only when its tradeoff matters to your review.
5. **Look beyond the fictional examples.** The [external development comparison](contractnli-evaluation.md#complete-development-model-comparison--october-26) scores all 61 contracts and shows where the model still fails. The separate [frozen test result](contractnli-evaluation.md#frozen-test-result--october-26) covers 123 contracts; read the contradiction errors alongside overall accuracy.
6. **Check what remains.** [Current status](STATUS.md) separates local, model, CI and hosted evidence. The [review follow-up](review-findings.md) records the completed external evaluation, known failures and optional hosted-service gates.

For the full document-intake demonstration and independent command-line run, use the [walkthrough](demo-walkthrough.md). For fresh database verification, use the [PostgreSQL CI guide](postgres-ci.md). Test counts describe execution coverage; they do not establish model quality or production readiness.
