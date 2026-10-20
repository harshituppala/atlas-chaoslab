# 035 — Verify a dedicated synthetic lab image under explicit local constraints

Date: October 20, 2026
Status: locally executed on Linux arm64; not deployed

## Requirement

The synthetic API and browser had native-machine evidence, but no current Linux packaging/runtime evidence. The full-service image mounts the private API and copies more demo/report inputs than this limited lab needs. A deployable artifact must preserve the synthetic-only entry and disclose its deliberate loss of state on restart.

## Decision

Add Dockerfile.lab with official Node/Python image-index digests pinned from the public registry. It builds only the dedicated React lab entry and copies Python source, locked dependencies and the one pinned fictional fixture into the runtime. The private frontend, reports and operator files are not copied. Python runs as UID 10001 with bytecode writes disabled.

A separate container entry requires ATLAS_LAB_CONTAINER=1 and an exact ATLAS_LAB_ORIGIN before creating the lab app/listener. PORT is validated. The app still refuses private database/principal/managed-auth/model configuration. The container entry binds its configured port on all container interfaces; this is not the loopback CLI and must not be run publicly without an approved hosting configuration. Proxy headers are not trusted to derive access settings; the origin is explicit.

The verifier constructs a 78-file allowlisted context under ignored var. It excludes Git history, host runtimes/caches, credentials, reports, user documents and sibling projects. Verification scripts/test files are separately mounted read-only and are not copied into the image. Immutable image identity and source-file manifests bind the checks; source/supporting input hashes are compared again before the local report is replaced. Docker-managed image/build cache remains in the existing engine's storage; context, logs and reports stay in the portfolio.

## Executed constraints and evidence

The actual Linux arm64 image used Python 3.12.15. Inspection and runtime checks verified UID 10001, a read-only root filesystem, no published host ports, Docker network none, all capabilities dropped, no-new-privileges, one CPU, 64 PIDs and a 536,870,912-byte memory limit. Docker's MemorySwap value is also 536,870,912, meaning no additional swap allowance; the report names this raw setting swap_limit_bytes. Writable /app/var and /tmp are small noexec/nosuid tmpfs mounts. No Docker socket, host credentials, workspace tree or persistent database was mounted.

Pip's installed-dependency check passed. All 32 focused synthetic-boundary/container-configuration tests passed inside the constrained image. These are not the entire backend suite inside Linux. The separate full native run passed 453 tests with 18 optional PostgreSQL skips. Ruff and 138 Python formatting checks passed.

Real HTTP inside the isolated namespace served the built page, two exact matching assets and expected policy headers. A real baseline child produced eight provisional requirements/fourteen valid citations. The driver checked cached repeat analysis, explicit human review, stale-version/conflicting-evidence refusal, separate-session empty state, private API absence, origin/host/body rejection and refused root-filesystem writes. After an actual container restart the old cookie/result were rejected; a fresh session completed another real analysis. Restart is deliberately a reset, not durable recovery.

Observed cgroup memory.peak after the focused tests and first HTTP exercise was 230,924,288 bytes (about 220.2 MiB). This includes cgroup-accounted memory/cache and test-driver overhead. It is not per-process RSS, representative load, build memory or a guarantee that every workload fits the limit. The test-owned container was removed; the image remains available locally by its recorded immutable identity.

## Corrections during verification

The initial build and 32 Linux tests succeeded, but Docker archive-copy could not retrieve the JUnit file on the tmpfs mount. Reading it through an exec process retrieved the actual artifact; no synthetic result was substituted. Private stderr is now retained when a captured verification command fails, and cleanup runs even if log collection fails.

The HTTP driver initially assumed the isolated namespace would contain only lo. Inspection showed down kernel tunnel devices and no IPv4 routes. The corrected check verifies loopback exists, every non-loopback device is down and the IPv4 route table has no routes, alongside Docker's network-none setting. It does not confuse interface names with connectivity or attempt external network traffic. Earlier failed artifacts remain under ignored var; the final report contains only completed evidence.

## Limits and next gates

Only the recorded architecture/runtime was executed. Public build downloads occurred; runtime checks had external networking disabled. Pinned base digests are not a vulnerability scan, signed build or cross-architecture proof. There was no browser inside the image, hosted TLS/Secure-cookie, reverse proxy, cold-start/usage billing or provider restart validation. Prior native browser evidence remains separately scoped.

The 512 MiB/CPU/PID/filesystem/network flags are local verification settings, not verified free-provider capabilities or an invoice cap. Parent/host failure and escaped-process limitations remain. Full durable managed-access service, exact publication approval and actual hosting acceptance are unfinished. No source upload, cloud provisioning or paid model call occurred.
