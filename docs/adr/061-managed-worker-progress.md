# Stop the workbench when its worker stops making progress

The first supervisor watched process exit. A worker could stay alive while its queue loop was blocked, leaving the API available and jobs apparently stuck. A lease-renewal thread alone cannot prove that analysis is progressing.

The managed entry point now starts a baseline-only worker wrapper. The queue loop writes to a private inherited pipe before each processing attempt. The supervisor gives it 150 seconds to report again, allowing the existing 120-second bounded analysis plus database and cleanup time. Startup has the same deadline. A silent, closed or malformed progress stream stops both services with a failure exit. There is no automatic restart or paid-model retry.

Only the worker inherits the write descriptor. Its analysis subprocesses close unrelated descriptors, and the wrapper marks the descriptor non-inheritable. This is a liveness check between trusted processes, not protection against a malicious worker that deliberately forges progress. Existing job leases still fence result publication. After whole-container shutdown, the database retains the job for the existing recovery rules.

## What was executed

Eleven new native checks cover a genuinely stopped worker, a silent worker, a closed pipe, invalid bytes, continued healthy progress, operator shutdown, invalid deadlines and an actual baseline queue worker. Together with the earlier supervisor controls, twenty-six focused checks passed. The full native suite passed 940 tests with eighteen optional PostgreSQL groups skipped.

The actual managed image was then built and exercised against a separate PostgreSQL TLS container. Its API passed database readiness and refused unsigned access. Its real worker completed the fictional queued analysis; an external authenticated test client checked eight requirements, fourteen source spans, a saved review, audit history, stale-write refusal and workspace separation. The test then sent SIGSTOP to the actual worker. At the production 150-second deadline the supervisor began shutdown; the container exited with failure after about 160 seconds, including the ten-second shutdown grace. The saved review remained readable from the independent database. [The report](../../reports/managed-image-tls.json) records the image and source fingerprints.

The full image build exposed an older packaging gap: the frontend imports reports relative to `apps/web`, but its build stage had flattened that directory and omitted those inputs. The build now preserves the directory layout and copies the named public inputs. Both the explicit managed target and the default bearer target build. Ordinary default builds still use the original API command; the managed entry point is opt-in.

## Scope

The acceptance container used the host's non-root UID so it could read private mounted settings. It had a read-only root, dropped capabilities, temporary scratch space and no model or AWS credentials. Docker administrators and same-user processes remain trusted. The API's managed sign-in was configured with fictional endpoints; no Cognito session was created inside this image. The external test client used synthetic bearer identities in a separate in-process API, while the packaged worker consumed the shared database queue. Database TLS, service lifecycle and job processing were exercised; hosted identity, public ingress and a signed browser review inside the image were not.

The owner chose free hosting: the public fictional lab stays online and the full private workflow runs locally. A paid always-online private service is outside the current release scope. Its additional ingress, identity and backup acceptance would be a separate deployment decision.

## Reproduce

```sh
docker build --target managed -t atlas-managed:validation .
PYTHONPATH=src .runtime/bin/python scripts/verify_postgres_tls.py \
  --managed-image atlas-managed:validation
```

The runner uses a cached PostgreSQL image; CI pulls that database image explicitly before running it. The freeze check takes about three minutes because it uses the production deadline. No completed model cohort is rerun. Default invocation without `--managed-image` retains the separate TLS-only check. The new CI job builds both targets and repeats the managed-image acceptance on Linux; its result is recorded in GitHub Actions separately from this local proof.

The first Linux attempt failed during database startup. The test originally mounted its private host directory directly, but the database runs under a different numeric user on Linux. The fixture now mounts a readable material subdirectory inside the private outer directory, and checks access as the actual database user before startup. The host directory remains private; no production database permissions changed.
