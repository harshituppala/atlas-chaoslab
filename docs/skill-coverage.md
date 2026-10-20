# Implementation and evidence

This map follows the skills identified in the earlier review of twenty junior AI job postings. The original postings are not included here, so the table describes the projects rather than making a current market-ranking claim.

| Area | Implemented and checked | Still to demonstrate |
| --- | --- | --- |
| Python | Typed domain models, process supervision, transactional persistence, unit and integration tests | Maintainability under sustained changes and representative load |
| APIs | FastAPI, scoped authorization, upload limits, durable job APIs, Bedrock adapter | Hosted integrations and operational behavior |
| TypeScript and React | Requirement review, exact source highlighting, conflict handling, evaluation views | Broader browser and accessibility testing |
| Databases | SQLite, PostgreSQL migrations, concurrent jobs/reviews, forced tenant policies, restricted roles, logical restore | Hosted provisioning, offsite backups and production recovery |
| Retrieval | BM25, pinned CPU embeddings, rank fusion, persistent exact pgvector search | Representative contract data and corpus-scale performance |
| Model workflows | Bounded LangGraph stages, structured Bedrock output, finite evidence choices, pinned job settings | Better threshold reasoning, benign-filter handling and hostile-evidence rejection |
| Evaluation | Independent adapter/scorer boundary, golden cases, fault scenarios, paired raw-run comparisons | Independently authored data and blinded review |
| Security | Source integrity, tenant checks, review authority, request/process budgets, explicit paid execution | Real managed sign-in and hosted security validation |
| Delivery | Local Git milestones, locked dependencies, Linux container checks, CI configuration | Remote CI, a verified hosted release and rollback |
| Observability | Metadata-only stage traces, evaluation timing and estimated model usage | Cross-process trace context, deployed collection and billing reconciliation |

A technology appearing in the code is different from operating it in production. Use the linked runbooks and measured reports when explaining what was actually tested.
