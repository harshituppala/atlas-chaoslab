"""Synthetic backup fixture and canonical table digest, run inside the local initializer.

Never accepts a database URL or arbitrary host. Controlled vectors test persistence,
not embedding or retrieval quality. Only digests/counts leave the trusted operator.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from psycopg import sql
from sqlalchemy import inspect

from atlas.documents import DocumentStore
from atlas.domain import Document
from atlas.ingestion import extract_document
from atlas.local_stack import database_url, load_secret
from atlas.pg_retrieval import PersistentHybridIndex
from atlas.security.memberships import MembershipChange, MembershipRegistry
from atlas.security.tokens import VerifiedSubject
from atlas.store import Store


class ControlledEncoder:
    recipe_sha256 = hashlib.sha256(b"backup-persistence-fixture-v1").hexdigest()
    maximum = 256

    def __init__(self, reject_encoding=False):
        self.reject_encoding = reject_encoding

    def token_count(self, value):
        return len(value.split())

    def encode(self, values):
        if self.reject_encoding:
            raise RuntimeError("Restored cache must not silently re-encode source documents")
        rows = np.zeros((len(values), 384), dtype=np.float32)
        for index, value in enumerate(values):
            rows[index, 0 if "saml" in value.lower() else 1] = 1
        return rows


def canonical_tables(connection):
    tables = inspect(connection).get_table_names(schema="atlas")
    output = {}
    for table in sorted(tables):
        query = sql.SQL("SELECT row_to_json(t)::text FROM {} AS t").format(
            sql.Identifier("atlas", table)
        )
        rows = sorted(connection.exec_driver_sql(query.as_string()).scalars().all())
        output[table] = {
            "rows": len(rows),
            "sha256": hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest(),
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seed", "manifest", "verify"])
    args = parser.parse_args()
    store = Store(
        database_url("atlas_owner", load_secret("operator")["owner_password"]).render_as_string(
            hide_password=False
        )
    )
    try:
        if args.action == "manifest":
            with store.engine.begin() as connection:
                print(json.dumps(canonical_tables(connection)))
            return
        raw = Path("datasets/documents/municipal-rfp.pdf").read_bytes()
        upload = extract_document(raw, "pdf", "Synthetic restore fixture", "rfp")
        documents = [
            Document.model_validate(d)
            for d in json.loads(Path("datasets/demo.json").read_text())["knowledge"]
        ]
        registry = MembershipRegistry(store)
        if args.action == "seed":
            DocumentStore(store).save("a", "recovery-operator", upload, raw)
            registry.change(
                MembershipChange(
                    issuer="https://identity.example.invalid",
                    subject="synthetic-recovery-reviewer",
                    tenant="a",
                    role="reviewer",
                    active=True,
                    expected_version=0,
                )
            )
            cache = PersistentHybridIndex(store.engine, "a", documents, ControlledEncoder())
            assert not cache.cache_reused
            print(
                json.dumps(
                    {
                        "seeded_uploads": 1,
                        "seeded_memberships": 1,
                        "seeded_vector_chunks": len(cache.sources),
                    }
                )
            )
            return
        restored_raw, restored_document = DocumentStore(store).original("a", upload.id)
        assert restored_raw == raw and restored_document == upload
        assert registry.resolve(
            VerifiedSubject(
                "https://identity.example.invalid", "synthetic-recovery-reviewer", 2_000_000_000
            ),
            "a",
        ) == {
            "tenant": "a",
            "actor": "synthetic-recovery-reviewer",
            "role": "reviewer",
        }
        cache = PersistentHybridIndex(
            store.engine, "a", documents, ControlledEncoder(reject_encoding=True)
        )
        assert cache.cache_reused and cache.sources
        assert all(source.matches(cache.documents[source.document_id]) for source in cache.sources)
        print(
            json.dumps(
                {
                    "original_bytes_match": True,
                    "source_map_matches": True,
                    "membership_restored": True,
                    "vector_cache_reused_without_encoding": True,
                    "cached_citations_valid": len(cache.sources),
                }
            )
        )
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
