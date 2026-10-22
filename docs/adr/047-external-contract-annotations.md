# Evaluate against external contract annotations

The existing RFP fixtures were written alongside the projects. They are useful regression checks, but their authorship limits the strength of an accuracy claim. ContractNLI offers external labels and evidence spans for a different, clearly defined task. The owner's dataset-terms approval covers the private download and evaluation; it does not turn the corpus into public demo data.

The importer pins the official archive digest and reads a single fixed development member without extraction. This also handles a nonportable PDF filename found during the archive audit without relaxing filesystem-path safety. Size limits, duplicate-member/JSON checks, source bounds and complete annotation checks reject ambiguous inputs. Runtime admission remains active under optimized Python. Neither test nor training data is loaded.

The new task reuses CHAOSLAB's existing adapter process, deadline and output budgets. Hypotheses and candidate spans cross that boundary; expected choices and evidence indexes stay in the judge. Label, evidence and joint correctness are separate. Failure and omission remain in denominators. A real source span cannot excuse a wrong classification, and a correct label cannot excuse missing evidence.

The first run uses a constant `NotMentioned` reference. It scored 423 of 1,037 development claims correctly, with zero evidence recall. This is a class-distribution floor, not a language-model result. The report preserves those limitations, per-class counts and source/data fingerprints. No paid model call was made.

Thirty-five focused controls passed; the full native suite passed 701 tests with eighteen optional PostgreSQL groups skipped. A fresh dependency-free 0.1.2 wheel ran a fictional contract reference and CLI check without ATLAS, alongside the existing eight comparison controls. The external corpus was not used in that installation check. The model adapter and untouched-test evaluation remain future work; no existing RFP expectations or model reports were changed.
