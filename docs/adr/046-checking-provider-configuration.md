# Check provider configuration before a user signs in

A reachable signing-key URL is insufficient to check the login setup. The pool issuer might be correct while the configured login domain belongs to another pool. Waiting for a user to enter a password is a poor way to discover that mismatch.

The operator now has a read-only preflight. Offline mode admits the private settings without opening a database. An explicit `--provider` mode fetches the pinned issuer's public discovery document and requires all four endpoint identities to agree with the settings. It then fetches the pinned public keys through the existing key-admission code. Discovery never supplies a new request destination. Standard HTTPS certificate validation stays enabled; environment proxies and redirects are disabled.

Discovery responses are limited to 64 KiB and a five-second deadline. Duplicate members, non-standard numeric constants, excessive nesting, compressed responses, mismatched endpoints and missing advertised code support fail with fixed messages. Provider bodies and configuration values do not enter the result or exception. A deeply nested key response also now produces the existing controlled key-service failure rather than escaping its exception handler.

Twenty-five controlled cases passed, including endpoint substitution, transport failures, malformed metadata/keys, client cleanup and offline CLI behavior. The full native suite passed 666 tests, with 18 optional PostgreSQL groups skipped. The existing joined synthetic TLS/Chromium acceptance passed all twelve groups after the change. The live public AWS probe matched all endpoint pins and admitted two RSA signing keys. Its report contains source and configuration fingerprints, with account-specific endpoints and identifiers omitted.

These checks do not authenticate anyone. Discovery advertises provider capabilities; it does not prove the particular app client's grants, scope registration or PKCE behavior. No user token, actual callback, workspace membership, paid inference or hosted service was tested. Real user sign-in remains the next acceptance step.
