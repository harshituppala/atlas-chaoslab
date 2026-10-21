# Paired scenario comparisons

Run from the repository root. CHAOSLAB compares raw saved scenario outputs, not existing aggregate reports. It makes no model calls.

```sh
PYTHONPATH=src .runtime/bin/python -m chaoslab.comparison \
  --dataset datasets/scenarios.json \
  --reference var/comparison/reference.json \
  --candidate var/comparison/candidate.json \
  --output reports/my-comparison.json
```

Both artifacts must follow the label-free scenario manifest/bundle contract: dataset_sha256 plus results with opaque id, input_sha256 and status succeeded/failed. A succeeded row includes output.documents and output.assessments. Obtain the manifest with chaoslab.scenarios --export-inputs into a new private var path. Expected labels stay in the scorer's authored dataset; never send them to an agent adapter. Existing aggregate reports lack raw evidence and are intentionally insufficient.

The report includes paired scenario and obligation transitions, missing-attempt nulls, explicit operational failures, hashes and a fixture-only acceptance gate. Add --require-fixture-gate when a local/CI check should exit nonzero after writing a failed comparison. The default mode always permits recording honest quality failures; malformed/incompatible evidence remains an error in either mode. Output must not alias an input. Choose public output only for synthetic, reviewed inputs; the CLI is not a general private-data sanitizer, and scenario IDs remain visible.

## Exit status and broken inputs

| Exit | Meaning | Report behavior |
| --- | --- | --- |
| 0 | Comparison completed; any requested fixture gate passed | Writes the comparison |
| 1 | A completed comparison failed the requested fixture gate | Writes failed evidence |
| 2 | Invalid dataset, artifact structure or unreadable input | Preserves an earlier report |

Saved succeeded rows need usable document, requirement, assessment and citation containers. Structural admission does not make wrong evidence valid: incorrect digests/spans, relation strings, missing requirements and unauthorized review states still fail scoring. Fresh adapter responses that cannot satisfy the observation shape are recorded as attempted execution failures.

The comparison reader bounds each input at eight megabytes and 64 nested levels. It refuses duplicate keys, non-finite values including exponent overflow, and malformed encoding. [ADR 043](adr/043-saved-observation-admission.md) describes the controlled failure cases and the standalone installation checks. Scorer/input drift refusal and filesystem publication failures remain separate operational errors; do not infer report publication from an exit status alone.

## Reproduce the recorded experiment

With this machine's retained private historical recording:

```sh
PYTHONPATH=src .runtime/bin/python scripts/compare_recorded_scenarios.py
```

This verifies var/bedrock/scenarios-live-v4.json against reports/scenarios-live-v4.json, executes a fresh extractive baseline via three trusted subprocesses, stores its raw outputs under a new private var/comparison directory, and writes reports/scenario-comparison.json. All source/dataset/model/report inputs are checked for drift. It neither changes the old reports nor calls Bedrock. If the private original is absent in a clean source-only checkout, the historical experiment cannot be rerun; supply your own compatible raw bundles to the generic CLI instead. The public comparison is not enough to reconstruct or independently reattest original inference.

The recorded result is five obligation contracts passing on both sides and four improving, zero regressing/unpaired, across three complete scenarios/nine obligations. The candidate is a historical single execution per scenario; the reference is a newly executed deterministic baseline. Do not use this as a latency/cost comparison, a statistical significance claim, nine independent production observations or proof of general model superiority. Keep the separate held-out and hostile-evidence failures visible.

## Verification

```sh
PYTHONPATH=src .runtime/bin/python -m pytest -q tests/test_comparison.py \
  --basetemp=var/pytest-comparison
PYTHONPATH=src .runtime/bin/python -m pytest -q \
  --basetemp=var/pytest-comparison-full --junitxml=var/comparison-backend.xml
```

The optional PostgreSQL groups need their separate integration environment. These tests establish comparator correctness on controlled mutations and the native regression suite; no new browser/cloud/identity-provider validation follows from them. No extraction/model pipeline version or fixture expectation changes are needed for this reporting-only milestone.
