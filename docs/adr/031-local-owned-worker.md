# 031 — Own one baseline worker in a local API lifespan

Date: October 19, 2026
Status: implemented and checked locally; not a public hosting profile

## Requirement

Free hosting cannot be planned around a separately billed background worker. Before changing the public access or storage boundary, establish whether the existing database queue and baseline child can run under one server lifecycle. Keep the usual separate API/worker topology available.

## Decision

Add an explicit loopback launcher with one lifespan-owned worker thread, a separate SQLite engine for its queue, and the existing isolated baseline child. The factory receives a concrete database file and explicit local principals. It refuses inherited database, managed-auth and model-job configuration before creating storage. The launcher uses existing owner-private credentials and binds only 127.0.0.1. It does not generate a public login or deploy anything.

The worker is started once. Between steps it waits on a stop event. Shutdown requests a stop, waits for an already-entered step, and disposes storage only after the thread exits. Baseline computation uses the existing bounded child protocol with a ten-second deadline. An unexpected queue-loop failure leaves the worker failed rather than silently restarting it. Readiness requires both the existing database/schema checks and a running worker; liveness remains separate. Ordinary job execution errors retain the existing queue retry/fencing behavior.

The controller is not a scheduling or failure-containment service. Its thirty-second join timeout raises if the thread remains active; it does not falsely claim a graceful stop or close storage beneath that thread. The non-daemon thread can keep the process alive. Database calls, publication and platform suspension are outside the child execution deadline. An external supervisor is still needed for hard process termination and recovery. Uvicorn's installed signal handler completes lifespan shutdown and then may re-raise SIGTERM; the HTTP recorder therefore checks the completed-shutdown log marker as well as the process status, rather than assuming exit code zero.

PostgreSQL stays on the existing separate-service role boundary. Co-locating API and worker database privileges would require a different threat-model decision; this SQLite experiment does not validate it. AI extraction, retrieval, prompts and publication semantics are unchanged, so their pipeline versions are unchanged.

## Evidence and limits

Nine new cases check real child completion through the API, local restart, pending review preservation, tenant/auth checks, refusal of paid submissions, a failed worker's fixed readiness response, graceful active/idle stop, lifecycle reuse refusal, configuration rejection and skipping a pre-existing queued model job. Mixed-pipeline scheduling uses controlled computation; the end-to-end case executes the actual child.

The latest full native run passed 402 tests and skipped 18 optional PostgreSQL groups. The first full run had one failure in the existing queue API test: it observed a running job after process_once returned. The isolated check and subsequent full run passed without changing that test or queue logic. The remaining synthetic row had an expiring lease; the underlying cause of that first failure was not established. Do not describe this as proof of absence of timing faults. Its original failure remains in the session output; the final JUnit records the successful rerun.

The reproducible HTTP recorder launches the actual loopback CLI twice. A real isolated job completes on its first attempt with eight requirements and fourteen publication-validated citations, all pending review; authenticated results survive the SQLite restart. Anonymous access is 401, another tenant's result is 404, and a model submission is 503. Both launches complete lifespan shutdown under SIGTERM. The recorder initially rejected Uvicorn's signal status despite successful shutdown; inspecting the installed handler led to the explicit marker/status check described above.

This is not free-provider execution, managed login, anonymous public sessions, durable cloud storage, a container refresh, PostgreSQL validation or a production recovery target.
