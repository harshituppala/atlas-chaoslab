# ADR 015 — Persistent cumulative model-test reservations

Status: implemented locally; provider activation remains blocked.

## Requirement

The user authorized a cumulative USD 10 model-testing budget, including earlier known estimates and uncertain calls. Per-run ledgers alone cannot enforce this across restarts or simultaneous CLI invocations.

## Decision

Both live model CLI entry points reserve their configured worst-case token cost against one private `var/bedrock/campaign-budget.json` before creating the provider gateway. Offline planning does not initialize credentials or spend the authorization. Initialization is an explicit operator action after consent; missing, corrupt, duplicate or exhausted journals fail closed. New output names cannot bypass an existing campaign's ceiling. Each reservation identifies the resolved output path.

An OS advisory lock on a stable sibling file serializes cooperating threads/processes. The journal is replaced atomically, flushed, and its parent directory synced before a reservation returns. Files are private, bounded and kept under ignored var. A failed SDK setup or process death retains the entire reservation. There are no automatic refunds or authorization increases. Historical reviewed usage/reservations are carried in at initialization. Existing run-specific artifact reservations remain independently preserved.

## Evidence and limits

Tests cover independent competing processes, threads, restart/duplicate reservation refusal, nonfinite/negative amounts, corruption, private paths/symlinks and persistence failure. These are local filesystem checks, not provider billing proof. The macOS/POSIX implementation uses flock; Windows and network filesystem semantics are not validated.

This guards cooperating CLI tools against accidental cumulative overspending. A user or compromised local process can edit/delete the authorization or choose another file; direct SDK calls, console requests, provider pricing changes, tax, unrelated cloud resources and actual token-bound violations are outside this mechanism. No AWS account-level hard cap is established. Do not infer new paid-resource or agreement consent from a budget file. Review unknown charges before further test allocation and include console costs manually. Future production use needs centralized authenticated budget ownership and provider billing reconciliation.
