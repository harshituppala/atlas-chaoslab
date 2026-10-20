# ADR 029: bound worker output while it is produced

Date: 2026-10-19. Status: implemented and verified on the native POSIX host.

## Problem and decision

The worker previously used subprocess.run(capture_output=True) and checked stdout size after the child exited. That limits acceptable results but cannot prevent a verbose/stuck child from consuming parent memory first; stderr had no independent byte budget. Replace both baseline and operator-enabled model worker calls with a small shared POSIX supervisor that pumps stdin/stdout/stderr concurrently through nonblocking pipes and selectors.

The parent checks encoded input before spawn (1,500,000 bytes), retains at most 8,000,000 stdout bytes and counts/discards at most 65,536 stderr bytes. An incoming read uses a bounded 65,536-byte chunk, and over-budget data is rejected before being appended. Exact limits are accepted. Byte budgets and the monotonic deadline are constructor-call arguments, not document-owned settings. Parent buffers, decoding/copying, serialization, child allocation and kernel buffers add memory; these controls are not a total RSS cap.

A new session/process group belongs to each invocation. The parent drains/writes all pipes concurrently, including when the child fills stdout before reading stdin. Deadline and output-budget failures kill the invocation's process group, wait for the root, close pipes and return fixed error categories. Even normal root completion triggers same-group descendant cleanup. A child closing pipes while continuing to run is still subject to the deadline. Early stdin closure does not deadlock or leak the child. Existing baseline/model result validation and queue publication fences remain authoritative.

## Failure and paid-execution semantics

The default baseline wall deadline remains 120 seconds and the model deadline remains 300 seconds. The generic supervisor permits explicit finite positive deadlines up to 600 seconds, and bounded byte-budget arguments. Baseline timeout handling retains the existing bounded retry/attempt policy; byte-budget failures are resource-budget failures. Model jobs remain one attempt and never automatically replay paid work. Killing a model child cannot undo a provider request; the existing uncertain-billing timeout message, conservative reservations and private receipts remain the operator's source of truth. This milestone neither configures credentials nor enables new paid execution.

stderr content is never returned by the supervisor, put into public reports or included in its fixed errors; only its byte count is returned on success. Overly verbose legitimate diagnostics now fail closed rather than growing memory. Do not raise limits to mask a malfunction without investigating privately. The parent still receives bounded source-bearing stdout for normal validation/storage, so this is a resource boundary rather than a redaction system.

## Containment limits

These are trusted implementation children handling untrusted document data, not arbitrary hostile-code sandboxes. Children retain filesystem/network permissions and can create files or use resources beyond these pipes. Descendants that escape the new process group/session are outside cleanup's guarantee. Parent SIGKILL/host failure cannot run Python finally cleanup. Kernel-level uninterruptible operations and process launch are not independently preempted by the selector loop. There is no filesystem/CPU/network/memory isolation or complete process-tree containment claim. This implementation targets the repository's POSIX Mac/Linux runtime, not Windows.

Successful extraction/model semantics, prompts, citations and fixtures remain unchanged, so pipeline versions are unchanged. Failure supervision changes are separately documented and verified. The CHAOSLAB adapter subprocess runner and document parser are separate existing boundaries; they are not silently described as migrated to this supervisor.

## Executed verification

Eighteen new tests execute actual Python children for simultaneous pipe pressure, exact byte boundaries/nonzero exits, early input close, pre-spawn input refusal, stdout/stderr overflow, deadlines after pipes close, root reaping and same-group descendant heartbeat cessation after timeout and normal exit. Later invocations still succeed. An actual baseline child returns eight pending assessments. The model wiring and billing-message tests use controlled responses/errors and make no provider calls.

The full native suite passes 384 tests with 18 optional PostgreSQL skips; Ruff checks and all 124 Python format checks pass. scripts/verify_worker_supervision.py checks the actual JUnit results and executes a fresh SQLite queue: a one-attempt deadline job fails without a result, and a following real isolated baseline job succeeds on its first attempt with eight requirements, 14 valid citations and all reviews pending. reports/worker-supervision.json identifies executed checks, source/JUnit hashes and the honest post-execution scope of test-source hashes. Queue-exercise source hashes are frozen before and checked after that exercise. No new inference, remote CI, browser, Linux image/container or cloud validation occurred.
