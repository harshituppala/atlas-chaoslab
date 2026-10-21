# ADR 039: reject malformed experiments before scoring

Date: October 21, 2026. Status: local suite and installed-package checks passed; remote CI pending.

A controlled mutation exposed a false pass in the scenario judge. With an authored relation of `invalid` and an unknown agent status, both sides became the same fallback value. An otherwise well-formed answer could pass. No existing golden case uses that label; this was a defect in how malformed experiments were handled, not evidence that a recorded model result had improved.

Validate the authored contract before exporting inputs, scoring a scenario or comparing saved runs. Relations must be supported, contradicted or insufficient. Document IDs must be unique within a case. Expected obligations must quote the RFP, and evidence IDs must identify unique knowledge records. Insufficient evidence has no selected records; supported and contradicted expectations require them. Bound case counts, document counts and text lengths without importing ATLAS's models. Existing scenario and hostile-evidence expectations remain unchanged.

The command now distinguishes malformed experiments from failed candidates. Invalid comparison input exits with code 2 and preserves any previous report. A valid experiment that fails the requested fixture gate still writes its measured result and exits with code 1. A malformed label is never counted as an agent failure, a successful abstention or an accuracy observation.

Fresh baseline runs retain five passing obligations out of nine, zero passing complete scenarios out of three, and three passing hostile-evidence cases out of twelve. Archived datasets and reports were not replaced.

The validator is included in scorer fingerprints and in the separately installed wheel. Twenty-seven new tests cover the reproduced false pass, invalid relations, ambiguous source identities, impossible evidence labels, source-quote drift and report preservation. The complete native suite passes 498 tests, with eighteen optional PostgreSQL groups skipped. The [fresh package check](../../reports/chaoslab-package.json) also exercises invalid-label refusal without ATLAS installed.

This validates internal consistency, not whether an author's label is factually correct. The cases remain same-author development data. It does not create blinded evaluation, general agent support or a hostile-code sandbox. ATLAS extraction, model execution, pipeline versions and frozen model reports are unchanged.
