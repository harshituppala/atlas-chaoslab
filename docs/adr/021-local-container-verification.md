# ADR 021 — Execute the image before claiming container support

Date: 2026-10-16

## Requirement and decision

Local macOS tests cannot establish that the packaged Linux application runs. Build the existing multi-stage image, then verify its actual source/dependencies and execute the backend suite and a real HTTP/worker/restart workflow as its configured nonroot user. Use the immutable image ID after build. Do not mount host source, credentials, the Git repository, AWS configuration or the Docker socket into the verification containers. Disable external networking during execution; loopback remains available.

`python -m atlas.models.provenance` is not an operator command; the verifier directly imports its source-manifest function inside the image and compares file hashes to the host. Include pyproject.toml in the runtime so this bounded source manifest is complete. Tests and the deterministic fixture generator are mounted read-only solely for verification. The production image need not contain its test suite or fixture-generation tool.

CHAOSLAB's baseline runner previously handled Git command failures but crashed when the executable itself was absent. Missing Git now gives null revision/dirty state rather than an invented commit or cleanliness claim. Its independently frozen source digest remains required. This changes report availability/provenance, not extraction or model execution semantics, so pipeline versions remain unchanged.

## Executed evidence

The first image built, but its Linux suite returned 253 passes, five failures and 18 skips. Four failures exposed missing-Git handling in the evaluation runner; one was a missing fixture-generator test asset. Preserve that initial JUnit privately. After correcting these issues, `scripts/verify_container.py` builds, checks dependency consistency, matches image source to host, runs the suite, and executes `scripts/container_workflow.py` using the same immutable image. The final measured outcome is in reports/container.json.

The HTTP exercise starts actual API processes, admits an idempotent baseline job, restarts the API while it is queued, runs the actual isolated worker, checks citations, races two authorized reviews, restarts the API again, and checks the saved decision and foreign-tenant refusal. Everything is synthetic and uses temporary SQLite. Paid model admission is explicitly disabled. Temporary containers and child processes are removed by the harness.

## Limits and next gate

This is Linux ARM64 execution on Docker Desktop, not an AMD64 or production host result. PostgreSQL integrations remain skipped in this particular suite; their separate native-cluster evidence is not container evidence. No live provider, embedding runtime, browser-in-container, managed identity login, image vulnerability scan, remote CI or AWS deployment was validated. Base-image tags can move; record the actual immutable resulting image ID. Hashes are local provenance, not signed attestations or proof against a malicious local operator.

The old Compose target still requires explicit migrations, restricted service roles, runtime connection configuration and a tested initialization sequence. Do not run its owner connection as the API or worker, weaken startup role checks, or call the Compose stack verified on the basis of this image-only milestone. Database backup/restore remains an additional recovery gate.
