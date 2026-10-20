# ADR 001 — A deterministic baseline before model-backed reasoning

Status: accepted for milestone 01.

We need an inspectable workflow before paying for model calls or making accuracy claims. Mandatory-line extraction and BM25 retrieval produce a baseline that runs offline, costs no external model tokens, and makes provenance verifiable. LangGraph provides explicit stages so model-backed extractors and retrievers can be introduced without moving trust decisions into prompts.

Tradeoffs: this baseline misses paraphrased obligations, lacks semantic retrieval, and cannot establish entailment. Negative words are a conservative review flag, not a contradiction classifier. The deliberately missed held-out obligation remains in the measured report. The baseline must not be marketed as a completed AI intelligence product.

Exit criteria: a provider-backed implementation improves held-out extraction and factual support metrics while preserving citation integrity, abstention, tenant isolation, bounded execution, and human authority.

References consulted: https://docs.langchain.com/oss/python/langgraph/overview and https://github.com/pgvector/pgvector.
