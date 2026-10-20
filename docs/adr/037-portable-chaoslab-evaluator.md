# ADR 037: install CHAOSLAB without the application

Date: October 20, 2026. Status: local wheel and clean-environment checks passed; remote CI pending.

CHAOSLAB had separate scoring code but still required the combined dependency setup. Comparison fingerprints also read files relative to the caller's directory. An installed scorer would fail to find them; the baseline source digest could hash an empty tree. A separate package should not borrow provenance from an unrelated working directory.

Add a setuptools project alongside the existing package. Its `chaoslab-eval` wheel installs `chaoslab-compare` and declares no runtime dependencies. Keep the combined project for ATLAS integrations and historical report commands. Scoring rules, golden expectations and archived model reports are unchanged.

Comparison fingerprints now read the loaded package files. The broader digest uses the loaded source tree in this repository and the installed CHAOSLAB package elsewhere, retaining repository-relative logical names. An installed digest does not cover external adapter code and is not signed or loaded-bytecode attestation. The report states that scope.

The verifier stages Python files and build metadata, builds locally and installs without a package index into a fresh environment. Outside the source tree it checks that ATLAS, FastAPI, SQLAlchemy and pytest are absent. An unchanged controlled output passes. Corrupting a citation produces a regression and exit code 1; removing an attempt stays unpaired and exits 1. Failed comparisons still publish reports. A separate trusted adapter also runs through the installed child process. The [package report](../../reports/chaoslab-package.json) binds the source and wheel used.

The full native suite passed 462 tests, with eighteen optional PostgreSQL groups skipped. Twenty-four focused provenance/comparison tests passed. These results establish an installation boundary, not a second application, independent benchmark authorship or general model quality. ATLAS retrieval/database probes still need their own dependencies. Process controls are POSIX-specific and retain the user's permissions. No registry upload was performed. Wheel bytes identify this build; byte-for-byte reproducible builds are not claimed.
