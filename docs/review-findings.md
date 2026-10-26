# Follow-up on the project review

This tracks the findings relevant to ATLAS and CHAOSLAB. The assessment was checked against source and executed evidence; it is not a list of accepted claims about unrelated projects.

| Finding | Status | Evidence and remaining gate |
| --- | --- | --- |
| PostgreSQL is outside ordinary CI | Fixed; remote gate passed | The new [Linux CI job](https://github.com/harshituppala/atlas-chaoslab/actions/runs/40256025026) passed all seventeen selected groups with real restricted-role connections. Subsequent commits now run that gate; see [the database guide](postgres-ci.md). |
| The external model comparison is incomplete | Verified; blocked on credential refresh | Both stopped prefixes remain preserved. The independent reference is complete; a complete model cohort and replay are not. The [continuation runner](contract-model-runbook.md#continue-an-admitted-prefix) can request only the missing inputs after identity, price and retained-budget checks. |
| A frozen untouched-test comparison is missing | Verified; unfinished | The test split remains unused. Freeze the protocol and model settings before evaluating it; development results cannot substitute for that acceptance gate. |
| The full authenticated service has no durable hosted acceptance | Verified; unfinished | Real local Cognito review and separate PostgreSQL/container tests exist. The public lab is temporary and fictional. Prepare an explicit hosted-service cost/access choice before provisioning anything new. See [deployment gates](deployment.md). |
| Reviewers face too much documentation | Verified; shorter route prepared | Start with the [reviewer route](reviewer-guide.md), then follow a specific result or decision. No need to read every ADR. |
| The frontend entry point is too large | Verified; unfinished | It still combines intake, review, history and evaluation views. Extract those task boundaries after the delivery gates are stable, preserving connected-browser regressions rather than performing a broad unverified rewrite. |
| Green CI could be read as solved model quality | Verified; known failures retained | The [failure analysis](adr/030-live-paired-injection-diagnostic.md) and [recorded evaluation page](https://atlas-review-lab.onrender.com/?view=evaluation) distinguish citation integrity, answer quality and operational tests. Those failures have not been removed. |

A finding is marked fixed only after its specific acceptance evidence passes. Passing a build does not finish model evaluation, sign-in, hosting or recovery. No new deployment, inference authorization or external publication permission is implied by this tracker.
