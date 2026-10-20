"""Local semantic retrieval and rank fusion; no automatic model downloads."""

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from .domain import Citation, Document, ResourceBudgetExceeded
from .retrieval import BM25, INSTRUCTION

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
WEIGHTS_SHA256 = "53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db"


class Encoder(Protocol):
    def encode(self, texts: list[str]): ...
    def token_count(self, text: str) -> int: ...


class LocalEncoder:
    def __init__(self, path=".cache/models/minilm"):
        import os

        os.environ.setdefault("HF_HOME", str(Path(".cache/huggingface").resolve()))
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import SentenceTransformer

        root = Path(path).resolve()
        if not (root / "model.safetensors").exists():
            raise FileNotFoundError(
                "Prepare the pinned embedding model before enabling semantic search"
            )
        with (root / "model.safetensors").open("rb") as weights:
            from hashlib import file_digest

            if file_digest(weights, "sha256").hexdigest() != WEIGHTS_SHA256:
                raise ValueError("Embedding weights differ from the pinned public artifact")
        self.model = SentenceTransformer(
            str(root),
            device="cpu",
            local_files_only=True,
            trust_remote_code=False,
            model_kwargs={"use_safetensors": True},
        )
        self.maximum = int(self.model.max_seq_length)
        # Cache lineage includes tokenizer/config/runtime changes, not just model weights.
        import json
        from importlib.metadata import version

        recipe = {
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "weights": WEIGHTS_SHA256,
            "maximum_tokens": self.maximum,
            "chunks": "word-overlap32-v1",
            "runtime": {
                name: version(name)
                for name in ("sentence-transformers", "transformers", "torch", "numpy")
            },
            "configuration": {
                str(file.relative_to(root)): sha256(file.read_bytes()).hexdigest()
                for file in sorted(root.rglob("*.json"))
            },
        }
        self.recipe_sha256 = sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()

    def token_count(self, text):
        return len(
            self.model.tokenizer.encode(
                text, add_special_tokens=True, truncation=False, verbose=False
            )
        )

    def chunk_spans(self, text, overlap_tokens=32):
        """Split at source word boundaries without losing or silently truncating text."""
        words = list(re.finditer(r"\S+", text))
        spans = []
        start = 0
        while start < len(words):
            low, high = start + 1, len(words)
            end = start
            # Tokenization is monotone for prefixes ending at whitespace boundaries.
            while low <= high:
                middle = (low + high) // 2
                candidate = text[words[start].start() : words[middle - 1].end()]
                if len(candidate) <= 4096 and self.token_count(candidate) <= self.maximum:
                    end = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if end == start:
                raise ResourceBudgetExceeded("A source word exceeds the embedding budget")
            spans.append((words[start].start(), words[end - 1].end()))
            if end == len(words):
                break
            # Limit overlap by actual tokenizer length, always advancing at least one word.
            next_start = end
            while next_start > start + 1:
                candidate = text[words[next_start - 1].start() : words[end - 1].end()]
                if self.token_count(candidate) > overlap_tokens:
                    break
                next_start -= 1
            start = next_start
        return spans

    def encode(self, texts):
        if any(self.token_count(text) > self.maximum for text in texts):
            raise ResourceBudgetExceeded("Embedding input would be silently truncated")
        return self.model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )


@dataclass(frozen=True)
class Hit:
    source: Citation
    score: float
    method: str


def reciprocal_rank_fusion(rankings: list[list[str]], k=60) -> list[tuple[str, float]]:
    if k < 1:
        raise ValueError("Rank fusion constant must be positive")
    scores = {}
    for ranking in rankings:
        # Duplicated IDs cannot gain artificial extra votes within one retriever.
        seen = set()
        for rank, identifier in enumerate(ranking, 1):
            if identifier in seen:
                continue
            seen.add(identifier)
            scores[identifier] = scores.get(identifier, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def identity(citation):
    return sha256(
        f"{citation.document_id}:{citation.digest}:{citation.start}:{citation.end}".encode()
    ).hexdigest()


class HybridIndex:
    backend = "hybrid_memory"

    def __init__(self, documents: list[Document], encoder: Encoder):
        import numpy as np

        self.encoder, self.documents = encoder, {d.id: d for d in documents}
        if len(self.documents) != len(documents):
            raise ValueError("Document IDs must be unique")
        self.sources = []
        for document in documents:
            for match in re.finditer(r"[^\n]+", document.text):
                text = match.group()
                if not text.strip() or INSTRUCTION.search(text):
                    continue
                if hasattr(encoder, "chunk_spans"):
                    spans = encoder.chunk_spans(text)
                else:
                    if encoder.token_count(text) > getattr(encoder, "maximum", 256):
                        raise ResourceBudgetExceeded(
                            "Evidence requires token-aware chunking before semantic indexing"
                        )
                    spans = [(0, len(text))]
                for start, end in spans:
                    self.sources.append(
                        Citation(
                            document_id=document.id,
                            digest=document.digest,
                            start=match.start() + start,
                            end=match.start() + end,
                            quote=text[start:end],
                        )
                    )
        if len(self.sources) > 5000:
            raise ResourceBudgetExceeded("Semantic chunk budget exceeded")
        self.lexical = BM25(documents, chunks=self.sources)
        self.by_id = {identity(c): c for c in self.sources}
        self.vectors = (
            np.asarray(encoder.encode([c.quote for c in self.sources]), dtype=np.float32)
            if self.sources
            else np.empty((0, 0), dtype=np.float32)
        )
        if self.sources:
            if (
                self.vectors.ndim != 2
                or len(self.vectors) != len(self.sources)
                or not np.isfinite(self.vectors).all()
            ):
                raise ValueError("Invalid embedding matrix")
            norms = np.linalg.norm(self.vectors, axis=1)
            if (norms <= 0).any():
                raise ValueError("Zero vector cannot be used for cosine retrieval")
            self.vectors = self.vectors / norms[:, None]

    def search(self, query, limit=3, method="hybrid"):
        import numpy as np

        if not query.strip() or not 1 <= limit <= 100:
            raise ValueError("Invalid query or result limit")
        if method not in {"lexical", "semantic", "hybrid"}:
            raise ValueError("Unknown retrieval method")
        if not self.sources:
            return []
        lexical = self.lexical.search(query, limit=min(100, len(self.sources)))
        if method == "lexical":
            return [Hit(c, 1 / (n + 1), "lexical_rank") for n, c in enumerate(lexical[:limit])]
        vector = np.asarray(self.encoder.encode([query]), dtype=np.float32)
        if vector.shape != (1, self.vectors.shape[1]) or not np.isfinite(vector).all():
            raise ValueError("Query embedding is incompatible with the index")
        norm = np.linalg.norm(vector)
        if norm <= 0:
            raise ValueError("Zero query vector")
        scores = self.vectors @ (vector[0] / norm)
        semantic = sorted(
            zip(self.sources, scores, strict=True),
            key=lambda item: (-float(item[1]), identity(item[0])),
        )
        if method == "semantic":
            return [Hit(c, float(score), "cosine") for c, score in semantic[:limit]]
        # Fuse a bounded candidate set; raw cosine and BM25 scores are incomparable.
        candidates = [identity(c) for c, _ in semantic[: min(20, len(semantic))]]
        fused = reciprocal_rank_fusion([[identity(c) for c in lexical[:20]], candidates])
        return [
            Hit(self.by_id[key], score, "reciprocal_rank_fusion") for key, score in fused[:limit]
        ]
