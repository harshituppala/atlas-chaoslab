# A separate RFP evaluation

Status: proposed protocol. No new independent annotations, held-out inputs or model results are claimed. The completed ContractNLI development/test cohorts and their pinned source/wheel remain unchanged. This task would test RFP review itself, rather than infer its quality from NDA labels.

## Question

Can the system find mandatory requirements, select sufficient supplier evidence and preserve an appropriate human-review state? Measure extraction, relation, source integrity and completeness separately. Do not collapse retrieval success into a compliance decision.

## Inputs and roles

Prepare at least eight short, rights-cleared document packets with at least twenty-four mandatory requirements in total. Each packet contains one buyer RFP and one or more supplier records. Use text-bearing PDF/DOCX and canonical text; scans and OCR remain excluded. Use fictional records or public materials with documented reuse terms. Exclude private contracts, credentials and personal data.

Include at least six supported requirements, six numeric/negation conflicts, and six insufficient-evidence requirements. Include repeated source wording and a condition that changes an apparent match. Record selection rules before any system output is viewed. These are proposed coverage quotas, not sampled population frequencies.

Two readers who did not implement the system annotate independently before seeing model/baseline outputs. For every mandatory obligation they record exact buyer text/location, relation, supplier evidence IDs and passages, and a short rationale. Resolve disagreements in a dated adjudication record; identify who adjudicated and any connection to implementation. Do not describe same-author labels as external annotation. Keep pilot/practice documents outside the evaluation cohort.

## Freeze before running

1. Obtain rights/consent for the input materials and independent annotation work.
2. Validate canonical text, unique IDs, source spans and the scenario dataset contract. Check authored expectations without changing them to fit a system output.
3. Record dataset bytes/hash, source-document hashes, adjudicated labels, scorer source or installed wheel, extraction recipe, retrieval settings, provider/model if any, prompt, call/timeout/retry policy and intended comparisons.
4. Commit the protocol and record the exact revision/hash before opening evaluation outputs. Keep any model-call approval separate; this plan grants no additional spending.
5. Keep raw documents, answers and annotation notes private unless rights and explicit publication review allow disclosure. Publish only reviewed aggregates and fictional examples.

## Execution and scoring

Run the offline baseline first without changing frozen expectations. If a model comparison is later approved, use the same cohort and scoring rules. Retain every attempted, missing, timed-out and malformed result. Do not silently retry a paid or interrupted cohort. Count absent obligations as extraction failures, not as correct “insufficient evidence” judgments.

Report the number of packets/requirements, extraction precision/recall, relation confusion counts, valid source spans, complete evidence coverage, missing outputs, review states, whole-packet success and per-case failures. Report exact denominators, separating operational from answer-quality failures. A correct span can still support a wrong conclusion. Do not pool these metrics with ContractNLI results.

Human-assisted review is a separate condition: record initial system output, the person's correction and final outcome. Measure elapsed time only with an actual timed protocol and disclose practice/order effects. Small samples do not establish population accuracy, significance or customer time savings. Participant sessions from the usability plan do not automatically supply independent benchmark labels.

## Change policy

If a result motivates a repair, retain the original result. Use development-only examples to make the repair, then design a new evaluation cohort under a new protocol. Any retrospective rescoring must be explicitly labeled and use a separately pinned scorer. Never replace the completed ContractNLI frozen test or claim it remains untouched after tuning against its failures.

## What is still needed

Rights-cleared packets, independent readers, adjudication, a frozen cohort and authorized execution. The software can run the existing scenario contract; none of those human or data-access gates is completed by writing this plan.
