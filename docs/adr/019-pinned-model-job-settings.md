# ADR 019 — Pin model settings at admission

Status: implemented; offline verified. Supersedes ADR 018's configuration-pinning gap.

A queued model review must not silently change models, region or spending limits because an operator edits the worker config after submission. Admission now uses a strictly validated credential-free spec exported from BedrockConfig. It includes model ID, count-token identity, region, limits and the verified price card. The local credential profile is deliberately excluded.

The API requires both explicit model admission enablement and a valid bounded spec file. It captures the spec at startup. The queue accepts it only through a trusted keyword argument, stores it in private input, and fingerprints the complete input plus pipeline version. Client request schemas prohibit internal fields and arbitrary provider configuration. A changed spec conflicts under an existing idempotency key.

The model executor compares canonical config digests before creating invocation artifacts, reserving campaign funding or initializing credentials. The prepared result includes the same digest, and the persistence validator compares it to the stored job. The existing JSON input/result columns avoid a schema migration. Credentials, tokens and local profile names never enter the exported spec.

Tests cover all relevant config drift, profile independence, idempotency, persistence rejection and historical status readback. Old unpinned jobs receive null attribution and cannot newly execute/publish. Previously completed analyses remain inspectable; no historical evidence is upgraded retroactively.

A differently configured worker can still claim a model job before rejecting it, making the single attempt terminal. This conservative behavior avoids accidental spending; configuration-aware worker routing would be needed for multiple model pools. Local operators and workers remain trusted. Hashes do not attest execution or prevent a compromised operator from forging data. No new paid call or deployed integration is claimed.
