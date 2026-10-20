# Request-body admission

The API admits at most eight concurrent POST/PUT/PATCH requests per process through body buffering and downstream response completion. Excess requests receive 503 and Retry-After: 1 without their bodies being consumed by the middleware. Existing byte/chunk/deadline budgets remain in force. GET health checks bypass this budget.

## Diagnose saturation

A fixed "Request body capacity unavailable" response indicates this process's admission slots are occupied. Check for slow body senders, handlers, database operations or responses before increasing capacity. The limit is shared before authentication; it provides no tenant fairness or connection throttling. Check health/readiness separately, and do not treat a healthy GET response as evidence that writes or workers have available capacity.

A failed request may originate elsewhere too: 408 means the receive deadline was exceeded, 413 means a body/chunk or route-specific upload budget was exceeded, and other 503 responses may indicate identity/database dependencies. Never log bodies, credentials or raw exception contents to investigate. Existing metadata-only request traces may record method/route/status when tracing is enabled; no new live occupancy dashboard or distributed metric is added here.

Busy-response writes have not reached this middleware's downstream app. Retry with backoff and the same idempotency key on routes supporting one, rather than generating duplicate keys or assuming Retry-After guarantees success. Do not automatically replay non-idempotent operations after unrelated transport/response errors.

## Reproduce the measured exercise

From the repository root:

```sh
PYTHONPATH=src .runtime/bin/python scripts/verify_body_admission.py
PYTHONPATH=src .runtime/bin/python -m pytest -q tests/test_body_limits.py tests/test_body_admission.py \
  --basetemp=var/pytest-body-admission
PYTHONPATH=src .runtime/bin/python -m pytest -q \
  --basetemp=var/pytest-body-admission-full --junitxml=var/body-admission-tests.xml
```

reports/body-admission.json records actual in-process results and before/after-checked source hashes. The native full-suite result is 366 passes and 18 opt-in PostgreSQL skips at this milestone. The diagnostic uses one limiter with a controlled hold/release barrier and synthetic payloads; it does not open a listening service, generate internet traffic, call a provider, prove HTTP-server/backlog behavior or measure peak RSS. Existing source-publication approval and deployment validation remain separate gates.

The API uses the middleware constructor's default capacity. Changes to that default, worker counts or process replicas need a new validation run and memory/database review. Host/proxy connection limits, per-tenant rate/fairness controls, downstream deadlines and service-wide overload management remain future deployment work. The current local static-token API must not be exposed publicly.
