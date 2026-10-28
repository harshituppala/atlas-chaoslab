# A second saved-answer format and a smaller UI controller

October 28, 2026.

CHAOSLAB now accepts SQuAD-style question/context datasets and saved question-ID-to-answer dictionaries through `chaoslab-qa`. This exercises reading comprehension outside ATLAS's requirement/relation schema without adding a provider SDK or requiring an application server. The documented format and evaluation conventions are described by [Stanford's SQuAD project](https://rajpurkar.github.io/SQuAD-explorer/) and its [official evaluator](https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/master/evaluate-v2.0.py). No dataset was downloaded; the archive-handbook example is authored and fictional.

Missing predictions explicitly score zero and remain in the denominator, including missing abstentions. The CLI reports paired changes, exact match and token F1; it does not implement no-answer probability tuning or claim official leaderboard equivalence. Optional source-span sidecars are a CHAOSLAB extension. A correct answer with an invalid span fails the citation gate, while an incorrect answer with a valid span still fails answer quality. Malformed experiments exit 2 without replacing a previous report; completed quality failures write a report and can exit 1.

The package is version 0.1.5. Completed ContractNLI results still require their previously pinned 0.1.4 wheel/source. Nothing in this change reruns, replaces or retunes those cohorts. Fresh package verification executes four new CLI controls outside the source tree without ATLAS, in addition to the existing installation controls. This is another artifact-format integration, not independent adoption or an externally maintained second application.

The workbench's evaluation rendering/types now live in EvaluationView. The application controller still owns authentication, requests, job state and evaluation disclosure state. This is a focused extraction, not a redesign or a new state-management framework. All twelve connected browser workflows, including controlled unknown-quality/cost displays, pass afterward.

The shorter documentation route distinguishes the finished free release from optional always-online private hosting. Participant tasks, owner exercises and an RFP-specific evaluation protocol are now written down. They are preparation: independent annotations, real user observations and an observed owner walkthrough remain human gates. No testimonials, time-saving estimates or domain accuracy were invented.
