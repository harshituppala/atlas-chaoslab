# ADR 004 — Source selectors before generated responses

Status: implemented and contract-tested; live generation is unvalidated.

The model selects exact obligation quotes from stable source chunk IDs, then selects a provisional relation and evidence IDs from a retrieved candidate set. It never supplies document hashes or offsets: the application reconstructs and validates those from immutable inputs. Unknown IDs, invented/ambiguous quotes, duplicate obligations, out-of-scope retrieved evidence, invalid JSON, and invalid evidence/relation combinations fail closed. Draft text remains a deterministic collection of excerpts. A valid citation proves source identity, not factual entailment.

LangGraph stages are fixed; there are no model-selected tools, HTTP requests, shell operations, or autonomous approvals. Document text is explicitly untrusted. This bounds the consequences of prompt injection but does not establish general injection resistance or model accuracy. Human review remains mandatory.

Bedrock is the first implemented provider adapter because AWS integration is part of the requested portfolio. OpenAI is a planned second adapter for independent model comparisons. The provider protocol keeps the reasoning workflow separate from SDK-specific requests. Bedrock's structured-output schema subset omits bounds that remain enforced by Pydantic locally. Provider-native citation mode is not used with structured output; citations are application-owned.

Live construction requires explicit spending opt-in and a model/region-matched, dated price card. Token preflight plus conservative input/output reservations bound admission. SDK retries are disabled; ambiguous failures retain their reservation and unknown usage/cost. A private atomic journal is written before each possibly billable invocation. Observed usage overrun terminates the workflow. Cost computed from a price card is an estimate, not an invoice or an absolute account spending guarantee. No live model calls have been made.

The model workflow is currently a guarded CLI/library, not connected to the public API or durable job queue. Production integration needs a persisted model configuration identity, durable per-attempt accounting across retries, reviewed price cards, real held-out evaluation, and explicit access/spending authorization. The baseline remains the default application workflow.

The CLI exclusively reserves an artifact name before provider construction. Existing reports, billing journals and interrupted reservations are preserved; repeated or concurrent runs must use distinct output names. An interrupted reservation is not automatically cleared because the previous request's billing may be uncertain. Concurrent ownership and preservation are tested locally without provider calls.

References: https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html and https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html.
