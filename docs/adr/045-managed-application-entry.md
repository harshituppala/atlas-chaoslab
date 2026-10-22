# Explicit entry point for managed sign-in

The exchange and session components could be assembled in Python, but there was no operator entry point for the real Cognito configuration. Reusing the demo launcher would also risk carrying its credentials into a managed service.

`atlas.managed:create_from_environment` now requires a private settings file and an explicit database URL. It rejects unknown settings, duplicate JSON members, oversized files, symbolic links and group/world-readable files. The file contains pinned provider, callback, issuer, key endpoint, public client, audience and scope values. It accepts no client secret. The example uses reserved placeholder domains; actual account settings stay outside public source.

The factory refuses inherited demo credentials, a second token-trust configuration and a paid model job specification. It passes an empty static-principal map and constructs one verifier shared by the API and exchange. Database membership still determines workspace access on every request. A successful provider sign-in alone grants no role.

The factory owns both HTTP clients and disposes the database engine at shutdown. Construction failures close the clients already created. Normal provider traffic keeps certificate verification, fixed endpoints, disabled environment proxies and the existing request limits. Transport injection is available only through the Python function for controlled tests; the environment entry point offers no transport override.

Twenty-four focused tests passed, covering settings admission, conflicting profiles, construction cleanup and a signed callback that remains unauthorized until a separate membership grant. The full native suite passed 641 tests, with 18 optional PostgreSQL groups skipped. The joined Chromium/TLS fixture now reads settings through this entry point and passed its twelve groups again. It still uses a synthetic provider; it does not prove real Cognito login.

The approved real directory, public client, domain and API scope have been created in AWS. The console confirms the authorization-code grant and exact local callback. No end user, real authenticated callback or hosted review service has been validated. Local session state remains unsuitable for an unplanned multi-instance deployment. TLS, proxy redaction, durable storage, membership operations and external browser acceptance remain deployment work.
