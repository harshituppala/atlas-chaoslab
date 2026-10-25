# Four saved answers, one review requirement

The buyer requires recovery within four hours. The supplier promises eight. The expected finding is a conflict, with the supplier's exact statement as evidence and the review left pending.

These files are handwritten fixtures. They are not model responses. Use them to demonstrate the evaluator's behavior without an API key or an ATLAS server.

| Candidate | Deliberate change | Expected comparison |
| --- | --- | --- |
| `reference.json` | None | One requirement passes in both runs; exit 0 |
| `wrong-decision.json` | Calls the conflicting promise supporting evidence | One regression; exit 1 |
| `broken-citation.json` | Replaces the supplier excerpt's digest | One regression; exit 1 |
| `missing-answer.json` | Removes the attempted case | One unpaired requirement; exit 1 |

The wrong-decision fixture keeps the original source text and citations. It illustrates why a valid citation cannot establish a correct assessment. The missing answer remains in the denominator rather than disappearing from the comparison.

After installing the standalone evaluator as described in [its guide](../../src/chaoslab/README.md#install-the-evaluator-on-its-own), run from the repository root:

```sh
chaoslab-compare --dataset examples/review-regression/dataset.json \
  --reference examples/review-regression/reference.json \
  --candidate examples/review-regression/wrong-decision.json \
  --output var/demo-wrong-decision.json --require-fixture-gate
```

Exit 1 is expected: the regression was detected and the report was written. Change `--candidate` to another file in the table and choose a new output path. Inspect `fixture_gate_passed`, `requirement_transitions` and `scenarios` in each report. A malformed input instead exits 2; it is an admission error, not a scored answer.

For all four checks with an installed environment that has no ATLAS dependency:

```sh
python scripts/verify_demo_walkthrough.py --python /absolute/path/to/evaluator-env/bin/python
```

The [measured rehearsal](../../reports/demo-walkthrough.json) records actual command outcomes and the input/scorer fingerprints. It demonstrates comparison gates, not model accuracy or protection against untrusted adapter code.
