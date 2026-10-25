# Show the evaluation alongside the review sample

The public review lab made ATLAS's basic workflow available, but left visitors unable to inspect what CHAOSLAB contributes. The private workbench already displayed comparisons; linking only to source reports made that evidence difficult to find.

The lab now has a separate Evaluation results page. It bundles four existing public reports and the authored transfer cases. Visitors can compare the rule-based baseline with a recorded model run, then inspect a wrong threshold decision or a failed extraction against the actual fictional input. The three-scenario comparison and twelve-case transfer experiment retain separate denominators and their development-set limitations.

This page is read-only. Direct navigation does not mount the review application, initialize a temporary session or request an API. It runs no model, evaluator or adapter. The Docker build copies only the named public reports and synthetic dataset into its frontend build context; private observations and external contracts are excluded. React renders source text as text, without HTML interpretation.

Dataset-version mismatches prevent the paired comparison from being described as comparable. The transfer baseline must also cover the authored case count. This is a presentation check on versioned local artifacts, not independent attestation of the original model execution. The source reports retain their own provenance and limitations.

Desktop and phone browser checks cover counts, failure selection, source text, navigation, storage/cookie absence and absence of API requests. The existing review, stale-write, controlled-capacity and expiry workflows remain required. Container and hosted acceptance are recorded separately when executed; a local browser pass does not establish a deployed update.
