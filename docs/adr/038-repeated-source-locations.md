# ADR 038: score repeated source text in its own segment

Date: October 21, 2026. Status: implemented and checked locally; remote CI pending.

The ingestion judge searched for the first occurrence of each expected quote in the entire extracted document, then checked its page. A repeated footer on page three was therefore marked wrong when the same footer appeared on page one. The parser had retained the right text and page coordinates; the judge was wrong.

A new three-page fictional PDF reproduces this with an empty middle page. The authored expectation keeps physical page numbers one and three. Two DOCX fixtures add split text runs, Unicode, tabs, breaks, a deleted revision and a table with a merged heading. Expectations were written separately from extraction results. The [first run](../../reports/ingestion-layout-before.json) passed two cases and rejected the valid repeated footer. Its older provenance field is a post-run source snapshot. The [corrected run](../../reports/ingestion-layout.json) passes all three with inputs frozen before execution and checked afterward.

Search within the expected source segment instead of taking the first global match. Quotes still cannot cross segment boundaries or borrow text from another page. Optional exact-text expectations check the DOCX reading policy, including omission of deleted revisions. Keep the original four ingestion cases unchanged; they still pass. ATLAS parsing, analysis semantics and pipeline versions are unchanged.

The runner now snapshots source, dataset and fixture bytes before execution, refuses publication if they change, and prevents the output from overwriting an input. Mutation tests check those boundaries and preservation of an older report. The initial four new command-level tests failed because their import stub affected pytest itself; scoping the stub to the ingestion module corrected the test harness. The full native suite then passed 471 tests, with eighteen optional PostgreSQL groups skipped.

Regenerating the three fixtures produced identical bytes on this machine. This does not establish identical PDF output across dependency versions. These same-author fictional cases check canonical text and source locations, not rendered reading order, table-row relationships, OCR or customer-document accuracy. No model calls were made. CI includes the new dataset alongside the original ingestion evaluation.
