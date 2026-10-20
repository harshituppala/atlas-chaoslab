# Recorded evidence room

This is a separate static viewer of synthetic saved results. It does not replace the local workbench or claim live AI processing, approvals, authentication or full-stack deployment. All recordings remain pending review. Known benchmark failures are retained.

## Build and inspect from a source checkout

With the existing pinned frontend dependencies installed:

```sh
cd apps/web
pnpm build:replay
python3 -m http.server 8127 --bind 127.0.0.1 --directory dist-replay
```

Open http://127.0.0.1:8127 locally. Stop that server before running `pnpm test:replay`, whose configuration owns a temporary server on the same port and refuses to reuse somebody else's process. The tests use Chromium from the installed Playwright browsers. `pnpm build` continues to build the actual workbench into dist, separately. Never deploy the whole repository, its var directory, the local API, credential files or private recording to serve this viewer. Only the reviewed dist-replay output belongs in a static hosting artifact; publication remains pending.

## Regenerate recordings locally

From the repository root, with the original ignored recording retained:

```sh
PYTHONPATH=src .runtime/bin/python -m atlas.replay
```

This executes the deterministic municipal baseline, validates its publication invariants, and verifies/projects the saved residency result against reports/browser-model-validation.json. It never makes a provider request. The fresh baseline timestamp changes on regeneration; the model timestamp remains historical. The committed replay-data.json supports builds when the private original is unavailable. Do not substitute production/customer data. Editing a fixture or a bundled recording invalidates old build/test hashes; rebuild and reverify before recording fresh evidence.

## Record local verification

```sh
PYTHONPATH=src .runtime/bin/python -m pytest -q --junitxml=var/replay-backend.xml
cd apps/web
pnpm build:replay
pnpm test:replay
cd ../..
PYTHONPATH=src .runtime/bin/python scripts/record_replay_validation.py
```

The recorder reads the actual private JUnit/Playwright outputs, refuses failing/incomplete browser runs or backend failures and writes a public aggregate with source/build/report hashes. These are post-execution on-disk hashes, not frozen execution provenance, remote CI or signed attestation. It does not replace visual inspection of reports/replay.png. The 18 default PostgreSQL skips require their separately documented integration environment; static replay tests establish no PostgreSQL or cloud behavior.

A future free-host deployment must use an explicitly approved public artifact, validate the actual hosted workflow/HTTPS/headers/asset paths, and retain prominent recorded-demo labeling. No deployment or new hosting account was created for this milestone.
