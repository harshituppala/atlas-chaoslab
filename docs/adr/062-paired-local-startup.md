# Start and stop the local review workspace together

The documented local setup needed separate API and worker terminals. Starting only the API left analysis jobs queued, and closing one terminal left the other service running. The owner’s free-hosting choice makes the local workbench the full recording workflow, so startup should be straightforward and repeatable.

`make local` now starts both services through the existing supervisor. It reserves a loopback listener before creating or opening the workspace, then passes that exact descriptor only to the API. An occupied port is refused before a new workspace is created. A private file lock also prevents two launchers from using the same workspace.

The workspace keeps its SQLite database and reviewer token across restarts. Existing credentials must be a private, bounded regular file owned by the current user. Invalid or linked files are refused without replacing them. The API receives the reviewer identity; the worker receives only its database connection and baseline-only settings. Ambient AWS credentials, model settings, proxy configuration and managed-login settings are omitted. The existing queue-loop watchdog also applies.

## Verification

Eight new native controls passed: repeated startup retains credentials and the populated database, inherited privileges are absent, a second workspace lock is refused, invalid/public/linked/duplicate-key credentials remain untouched, workspaces stay private and inside `var`, and linked database/scratch paths are refused.

The actual launcher then passed a real Chromium PDF/DOCX upload and source-backed review. Both API and worker stopped and were reaped. After reopening the same workspace, the credential, full analysis, audit events, uploaded-document records and both original byte hashes matched. The listener was released after each stop. A competing launch on its occupied port failed before creating a workspace. [The record](../../reports/local-workbench-launcher.json) binds the source and browser evidence.

The pipeline and model evaluation are unchanged. This is one synthetic static reviewer over loopback HTTP and SQLite. It does not establish external sign-in, browser-session invalidation, database TLS or hosted recovery. Same-user processes remain trusted. The earlier separate-profile launch commands remain available, and existing databases outside the selected workspace are untouched.

## Reproduce

After building the interface:

```sh
make local
```

Open http://127.0.0.1:8000 and connect with the long key in `var/local-workbench/credentials.json`. Keep it out of recordings. Ctrl+C stops both processes; starting again reopens saved work.

For isolated verification, run `PYTHONPATH=src .runtime/bin/python scripts/verify_local_workbench.py`. Node, pnpm and Chromium must already be available. The verifier creates its own private workspace, starts the real launcher twice and stops its own processes. It does not modify the normal local workspace or call a model.
