"""Persistent exact pgvector retrieval with immutable source/cache identity.

Queries are tenant/corpus scoped. This module does not establish database RLS or
semantic entailment and is not yet the default workbench execution path.
"""

import json
import re
from hashlib import sha256

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Column,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    select,
)
from sqlalchemy.exc import IntegrityError

from .db_scope import scoped_transaction
from .domain import Citation, ResourceBudgetExceeded
from .migrations import ensure_ready
from .retrieval import BM25
from .semantic import Hit, HybridIndex, identity, reciprocal_rank_fusion

metadata = MetaData()
corpora = Table(
    "retrieval_corpora",
    metadata,
    Column("tenant", String(128), primary_key=True),
    Column("id", String(64), primary_key=True),
    Column("recipe_sha256", String(64), nullable=False),
    Column("documents", JSON, nullable=False),
    Column("chunk_count", Integer, nullable=False),
)
chunks = Table(
    "retrieval_chunks",
    metadata,
    Column("tenant", String(128), primary_key=True),
    Column("corpus_id", String(64), primary_key=True),
    Column("id", String(64), primary_key=True),
    Column("citation", JSON, nullable=False),
    Column("embedding", Vector(384).with_variant(JSON(), "sqlite"), nullable=False),
    ForeignKeyConstraint(
        ["tenant", "corpus_id"],
        ["retrieval_corpora.tenant", "retrieval_corpora.id"],
        ondelete="CASCADE",
    ),
)


class CacheIntegrityError(Exception):
    pass


def corpus_identity(documents, recipe):
    canonical = [d.model_dump() for d in sorted(documents, key=lambda document: document.id)]
    identifier = sha256(
        json.dumps(
            {"documents": canonical, "recipe": recipe, "pipeline": "persistent-source-cosine-v1"},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return identifier, canonical


class PersistentHybridIndex:
    backend = "hybrid_postgres"

    def __init__(self, engine, tenant, documents, encoder):
        if engine.dialect.name != "postgresql":
            raise ValueError("Persistent vector retrieval requires PostgreSQL")
        if not tenant or len(tenant) > 128:
            raise ValueError("Invalid tenant scope")
        if len(documents) > 30 or sum(len(d.text) for d in documents) > 300_000:
            raise ResourceBudgetExceeded("Persistent corpus input budget exceeded")
        if any(d.kind != "knowledge" for d in documents) or len({d.id for d in documents}) != len(
            documents
        ):
            raise ValueError("Unique knowledge documents are required")
        recipe = getattr(encoder, "recipe_sha256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", recipe):
            raise ValueError("Encoder must declare a configuration/runtime recipe digest")
        ensure_ready(engine, bootstrap_empty_sqlite=False)
        self.engine, self._tenant, self.encoder, self.recipe = engine, tenant, encoder, recipe
        self.documents = {d.id: d.model_copy(deep=True) for d in documents}
        self.corpus_id, self.canonical = corpus_identity(list(self.documents.values()), recipe)
        self.cache_reused = self._load()
        if not self.cache_reused:
            built = HybridIndex(list(self.documents.values()), encoder)
            if built.sources and built.vectors.shape[1] != 384:
                raise ValueError("Persistent embedding dimensions must be 384")
            try:
                with scoped_transaction(engine, self._tenant) as connection:
                    connection.execute(
                        insert(corpora).values(
                            tenant=self._tenant,
                            id=self.corpus_id,
                            recipe_sha256=recipe,
                            documents=self.canonical,
                            chunk_count=len(built.sources),
                        )
                    )
                    if built.sources:
                        connection.execute(
                            insert(chunks),
                            [
                                {
                                    "tenant": self._tenant,
                                    "corpus_id": self.corpus_id,
                                    "id": identity(citation),
                                    "citation": citation.model_dump(),
                                    "embedding": vector.tolist(),
                                }
                                for citation, vector in zip(
                                    built.sources, built.vectors, strict=True
                                )
                            ],
                        )
            except IntegrityError:
                # Concurrent duplicate publication rolls back the entire corpus/chunk transaction.
                self.cache_reused = True
            if not self._load():
                raise CacheIntegrityError("Corpus publication did not produce a complete snapshot")
        self.lexical = BM25(list(self.documents.values()), chunks=self.sources)
        self.by_id = {identity(citation): citation for citation in self.sources}

    def _scope(self):
        return (chunks.c.tenant == self._tenant, chunks.c.corpus_id == self.corpus_id)

    def _load(self):
        with scoped_transaction(self.engine, self._tenant) as connection:
            header = (
                connection.execute(
                    select(corpora).where(
                        corpora.c.tenant == self._tenant, corpora.c.id == self.corpus_id
                    )
                )
                .mappings()
                .first()
            )
            if header is None:
                return False
            rows = (
                connection.execute(
                    select(chunks.c.id, chunks.c.citation)
                    .where(*self._scope())
                    .order_by(chunks.c.id)
                    .limit(5001)
                )
                .mappings()
                .all()
            )
        if (
            header["documents"] != self.canonical
            or header["recipe_sha256"] != self.recipe
            or not 0 <= header["chunk_count"] <= 5000
            or len(rows) != header["chunk_count"]
        ):
            raise CacheIntegrityError("Cached corpus identity/count mismatch")
        sources = []
        for row in rows:
            citation = Citation.model_validate(row["citation"])
            document = self.documents.get(citation.document_id)
            if (
                document is None
                or not citation.matches(document)
                or identity(citation) != row["id"]
            ):
                raise CacheIntegrityError("Cached source provenance is invalid")
            sources.append(citation)
        self.sources = sources
        return True

    def search(self, query, limit=3, method="hybrid"):
        if (
            not query.strip()
            or not 1 <= limit <= 100
            or method not in {"lexical", "semantic", "hybrid"}
        ):
            raise ValueError("Invalid retrieval query, limit or method")
        if not self.sources:
            return []
        lexical = self.lexical.search(query, limit=min(100, len(self.sources)))
        if method == "lexical":
            return [
                Hit(c, 1 / (rank + 1), "lexical_rank") for rank, c in enumerate(lexical[:limit])
            ]
        vector = np.asarray(self.encoder.encode([query]), dtype=np.float32)
        if vector.shape != (1, 384) or not np.isfinite(vector).all() or np.linalg.norm(vector) <= 0:
            raise ValueError("Invalid persistent-query embedding")
        vector = vector[0] / np.linalg.norm(vector)
        distance = chunks.c.embedding.cosine_distance(vector.tolist()).label("distance")
        count = limit if method == "semantic" else 20
        with scoped_transaction(self.engine, self._tenant) as connection:
            ranked = (
                connection.execute(
                    select(chunks.c.id, distance)
                    .where(*self._scope())
                    .order_by(distance, chunks.c.id)
                    .limit(count)
                )
                .mappings()
                .all()
            )
        if any(row["id"] not in self.by_id or not np.isfinite(row["distance"]) for row in ranked):
            raise CacheIntegrityError("Persistent retrieval returned an invalid candidate")
        if method == "semantic":
            return [
                Hit(self.by_id[row["id"]], 1 - row["distance"], "pgvector_cosine") for row in ranked
            ]
        fused = reciprocal_rank_fusion(
            [[identity(c) for c in lexical[:20]], [row["id"] for row in ranked]]
        )
        return [
            Hit(self.by_id[key], score, "reciprocal_rank_fusion") for key, score in fused[:limit]
        ]
