# Reviewing requirements without losing the source

An RFP can contain hundreds of obligations. A supplier may have the information needed to answer them, spread across capability records and policy documents. A reviewer needs to find that information, decide whether it answers the requirement and retain a record of the decision.

ATLAS handles that review. CHAOSLAB checks the systems that generate its findings. They share a repository so changes can be tested together, while the evaluator also runs on its own.

## Start with a disagreement

The fictional RFP requires recovery within four hours. The capability register promises eight. ATLAS selects the relevant passage and puts it beside the requirement. A reviewer can open the source, inspect the highlight and record a decision with a note.

That example shapes the design: related text is not automatically supporting evidence. The extractive baseline finds passages using rules and retrieval. The optional model workflow assesses their relationship to the requirement. Neither can approve its own finding; the review remains a separate action.

The [public lab](https://atlas-review-lab.onrender.com) demonstrates this on fixed fictional inputs. The private workbench also accepts text-bearing PDF and DOCX uploads. Scanned documents need OCR, which is not implemented.

## Keep the evidence checkable

Documents are stored as immutable snapshots. Each citation names a document, its content hash and a range of Unicode characters. The service verifies that the quoted text matches that range before publishing a result. Page and paragraph mappings let a reviewer find the same passage in an uploaded document, and the original file is available for comparison.

The model chooses among server-owned evidence options. It does not invent offsets or source text. This prevents one class of fabricated citation; it does not prove the selected passage supports the conclusion. The recorded experiments include a numeric-threshold mistake despite a valid citation, and a hostile appendix selected as evidence. [The failure analysis](adr/030-live-paired-injection-diagnostic.md) keeps those cases visible.

## Treat work and review as durable records

Analysis runs in a worker rather than holding an HTTP request open. Jobs use expiring leases. A replacement worker can recover abandoned work, while an old worker cannot publish after losing ownership. The result, initial review state and audit event commit together.

Reviews use version checks. If two reviewers act on the same version, the later stale update is rejected rather than silently replacing the earlier decision. The audit view shows the action, actor, requirement, note and saved version. [The queue decision](adr/003-durable-jobs.md) explains the failure cases behind these choices.

The PostgreSQL path uses separate API and worker logins with tenant row policies. Local integration checks exercise role boundaries, pooled connections, concurrent reviews and rollback; a separate recovery drill restored populated tables into an empty cluster. Those are different checks from a deployed backup service. The private SQLite launcher remains useful for a small local demonstration.

## Measure answers separately from operations

CHAOSLAB checks extraction, evidence selection, citation integrity, review state and failures separately. A timeout stays a failed attempt. A missing prediction stays in the denominator. Paired reports show what changed between two runs, including new mistakes inside a case that already failed for another reason.

The small fictional RFP datasets help explain specific failures, but they are too narrow for a general accuracy claim. A separate [ContractNLI evaluation](contractnli-evaluation.md) uses externally authored NDA annotations. On all 61 development contracts, the model reached 77.4% label accuracy and 48.7% correctness when both the label and complete evidence were required. Only 41 of 95 contradictions were labeled correctly. These are development results, not RFP accuracy or legal validation.

Saved responses can be rescored without importing the adapter or making another model call. A fresh standalone CHAOSLAB installation reproduced the development scores with ATLAS and provider libraries absent. The next comparison uses a separate test split with the model and scoring rules frozen before that split was loaded.

## Where the project stands

The fictional public lab has HTTPS, browser and restart checks. Its temporary sessions reset as advertised. Real Cognito reviewer sign-in has also been verified locally, including workspace denial, saved review, logout and repeat sign-in. The full authenticated workbench still needs durable hosted storage and deployed recovery checks.

The complete development evaluation and its independent replay are published. The separate test run and final demonstration recordings are not complete. [Current status](STATUS.md) records individual runs and remaining work without treating one successful check as proof of everything else.

[Run locally](../README.md#run-atlas-locally) · [Architecture](architecture.md) · [Security assumptions](threat-model.md) · [Reviewer route](reviewer-guide.md)
