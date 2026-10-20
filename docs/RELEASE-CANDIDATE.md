# Source publication review

The project owner has approved publishing ATLAS and CHAOSLAB as a public GitHub repository. The requested documentation edit is complete, and the source has been published. The previously reviewed snapshot remains unchanged; the editorial candidate is prepared separately.

## Published source

The review workbench and evaluators, their tests, synthetic examples, measured reports, dependency locks, deployment templates and documentation. The editorial pass updates stale descriptions and removes internal chat coordination from the reader-facing pages. It does not add the newer synthetic lab or change application code, tests, datasets or benchmark results.

Credentials, local databases, raw provider output, installed runtimes, private workspace material and the earlier local Git history stay excluded. A pattern scan helps identify accidental disclosure, but is not a complete security or licensing audit.

## What was checked

The reviewed source passed its native Python suite, with the optional database groups skipped. Separate browser, PostgreSQL, container and live-model reports describe their own runs. The editorial candidate preserves the reviewed executable files and measured artifacts byte for byte. All relative links across its Markdown files resolve.

The exact inventory, source revision and file hashes belong in the private release manifest. They support release verification rather than serving as project descriptions.

## Limits

The model tests retain incorrect threshold reasoning, a benign-filter failure and a hostile-source citation. This is a local application with development evaluation data; neither hosted operation nor general contract accuracy is established. The [public repository](https://github.com/harshituppala/atlas-chaoslab) has been checked against the reviewed release. The initial workflow-permission error was resolved through GitHub’s consent screen. Both jobs in the [first CI run](https://github.com/harshituppala/atlas-chaoslab/actions/runs/39451999129) passed. Hosted application acceptance remains unfinished.
