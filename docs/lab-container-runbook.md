# Synthetic lab image verification

The dedicated image packages the fictional lab rather than exposing the private bearer-token service. It accepts only the pinned seed and constrained reviews. Session and review history disappear on restart by design.

From the repository root with the installed Docker engine running:

```sh
PYTHONPATH=src .runtime/bin/python scripts/verify_lab_container.py
```

On this Mac, pass --docker /Applications/Docker.app/Contents/Resources/bin/docker when that CLI is not on PATH. The verifier downloads public build dependencies when absent from cache. It creates no hosted service, paid model call, repository upload or external message. It generates a strict allowlisted build context and private logs/JUnit under var/lab-container, then uses an immutable image ID for all checks. Source/supporting files must remain unchanged during the run. The engine's own image/cache storage remains Docker-managed.

The verifier starts one uniquely named test container with no host port and network none, a read-only root filesystem, UID 10001, dropped capabilities, no-new-privileges, one CPU, 64 PIDs and 512 MiB memory with no extra swap. Only small tmpfs paths and three read-only verification files are mounted. It runs dependency checks, 32 focused Linux tests and real HTTP inside that namespace, restarts the same container and verifies intentional state reset plus a new real analysis. Its finalizer removes the test container after startup, including on later test failure. Engine/host failure can still prevent cleanup; do not use a broad prune command to resolve it.

Network isolation is checked by Docker configuration, down non-loopback devices and an empty IPv4 route table. Kernel tunnel devices may exist while down. No connection to an external test address is attempted. Reading JUnit through exec avoids relying on archive-copy visibility of tmpfs content. Private command stderr/build/test/server logs are retained for diagnosis.

The old session cookie crosses the restart only through captured subprocess output and stdin; it is removed before public reporting and is never passed on the command line or written to the report. Do not print raw driver output yourself. The local report contains counts, outcomes, constraints, image/source identities and served asset hashes, not session tokens or result payloads.

reports/synthetic-lab-container.json records the latest complete run. Its observed cgroup peak is not process RSS, a production load result or an invoice cap. swap_limit_bytes records Docker's combined memory-plus-swap setting, set equal to the memory limit to allow no additional swap. Image architecture and Python version are explicit; another architecture needs its own execution evidence.

The image is retained as atlas-synthetic-lab:validation for review. Its entry refuses implicit startup: an operator must provide ATLAS_LAB_CONTAINER=1, ATLAS_LAB_ORIGIN and an optional valid PORT. The intended hosted origin must use HTTPS; the existing create_lab validation allows plain HTTP only for loopback tests. No public run command is provided here because source visibility, provider usage/limits and hosted acceptance remain unresolved. Do not mount real documents, cloud credentials, a Docker socket or the private database into this lab.

Repeat the full native gate separately when core code changes:

```sh
PYTHONPATH=src .runtime/bin/python -m pytest -q \
  --basetemp=var/lab-image-native --junitxml=var/lab-image-native.xml
```

Local packaging does not validate a provider's filesystem, TLS, proxy, shutdown, billing or cold-start behavior. The desktop/mobile Chromium workflows in ADR 034 were separate native checks, not browser-in-image checks. The full durable review service and its PostgreSQL role boundary remain a separate deployment profile. ADR 035 records the actual measurements, initial verification corrections and remaining gates.
