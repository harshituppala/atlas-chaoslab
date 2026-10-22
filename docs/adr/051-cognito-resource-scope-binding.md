# Bind Cognito scopes to the requested API resource

The first real browser attempt returned to ATLAS with `invalid_request`, before a password form appeared. Cognito’s diagnostic said that scopes used with resource binding must belong to the requested resource. The client requested the legacy `atlas/api` scope with a different HTTPS API audience. Discovery and local token tests had not exercised this provider contract.

Keep audience validation. The operator approved a resource server with the same identifier as the private API audience, a `review` scope under that resource, and enabling that scope on the existing public client. Cognito confirmed the update. Both registered callbacks and the existing code grant remain. The private application settings now request the matching URI-prefixed scope. No IAM or paid-model access follows from that scope; server-owned workspace membership is still required.

`LoginConfig` now rejects custom scopes outside the exact audience prefix, empty scope suffixes and OIDC-only scope sets. It does not normalize trailing slashes or accept lookalike resource names. Eight controls cover that admission rule. Examples and the synthetic HTTPS provider use the same contract, so the fixture no longer hides the mismatch.

The native suite passed 792 tests, with eighteen optional PostgreSQL groups skipped. The joined synthetic HTTPS browser run passed twelve groups. Separately, Safari reached the real Cognito password step after the approved correction. That is provider request acceptance, not an authenticated callback, workspace acceptance or a hosted deployment. Password entry and any first-password replacement remain with the owner.

AWS documents the relationship in its [resource-server guide](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html) and [authorization endpoint reference](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html). Private configuration, identity details and screenshots remain outside the release.
