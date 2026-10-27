# Restart the process, keep the review

Date: October 27, 2026. Status: local PostgreSQL acceptance passed; hosted acceptance remains open.

A page reload keeps the server's memory alive. It cannot prove that a stored review survives replacement of the application process, or that an old opaque session becomes unusable after that replacement.

The restart exercise now launches the managed application in a real child process, alongside a separate baseline worker and a fresh local PostgreSQL cluster. A synthetic identity provider completes the browser's code/PKCE exchange. The browser queues an analysis, checks its source, saves a review and reads the complete run and audit history.

The controller stops the application process and starts another on the same private listener. PostgreSQL and the worker remain running. The old session is refused. After a fresh sign-in, the browser retrieves the same run and audit history and compares both with the saved values. Restoring the old cookie still fails; restoring the new cookie succeeds. The test then retains the existing membership-revocation, logout and expiry checks.

Fixture bootstrap must not grant access again on every start. It reuses an existing active synthetic membership without incrementing its version, and refuses an inactive membership. Three offline controls check those boundaries. This is test infrastructure; it adds no public enrollment or restart endpoint to ATLAS.

Fourteen joined browser groups passed. Both application processes and both worker processes exited with status zero. The three existing browser modes also passed, and the full native suite passed 929 tests with eighteen optional PostgreSQL groups skipped. [The measured record](../../reports/managed-postgres-restart.json) binds the source and scope.

There is a shutdown limit worth keeping visible. The loopback TLS fixture reached its two-second connection-drain deadline on both application stops; the server reported zero running tasks cancelled. This proves the recorded persistence and session behavior, not uninterrupted requests or fully drained connections. Earlier attempts failed to save shutdown evidence; they were not admitted as successful reports.

The database connection uses authenticated loopback TCP without database TLS. The provider is synthetic. This exercise does not restart PostgreSQL, restore a backup, run the production supervisor/image or establish real Cognito, hosted proxy safety or cloud persistence. Those remain separate acceptance gates. No model call or cloud resource was used, and the frozen contract evaluations were unchanged.
