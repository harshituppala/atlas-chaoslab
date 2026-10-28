# Check saved reading-comprehension answers

This is a separate question-answering task with fictional archive rules, not an ATLAS requirement review. The input follows the documented [SQuAD question/context and saved-prediction format](https://rajpurkar.github.io/SQuAD-explorer/). No Stanford dataset was downloaded. The four questions and saved answers here are authored controls, not model benchmark results or outside adoption.

After installing `chaoslab-eval` from `src/chaoslab`, run:

```sh
chaoslab-qa --dataset examples/reading-qa/dataset.json \
  --reference examples/reading-qa/reference.json \
  --candidate examples/reading-qa/wrong-answer.json \
  --output var/reading-qa.json --require-fixture-gate
```

The wrong answer fails the gate with exit 1 after writing its report. Use `reference.json` for a passing control or `missing-answer.json` for an omitted answer. The omission remains in the denominator even when the correct answer is abstention (`""`). Unknown question IDs, duplicate JSON keys and invalid reference spans are invalid experiments; exit 2 preserves the previous report.

Optional source-span checking is a **CHAOSLAB extension**, not part of SQuAD's prediction format. Supply both `--reference-citations examples/reading-qa/reference-citations.json` and `--candidate-citations examples/reading-qa/broken-citations.json` with the correct candidate answers to expose a correct answer with a corrupt source digest. Offsets are Python Unicode character indices in the question's paragraph; the digest is SHA-256 of UTF-8 context bytes. Empty answers require no citation. Source validity alone does not establish a correct answer.

Normalization removes ASCII punctuation/articles, folds case and joins whitespace; token F1 uses multiset overlap and the best reference answer. This command does not implement probability-threshold tuning or official leaderboard evaluation. Missing answers explicitly receive zero and remain counted, so do not compare its aggregate with an official score without reconciling that policy. Optional citation validity and its gate are separate from answer exact match/F1.

The CLI reads saved local files and makes no network or model calls. It has no ATLAS/runtime dependencies. Reports retain question IDs and input/scorer hashes but omit answer/context text and absolute input paths. Review identifiers and inputs before publishing. [Installation evidence](../../reports/reading-qa-installation.json) records actual standalone CLI runs; genuine second-team use and broader datasets remain unverified.
