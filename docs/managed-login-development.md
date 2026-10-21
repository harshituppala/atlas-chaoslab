# Managed login development

The API can verify a Cognito resource-access token and resolve a server-owned workspace membership. The authorization-code exchange component now has offline tests. The browser sign-in flow is still unfinished, and neither component makes the full service ready for public exposure.

Run the component checks and record their source/test fingerprints:

```sh
.runtime/bin/python scripts/verify_login_exchange.py
```

This runs controlled token and key services. It does not require AWS credentials or create a user pool. The resulting report is `reports/login-exchange-offline.json`; detailed JUnit files and logs stay under `var/login-exchange/`.

## Integration boundary

`LoginExchange.begin()` returns an authorization URL and a separate browser binding. A future HTTP route must store that binding in a secure HttpOnly cookie before redirecting. It must not place it in the provider URL or browser storage. The callback supplies the state, cookie binding and code to `finish()`. Successful exchange returns a verified subject and an access token for server-side session handling. It grants no workspace role.

Keep login state and callback queries out of request logs and traces. Both the callback and redirect responses need no-store and referrer controls. Callback errors, logout and expiry must clear the appropriate browser state. The pending registry is local to one process, so routing and restart behavior need explicit tests before a multi-worker deployment.

## Provider acceptance still required

Use an explicitly reviewed HTTPS application origin and exact callback registration. Configure a public client for authorization code with S256, the required API scopes and the resource audience. Verify that its provider domain belongs to the intended pool and that issued access tokens satisfy the existing pinned trust profile. Membership must be assigned by the application operator; provider role/group claims do not grant access.

No pool or app client has been provisioned for this flow. Review access and cost before creating cloud resources. Real sign-in must be performed by the owner without sharing passwords or tokens in chat. After the routes and sessions exist, acceptance must include callback replay, wrong browser, provider denial/outage, membership revocation, logout and expiry. Until then, use the private local launcher or the separate fictional lab.

[Design and executed checks](adr/040-authorization-code-exchange.md) · [Current token profile](adr/025-explicit-cognito-access-profile.md)
