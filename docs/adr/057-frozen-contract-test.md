# Freeze the contract test before loading it

The complete development run exposed weak contradiction detection and incomplete evidence selection. Using the separate test split to adjust the prompt would turn it into another development set. We need a record of what was fixed before test exposure and a runner that refuses accidental changes.

The protocol is created only after saved development observations reproduce the complete published result. It binds the archive/member, model and tokenizer, prompt, request/schema source, token limits, scorer files and reporting rules. Macro label F1 is primary; the report also keeps accuracy, joint evidence correctness, per-class errors and missing predictions. There is no selected subset or post-test threshold.

The protocol file is new, private and fsynced. Its checksum is supplied separately to planning, execution and replay. The planner checks it before reading test JSON; the model runner also pins its execution recipe before and after each call. Protocol changes raise a cohort-level error, escaping the judge's ordinary wrong-answer handling. A provider interruption preserves the full reservation and partial evidence without a silent retry.

Development entry points retain their existing task identity and default behavior. Test requests and journals have a distinct identity. The model still receives the same label-free request structure and structured-output schema. The independent evaluator can rescore a complete test journal without importing ATLAS or provider libraries.

The global configured call ceiling rises from 100 to 200 to admit the 123-contract split as one cohort. The default stays twelve and token/dollar limits still apply. The runner narrows larger capacity to exactly the selected full cohort before reserving spending. No spending authorization follows from changing a validation ceiling.

Twenty-two new controls use fictional archives. They cover freeze-before-test ordering, evidence admission, changed policies/source/model settings, explicit task separation, wrong protocol checksums, malformed files, replay and a dry plan with no credential lookup or reservation. The local suite passed 898 tests with eighteen optional PostgreSQL groups skipped. A freshly installed wheel separately passed fictional freeze/test/replay controls with no ATLAS installation. These checks are distinct from the real model evaluation.

The actual protocol was frozen before test JSON was loaded. The subsequent offline plan admitted all 123 contracts without a provider request. The owner then approved the cumulative model allowance separately. Model results and independent replay remain a later acceptance gate.

A local owner can bypass the loader, replace files and recompute checksums. This is an accidental-drift boundary, not signed provenance or proof that nobody has ever seen this public corpus. The protocol cannot rule out pretraining exposure or establish general contract accuracy.
