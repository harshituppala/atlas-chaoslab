# Preserve contract observations for later scoring

A report of aggregate scores cannot show what an adapter actually returned. Calling a model again to reconstruct those responses introduces new answers, latency and cost. ContractNLI therefore gets an optional private journal and a separate replay mode before a model adapter is added.

The journal binds each document ID to the exact adapter-input digest. It records returned output before prediction admission, so an unusable response remains an observed failure when rescored. An invocation failure has a separate status and no exception text. Expected annotations stay in the judge. Recording errors stop publication; they cannot quietly become model errors.

A run uses a new directory under ignored `var/`. Files have owner-only permissions, bounded lines and a total byte budget. Each write is flushed to disk. A final record covers the preceding bytes and count, followed by an atomic rename and directory flush. Interrupted or source-changing runs remain partial. Replay admits the complete file, pinned dataset and all input fingerprints before scoring. Duplicate or missing documents, ambiguous JSON, symlinks, broadly readable files and inconsistent checksums are refused.

The public report contains an observation digest and count, the original scorer fingerprint and the scorer used now. Raw responses stay private because an adapter can quote contract text. Replay never imports the adapter named in the journal. Checksums identify saved bytes, but do not authenticate who produced them; a compromised local account can rewrite both data and hashes. Adapters continue to run with the user's privileges.

Twenty-eight new controls cover valid, omitted, malformed and failed responses, corrupted/partial journals, changed inputs, private file admission and recording failure. The full native suite passed 729 tests with eighteen optional PostgreSQL groups skipped. A clean 0.1.3 wheel also captured and replayed a fictional claim with an unavailable adapter and no ATLAS installation.

The complete development reference was captured once and replayed without adapter execution. Both scorings produced identical result objects for 61 documents and 1,037 claims: 423 correct labels and no retrieved evidence. No model was called and neither training nor test JSON was loaded. This adds reproducibility, not a new accuracy result. The [task guide](../contractnli-evaluation.md) links both aggregate reports and the commands.
