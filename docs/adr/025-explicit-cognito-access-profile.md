# ADR 025 — Explicit resource-bound Cognito access-token profile

Date: 2026-10-18

## Deployment requirement

The default verifier implements an RS256 resource-access profile requiring at+jwt/application/at+jwt. Cognito's documented access-token header can omit typ; its payload distinguishes access from ID tokens using token_use, identifies the app client using client_id, and only supplies aud when resource binding is requested. Silently dropping type/audience checks to make hosted login work would create token-confusion risk.

## Decision

Keep rfc9068 as the unchanged default. Add operator-selected cognito-resource, requiring a bounded explicit client_id, one or more API scopes, the exact resource audience, and JWKS at the pinned issuer's /.well-known/jwks.json path. The verifier accepts only RS256, retains issuer/audience/signature/time/subject/duplicate-member checks and key-fetch/cache limits, and accepts only an absent typ or JWT for this profile. It additionally requires signed token_use=access, exact client_id and all configured scopes as whole scope tokens. Reject unbound access tokens without aud, ID tokens, unexpected resource/client, malformed scope claims and cross-profile headers. No automatic provider detection or fallback exists. Required-scope configuration is frozen from JSON lists to immutable tuples.

The output remains VerifiedSubject only. Cognito groups, role/tenant claims, extra scopes and usernames grant no workspace role. Server-owned membership is checked on every request, including revocation. Configuring the Cognito profile disables neither membership checks nor managed-mode rejection of local bearer tokens. A signed subject is not independently a proof that a human completed an approval, and an operator must not grant reviewer membership to an unintended machine identity.

## Executed verification

Thirty-six new offline cases use actual RSA signatures and controlled JWKS responses: accepted header variants, ID/purpose/client/resource/scope/signature/time rejections, invalid provider configuration, immutable scope lists, default-profile separation, operator JSON loading through the real API, forged role/group/tenant claims, denied writes for viewers, rejected local-token fallback and immediate subsequent-request membership revocation. Existing generic JWT key rotation, outage, unknown-kid throttling and ambiguity cases still pass.

The full host suite passed 316 cases with 18 optional PostgreSQL groups skipped. The actual Linux image passed the same 316 cases, dependency consistency and the existing HTTP/SQLite worker/restart workflow. reports/cognito-profile.json binds actual JUnit/image evidence and states which host hashes were captured after execution; reports/container.json retains the Linux verifier's before/after input identity. These are local hashes, not signed attestations.

## Operator and release limits

The provider must actually issue resource-bound access tokens through the appropriate OAuth flow with the configured API scope. This milestone creates no Cognito pool/client, browser authorization-code/PKCE/callback flow, refresh-token storage, hosted key service or real managed login. TLS, production secrets, deployed token issuance and identity verification remain acceptance gates. Authentication configuration changes do not alter extraction/model workflow semantics, so pipeline versions remain unchanged.

Primary reference: [AWS Cognito access-token contract](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html), checked October 18, 2026.
