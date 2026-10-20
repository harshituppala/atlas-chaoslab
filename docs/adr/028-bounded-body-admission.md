# ADR 028: bound concurrent request-body processing

Date: 2026-10-19. Status: implemented and verified on the native host.

## Requirement and decision

The existing body middleware enforces per-request bytes, chunk count and receive deadline before parsing. Those controls alone allow an unbounded number of callers to hold individually valid buffered bodies. Add a nonblocking process-local admission budget, default eight requests, for POST/PUT/PATCH. Use a thread-safe bounded semaphore so a middleware instance can safely reject excess work without an awaiting queue or dependence on an event-loop-specific semaphore.

Saturation returns a fixed 503 with Retry-After: 1 before receive is called. GET/HEAD/other bypass methods retain their existing path, including health checks. Acquire before buffering and hold admission until the downstream app returns, because its parser/handler still needs the raw body. A finally block removes atlas.body from the request scope and releases capacity on ordinary completion, oversized/chunk-flood rejection, deadline, disconnect, receive/application/send failure or cancellation. The temporary chunk list is cleared after assembly; response/framework references outside this scope are not controlled by this cleanup.

The existing 1,500,000-byte, 10-second and 10,000-message defaults remain. Capacity is a constructor setting bounded to integer 1..128; the API currently uses the default eight. This changes request admission under contention, not successful analysis/extraction/model semantics, so pipeline versions remain unchanged. Rejected requests do not reach authentication, parsing, upload storage or job admission. No automatic client retries are introduced. Clients retrying a write should preserve its idempotency key where the route supports one.

## Limits and operational tradeoffs

This is per middleware instance/process, not a shared deployment budget, tenant rate limit, fair scheduler, connection limit, total memory cap or production denial-of-service defense. Additional API processes multiply admitted work. The limit applies before authentication, so one client can occupy the shared slots. The receive deadline limits body ingestion time, not downstream response time. Slow database/handler/response behavior can retain slots after the body is received; worker execution, queue admission, database timeouts and reverse-proxy/server connection/body limits remain separate controls.

Incoming chunks, server/network buffers, JSON objects, document parsing, database rows and responses have additional memory costs. A maximum accepted body size and eight slots do not establish an RSS bound. Health bypass keeps this middleware from blocking health requests but cannot guarantee health under event-loop starvation or broader host failures. A 503 retry hint does not guarantee recovery after one second. The fixed response contains no submitted input or identity information and the existing outer privacy middleware still sets no-store/security headers.

## Executed evidence

scripts/verify_body_admission.py runs an actual in-process ASGI concurrency exercise with 200 synthetic 65,536-byte requests, deliberately holding accepted downstream requests. Eight enter, 192 receive 503 without receive/body reads, peak downstream occupancy is eight and only 524,288 first-wave payload bytes are read. A GET health probe returns 200 during saturation; after release all eight slots accept a second wave, and raw scope-body fields are gone. Source/runner bytes are frozen before and checked after execution in reports/body-admission.json. This is deterministic ASGI concurrency evidence, not HTTP-wire load, measured memory or cloud validation.

Eighteen new regression cases verify the three write methods, pre-read refusal, health bypass, malformed capacity settings and slot cleanup on all listed failure/cancellation paths. The real FastAPI app's default eight-slot middleware is saturated through blocked receives; HTTPX ASGI requests verify 503, no-store/nosniff/retry headers and health response, then restored ordinary authentication after cancellation. The three original body-budget tests still pass. Full native backend verification: 366 passed, 18 optional PostgreSQL skips. Ruff check and all 121 Python format checks pass. No new browser/container/Linux image, proxy, distributed load, remote CI, model call or deployed service validation is claimed.
