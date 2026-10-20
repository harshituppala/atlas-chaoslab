# ADR 005 — Local embeddings with shared-source hybrid retrieval

Status: implemented and measured locally; persistent pgvector retrieval remains unvalidated.

The first semantic encoder is sentence-transformers/all-MiniLM-L6-v2 on CPU. Its repository commit and safetensors SHA-256 are pinned; loading uses only local files and disallows remote repository code. Model downloads are an explicit setup operation. This English short-text encoder has a limited token window. Token-aware overlapping chunks retain exact source spans and are checked before encoding, preventing silent truncation. BM25 and dense search share those same chunks so fusion cannot lose provenance.

Dense search uses normalized cosine similarity. Hybrid search uses reciprocal rank fusion rather than adding incomparable BM25/cosine scores. Stable source IDs resolve ties; duplicate votes within one retriever do not gain extra credit. Similarity is relevance, not proof of compliance.

CHAOSLAB independently scores ten authored positive paraphrase queries over ten synthetic capability excerpts. Labels were written before execution and never enter the encoder. Lexical recall at three was 0.70; semantic and hybrid recall at three were 1.00 on this fixture set. This small, deliberately simple corpus does not establish enterprise retrieval accuracy, unanswerable-query behavior, multilingual quality, or large-index performance. Exact measured ranks and environment/model/source identities are in reports/retrieval.json.

The heavyweight model runtime is optional, separately locked, and excluded from the baseline container dependency closure. Linux CPU-wheel resolution/container behavior, persistent vector indexes, reranking, multilingual corpora, cache isolation, and larger blinded datasets are later validation gates.

Model card: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 (Apache-2.0).
