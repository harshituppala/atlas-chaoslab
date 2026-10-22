# Threat model

Assets: source documents, tenant identities, reviewer decisions, source provenance, evaluation labels, local tokens. Trust boundaries: browser → API; tenant identity → database queries; untrusted documents → workflow; evaluation input → adapter; reviewer → authoritative decision.

| Threat | Implemented control | Remaining gap |
| --- | --- | --- |
| Cross-tenant reads/reviews | Scope queries to authenticated tenant; forced transaction-local DB policies; 404 for foreign IDs; restricted-login tests | Forced PostgreSQL policies and restricted login tests now executed; deployment validation and compromised-service containment remain separate |
| Forged or stale citation | Content hash/exact span validation; immutable raw upload hash; page/paragraph maps; admitted uploads compared with persisted tenant snapshots | Production object-storage integrity, OCR/layout review |
| Prompt injection in retrieved data | No model/tools in baseline; known suspicious excerpts omitted; six adversarial probes expose two selection bypasses and one false positive | Semantic evidence trust and broader attack coverage; the live paired run retains one hostile-source citation |
| Unsupported assurance | Excerpts only; missing/conflict status; approval gate | Semantic entailment and conflict classifier |
| Conflicting reviewer edits | Transactional version predicate; stale 409 | Production load/SLA testing; local concurrent PostgreSQL reviews executed |
| Duplicate submission | Tenant/key uniqueness, pipeline fingerprint, tested fenced job recovery, tenant-owned content-addressed upload deduplication | Production load/fairness testing; local PostgreSQL concurrency executed |
| Token theft | Random local tokens, restricted credential-file mode, memory-only frontend, loopback binding | Optional managed signed-token verifier/membership revocation implemented; actual provider login, deployment TLS, operator attribution and managed secrets remain |
| Browser caching, framing and script injection | No-store API/error responses, restrictive frontend CSP, no framing, native modal focus containment, local disconnect clears workspace memory | Token revocation, production proxy validation, full accessibility audit |
| Denial of service | Receive-time/chunk/byte caps; work budgets; parser and execution deadlines; decoder/XML/archive limits; per-process parser slots; atomic upload quotas | Distributed rate limits, job fairness, overall snapshot/log quotas, verified Linux memory limit |
| Audit tampering | Audit written with review transaction; no mutation route | DB role separation, append-only protections, external retention |
| Benchmark leakage | Evaluator keeps expected labels outside adapter inputs | Larger private held-out dataset and annotation review |
| Supply-chain compromise | Exact Python lock and pnpm integrity lock, explicit esbuild build permission | Automated vulnerability scans, action/image digest pinning, SBOM |

Local static bearer tokens are for private development access. Do not expose that API profile publicly. The offline baseline makes no model calls; separately enabled Bedrock execution incurs provider usage.


Queue controls: status APIs exclude worker tokens and stored source input. Cancellation revokes publication authority. Every publish revalidates the original source snapshot and prohibits worker-created approvals. Partial publication rolls back with its terminal status and audit records. Trusted worker/evaluation subprocesses provide deadlines, not security isolation for arbitrary untrusted code. Evaluation also enforces output file-size limits and prevents adapter mutation of the judge input. PostgreSQL row policies are locally verified; production role provisioning and tenant fairness remain unvalidated. Application credentials can set custom tenant context, so policies do not contain a compromised service capable of arbitrary SQL.

## Cumulative model-test allowance

Live model CLI processes reserve configured worst-case run costs in an ignored private campaign journal before gateway initialization. Stable POSIX advisory locking and atomic publication prevent cooperating concurrent processes from spending the same allowance. Corrupt/missing/exhausted journals fail closed; crashes and failed credential setup retain reservations, with no automatic refunds. This does not resist a malicious local user editing the file or using SDK/console calls outside the guard, and is not a tax-inclusive or account-wide provider billing cap. ADR 015 records scope and verification.

## Finite model evidence choices

Assessment generation in source-selection-v4 chooses from a bounded application-owned enum derived only from scoped, integrity-checked retrieval candidates. This removes invalid relation/citation combinations from the accepted response format. It does not establish entailment, completeness, prompt-injection resistance or authorization. Unknown choices fail locally; drafts stay extractive and all assessments remain pending human review. At most three retrieval candidates keep the enum bounded to fifteen choices (ADR 017).


## Model result preparation boundary

The optional model publication preparer checks submitted source snapshots, citation spans/hashes, extractive drafts, pending review, unique requirement IDs and complete consistent provisional relation coverage. Cost is an explicit worker-ledger input and may remain unknown. It emits a fixed publication trace instead of persisting arbitrary provider trace fields. The baseline persistence gate remains baseline-only. This helper assumes a trusted worker and does not attest provider execution or factual correctness; job routing and the opt-in workbench mode have separate checks; deployed identity and runtime acceptance remain unfinished.


## Paid job execution

Bedrock job admission is default-off. Provider configuration and spending-journal paths are worker operator arguments, never source text or client fields. Stored pipeline identity chooses the publication validator and participates in idempotency. Ordinary workers skip model jobs. Model jobs get one attempt; expired leases and timeouts cannot automatically replay paid inference. Exclusive artifact ownership and cumulative reservations precede credential access. Cancellation fences publication but does not guarantee remote cancellation or prevent already-started spend. Local POSIX ownership is not distributed coordination, and a crash can leave a paid result unpublished. Provider settings are now pinned at admission (ADR 019), and the workbench has a separate opt-in model mode. Actual hosted acceptance remains unfinished.


## Model configuration identity

Admitted model jobs store a credential-free execution spec, bound into idempotency. Workers compare their config to that spec before funding/credentials; result publication verifies the same hash against the stored job. Model, region, counter, limits and price changes therefore cannot silently alter admitted execution. Credential profile names are excluded and provider settings remain operator-owned. This is a consistency boundary, not protection against a compromised worker or database operator. Legacy unpinned jobs remain readable but cannot newly execute/publish (ADR 019).


## Displayed model settings at submission

The mode selector defaults to baseline and resets on opening/reconnection. AI-assisted mode names its model/region, source-sharing behavior and configured reservation bound. The request must include the displayed spec hash; server admission compares it to the operator spec and rejects stale pages before queue creation. This binds the stated settings, not credential availability, remaining account credits or a guaranteed final bill. Controlled browser fixtures verify UI behavior; backend tests enforce admission independently of the interface.


## Local container stack boundary

The Compose initializer alone receives the local database owner password and runtime-role provisioning passwords. The API and worker each receive only their own service secret; the API also receives synthetic static principals. Passwords are delivered through per-service read-only secret bind mounts and constructed into connection settings inside the process; inspected Docker configuration is checked not to contain generated secret values. This does not protect secrets from Docker/host administrators, process-memory access or a compromised authorized service. Host secret files use mode 644 for nonroot-container readability under a private mode-700 directory; this is local filesystem protection, not encrypted secret storage or Docker Swarm secrets.

The API role cannot bypass forced row policies; actual unfiltered SQL without tenant context returned zero rows after a run was stored. The trusted worker intentionally has nonsuperuser BYPASSRLS for cross-tenant queue claims and narrower grants. Both application processes use UID 10001, dropped capabilities and no-new-privileges. PostgreSQL is not published to the host. Only the API joins a separate frontend bridge and publishes on 127.0.0.1; this permits API outbound traffic and is not an air gap. Paid admission is disabled and the stack receives no AWS/model credentials. Internal database traffic uses SCRAM without TLS on the local Docker network; production TLS/identity/secret rotation are unverified.

One synthetic Compose workflow and a Linux offline suite do not establish container escape resistance, vulnerability freedom, load tolerance, malicious service containment or deployment readiness. No snapshot/backup restore is claimed from successful volume persistence. The verifier creates a unique disposable project and deletes only its own test volume.


## Logical backup boundary

The local recovery drill exports all application tables as the trusted owner, quiesces API/worker writes, copies the custom-format archive into a private ignored directory and hashes its bytes before deleting only its own synthetic source volume. A destination-empty gate proves no application tables/runtime roles survived into the new cluster. Restore uses exit-on-error and one transaction; roles and grants are reprovisioned explicitly rather than assumed to exist in a per-database dump. Full table-content digests and real application readback/resumption are separate gates. A deliberately truncated archive is rejected without changing restored table contents.

The archive includes original uploads, source text, memberships, review history and queued inputs. Mode-600 files under mode-700 directories protect local access, not Docker/OS administrators or lost-disk/cloud exposure. Encryption, offsite storage, authenticated backup manifests, continuous/WAL recovery and retention are not implemented. A hash is not an authenticity proof; only the harness's own trusted synthetic archive is restored, since PostgreSQL archives may execute owner-chosen SQL. Never use this destructive disposable-volume drill on a real client database.


## Paired hostile-evidence evidence

The new same-author paired diagnostic shows six of six hostile appendices entering the deterministic baseline's selected evidence despite valid citation hashes/spans. Its known-string filter also excludes a benign training fact mentioning system prompt. The three observed strict regressions conditional on passing controls are not automatically successful instruction-following attacks; extraction/relation/selection failures are counted independently from forbidden-source and approval-state observations. The application still enforces pending review and extractive drafts. No real tools, secrets, external actions or live LLM are exercised by this baseline, so neither exfiltration resistance nor model injection resistance is established (ADR 024).


## Cognito token-confusion boundary

The provider-specific profile is explicit; no missing-typ or JWT header is accepted by the default RFC 9068 profile. In cognito-resource mode, signature/issuer/audience validation is still mandatory, and signed token_use, client_id and complete API scope membership are additionally checked. Tokens lacking the resource audience are rejected. ID-token purpose, foreign client/resource, scope substring tricks and malformed scope lists are tested rejections. JWKS is pinned to the issuer path and cached under the existing bounded refresh/outage policy. The verified subject must still have active server-owned membership; groups, role/tenant claims and extra scopes cannot elevate it.

These tests use generated keys and a controlled JWKS transport. They do not establish that a deployed Cognito pool issues the intended claims, that a browser safely completes login/PKCE, that refresh tokens are protected, or that remote revocation is immediate. Membership revocation is enforced on subsequent requests; existing signing-key cache and in-flight-operation limits remain. Nothing here provisions or exposes a public identity service.


## Separate recorded replay boundary

The static evidence room bundles only the explicit synthetic recordings projected by atlas.replay. Exact source hashes/spans, extractive drafts and pending review are validated on export; private job/actor/trace/prompt/token/review-note fields are omitted. Hash matching ties the historical projection to its saved report, not a signed provider attestation. This narrow fixture exporter is not a general redaction system. Every bundled byte should be treated as public when considering a future host. No user input is rendered as HTML. Browser search/selection has no persistence or write endpoint; connect-src none blocks fetches, tested with an intentional negative probe.

The separate replay artifact contains no API credentials, managed-login implementation or paid-inference controls. Static hosting cannot establish production API/database identity or durability. Its meta content policy cannot set frame-ancestors; future hosting must validate headers/HTTPS/cache/asset paths and the approved exact artifact. Targeted local Chromium checks are not a comprehensive browser/accessibility/security audit. Publication permission and the unchanged source candidate remain separate gates (ADR 026).


## Paired comparison evidence boundary

CHAOSLAB's offline comparator accepts raw scenario bundles only under the same dataset bytes and current scorer. Existing source/input identity gates and exact citation/draft/review checks are rescored on both sides. Duplicate/unknown IDs, ambiguous JSON, non-finite constants, oversized artifacts and incompatible inputs refuse publication; missing attempts are explicitly unpaired rather than apparent improvements. Operational failures are strict failures with separate counts and no exported exception strings. Both scenario- and obligation-level regressions block the fixture gate, which confers no application/reviewer/deployment authority.

Only dataset-owned scenario IDs, outcome booleans, obligation indices/digests and provenance hashes are projected. IDs from a private dataset can still disclose private information; this is not an automatic redaction tool. Hashes checked before/after bind saved bytes, not signed provider authenticity. Trusted adapter subprocesses retain host privileges. Three correlated same-author scenarios and a historical candidate do not establish production superiority, controlled cost/latency, broad injection resistance or an independent validation set (ADR 027).


## Concurrent body-admission boundary

Per-request body limits are supplemented with eight nonblocking admission slots per API middleware instance for POST/PUT/PATCH, held through downstream processing while body references may remain live. Saturation rejects before receive with a fixed 503/Retry-After; the outer response policy retains no-store/security headers. Cleanup removes the raw scope-body field and releases capacity across errors, budget failures, disconnect and cancellation. Actual in-process saturation and FastAPI ASGI checks verify refusal-before-read, health bypass and reuse (ADR 028).

This shared pre-auth limit is not a per-tenant rate/fairness mechanism; a caller can occupy all slots. Replicas/processes multiply capacity, receive deadlines do not bound downstream time, and server buffers/chunks/parsers/responses add memory beyond accepted payloads. Scope cleanup cannot erase references owned by downstream code. No socket load, total RSS, proxy limits, distributed overload protection or production DoS guarantee was measured. Do not expose the local API based on this control alone.


## Worker child-pipe boundary

The trusted baseline/model child paths now bound stdout during receipt rather than after unbounded capture, enforce a separate counted/discarded stderr budget, check input before spawn and progress all pipes concurrently to avoid pipe-pressure deadlock. A monotonic deadline also applies after pipes close. Failure and normal-exit cleanup target the invocation's new POSIX process group and reap its root; actual native checks verify excess-output stop and descendant heartbeat cessation. Worker/result/queue publication validation remains unchanged (ADR 029).

These are not hostile-code sandboxes, total-RSS controls or complete process-tree containment. Children retain host file/network access, can escape their group, and cannot be cleaned up by Python finally after parent SIGKILL/host failure. Source-bearing stdout remains private validation/storage input; diagnostic strings are not exported. Killing a paid model child cannot undo provider-side execution or establish zero billing: one-attempt policy, uncertain private receipts and conservative reservations remain. Only native offline behavior was newly measured; model wiring used controlled outputs and no provider call.


## Observed live hostile-evidence limitation

The October 19 unchanged-v4 model run selected a forbidden instruction-bearing appendix in one of six hostile cases even though its citations had valid document hashes/spans and its relation remained the expected contradicted label. Citation integrity and structured output therefore did not prevent evidence contamination. One strict regression occurred among four passing clean controls; that conditional result is not a general instruction-following attack rate. No unauthorized review states were observed, but the fixture grants no tools, credentials or external communication, so exfiltration/tool safety is not established. Benign security-training text is also suppressed by the current keyword filter, while a clean numeric-threshold relation is wrong. These failures remain frozen in reports/injection-pairs-live-v4.json (ADR 030). No production or comprehensive injection-resistance claim follows.


## Local lifespan-owned worker boundary

The optional loopback SQLite profile owns one baseline worker thread under API startup/shutdown. Explicit file/principals and refusal of inherited model/managed/database settings reduce accidental configuration crossover. An unexpected queue-loop failure makes readiness 503 with fixed text; liveness stays separate. Model jobs are not claimed, and paid submissions are disabled. Real child publication, tenant checks, SQLite restart and completed lifespan shutdown were exercised locally (ADR 031).

The worker and API share process privileges and are not separate security principals. A non-daemon thread and thirty-second join can fail to stop promptly; storage is deliberately kept open if that happens. Child deadlines do not bound database calls or publication. Liveness/thread state does not establish forward progress, and the existing API can still accept jobs when worker readiness fails. No public sessions, provider persistence, external supervision, hostile-code containment, total RSS cap or cloud recovery guarantee is provided. Never expose the static-token API publicly based on this runtime simplification.


## Recovery evaluator adapter boundary

The recovery judge no longer calls adapters in its own process. Each case uses the existing CHAOSLAB disposable-process deadline/artifact boundary; a timeout, crash or malformed observation is a fixed failed outcome and does not prevent later cases from being evaluated. Strict nonempty typed expectations and before/after source/dataset identity checks prevent vacuous passes and silently mixed execution identities. Only known observation keys with bounded counters/booleans/queue states are projected. Raw events, unknown fields and exception details are omitted; source-bearing canary tests verify these refusals (ADR 032).

Adapters remain trusted code with host filesystem/network privileges and can misreport observations. Process-group escape, parent/host failure, total RSS/disk use and external adapter source outside src remain outside the boundary. Authored dataset IDs and scope remain public report content; this is not a general redaction mechanism. Seven local SQLite cases still use simulated lease time and establish neither a cloud recovery target nor a cause for the earlier intermittent queue test failure.


## Temporary synthetic-session API boundary

A separate local factory mounts only the seeded lab routes. Pinned synthetic input, literal case IDs, server-owned note choices and private-configuration refusal prevent normal callers from submitting private sources or enabling inference. Session-cookie digests select separate in-memory databases. Exact Origin checks on writes, cross-site Fetch Metadata refusal, a host allowlist, no CORS grants and no-store responses supplement the HTTPS cookie attributes. Existing source/publication/review gates remain authoritative (ADR 033).

Absolute monotonic expiry, periodic/request-release cleanup, active-slot retention, post-computation expiry checks, body limits, one computation slot and per-session/process budgets bound this specific profile's retained operations. They are process-local controls, not fair identity-based rate limiting, a total RSS/CPU/disk/network bound or an invoice cap. An anonymous caller can occupy all available capacity. State and counters reset on process failure/restart; replicas multiply capacity. Browser/TLS/provider behavior is unverified, and cookies identify temporary fictional exercises rather than people. The private token API is not mounted and must not be exposed based on this preparation. No customer-data or durability promise is made.


## Dedicated synthetic browser entry

The lab build offers only hardcoded same-origin lab requests with cookie credentials; no bearer-token/API-address/upload/model/free-note controls or browser storage are used. Read-only lifetime metadata does not renew sessions. Client expiry clears the displayed result; the server remains authoritative. A stale review refreshes the result and requires another explicit decision. Only the explicitly marked dist-lab artifact can be mounted through the lab launcher, preserving separation from the private build (ADR 034).

Three real Chromium/loopback HTTP workflows verify source focus/highlights, review conflicts, reload/logout, HTTP cookie attributes, network route separation and mobile overflow. Capacity feedback and shortened client lifetime are controlled faults. They do not establish real hosted Secure-cookie/TLS behavior, provider restarts, comprehensive accessibility, resource/invoice caps or a ten-minute browser expiry. Other tabs can retain already-rendered fictional data after logout until their next request/reload/timer. Static artifact content still needs explicit publication review; the profile marker is not a secret scanner.


## Dedicated synthetic image boundary

The lab image builds from an explicit context of Python source/locks, one pinned fictional fixture and the dedicated frontend. It omits repository history, host credentials/caches, reports, user documents and the private frontend. Its container entry requires explicit opt-in/external origin and mounts only the synthetic API. Actual local Linux checks used UID 10001, read-only root, network none/no host ports, dropped capabilities, no-new-privileges, small tmpfs mounts, 512 MiB memory/no extra swap, one CPU and 64 PIDs (ADR 035).

Thirty-two focused Linux tests and real HTTP/review checks passed under those settings. An actual restart invalidated the previous session and permitted a new analysis; it did not preserve review history. Observed cgroup memory peak is a limited-workload measurement, not process RSS or a comprehensive resource/abuse bound. Pinning public base-image digests does not establish vulnerability-free dependencies or signed provenance. Host/engine failure can prevent cleanup; provider TLS/proxy/storage/quotas and other architectures remain unverified. Docker-managed caches are outside the verifier's source context. No credentials, socket or host workspace are required inside the runtime.

## Hosted synthetic lab

The free public lab uses the separate synthetic-only container entry, not the private upload API. Real HTTPS checks verified Secure/HttpOnly/SameSite cookies, exact source spans, review conflicts, session isolation and origin/body refusal. Targeted Chromium checks cover desktop/mobile use and logout. A provider-triggered restart rejected the old session before expiry and allowed a fresh analysis. The container deadline is twenty seconds after an observed five-second failure on the free host; one compute slot and the existing start/session/body budgets still apply. Fixed failure logs omit document and exception contents. These checks do not establish durable customer storage, a production identity flow, load resistance, all browser behavior or an invoice cap.

## Separately installed evaluator

The standalone wheel does not install ATLAS or third-party runtime packages. This reduces setup coupling, not adapter privileges: selected trusted adapters retain the user's filesystem and network permissions. Comparisons fingerprint installed scorer files rather than paths in the caller's directory. Installed package digests exclude external adapter code. The controlled checks in ADR 037 do not establish package-signing, supply-chain integrity or isolation from hostile code.

## Ingestion evaluation inputs

The ingestion runner freezes source, dataset and fixture bytes before execution and checks them before publishing. Changed inputs refuse publication; the report destination cannot overwrite its dataset or a fixture. Source-location checks search inside the authored segment, so repeated text elsewhere cannot substitute for that page or paragraph. These controls detect drift in trusted local runs; they do not make adapter code safe to execute or attest loaded bytecode.

## Authored evaluation contracts

Unknown relations, duplicate source identities, out-of-source obligation quotes and inconsistent evidence expectations reject a scenario experiment before scoring. Errors describe fields without echoing source text. Invalid inputs preserve the previous comparison report. This prevents malformed labels from matching fallback states, but does not establish the factual correctness or independence of the author's expectations. See ADR 039.

## Authorization-code exchange component

The opt-in backend component binds state and PKCE to a separate browser secret, consumes attempts before network exchange, and bounds pending and in-flight work. Provider redirects, compressed/oversized payloads, invalid access purposes and mismatched trust fail closed. Refresh tokens are discarded and no workspace roles are assigned. ADR 041 adds opt-in callback/session routes with HttpOnly cookies and Origin/CSRF checks. Default profiles leave them disabled; proxy-log redaction and actual provider/browser acceptance remain mandatory integration work. See ADR 040 and the offline report; the public fictional lab is unchanged.

## Opt-in HTTP sessions

Provider tokens remain in process memory behind opaque host-only session cookies. Writes require the configured Origin and session CSRF token; ambiguous cookies and mixed bearer/cookie requests are rejected. Every API request rechecks token trust and current membership. Logout and expiry invalidate server state, and reauthentication rotates handles. The registry has bounded capacity and survives no restart. Distributed throttling, proxy-log controls, browser SameSite enforcement and real provider acceptance are not established by the controlled HTTP tests. The workbench now discovers this opt-in profile and keeps provider tokens out of browser JavaScript. It unmounts displayed workspace data and aborts pending requests on expiry, denied identity or sign-out. Failed logout retains an explicit retry; it does not claim server revocation. A configured form origin expands only form-action, with script/connect sources unchanged. Controlled browser fixtures do not establish real provider redirects, SameSite behavior or deployed proxy safety. See ADR 042.


## Saved evaluation observations

Comparison admits observation containers before indexing them. Malformed saved experiments exit 2 without replacing an earlier report; wrong but usable citations and assessments remain scored failures. Fresh unusable adapter responses are recorded as attempted failures. Bounded bytes, explicit nesting depth and finite-number checks reduce parser ambiguity; fixed structural errors omit source contents. These checks do not sandbox adapters, attest saved output or sanitize arbitrary private metadata. Scenario IDs still appear in public comparison reports; operators must review publication inputs. See ADR 043.


## Joined local browser identity check

A real Chromium/TLS fixture caught an Origin:null form failure that manually supplied HTTP headers and intercepted UI responses missed. Optional login HTML uses same-origin referrers and no-store, including its index revalidation path; callbacks/API responses retain no-referrer. Origin admission remains strict. Browser checks now exercise cross-site Strict-cookie withholding, consumed callback replay, signed membership, CSRF, revoked access and logout through the real application. The provider is synthetic, uses a subprocess-pinned test certificate and contains local test controls. It must never be mounted in a hosted service. These results do not establish real Cognito configuration, public trust, production proxy redaction or distributed sessions. See ADR 044.

## Managed application configuration

The operator factory requires private, bounded settings with exact fields and explicit database selection. It rejects symbolic links, duplicate JSON keys and inherited demo/bearer/model profiles. It supplies no static credentials and grants no membership. Unknown configuration cannot silently enable a client secret, proxy override or paid job profile. The application owns the verification/exchange clients and closes them on shutdown or construction failure. These controls assume a trusted local operator; filesystem permissions do not protect against that same account, a compromised process or an incorrect provider pin. Real AWS resource creation is separate from acceptance: directory/client/scope configuration has been saved, but no real user callback, deployed TLS endpoint or hosted access boundary has yet been tested. See ADR 045.

The optional provider preflight compares public discovery against operator pins and requests keys only from the pinned key endpoint. It cannot follow a discovery-supplied URL or redirect. Size/time limits and fixed errors constrain malformed responses; the result omits endpoint values, key IDs and response bodies. It shares runtime key admission, including controlled refusal of excessively nested key JSON. A matching public document and usable RSA keys establish configuration consistency only, not app-client registration, user authentication or workspace authorization. See ADR 046.
