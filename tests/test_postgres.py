"""Opt-in real PostgreSQL tests. Every test owns a fresh randomly named schema."""

import json
import os
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from alembic import command
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import URL, make_url

from atlas.api import create_app
from atlas.documents import DocumentStore, quotas
from atlas.domain import Document, ResourceBudgetExceeded
from atlas.execution import execute
from atlas.ingestion import extract_document
from atlas.jobs import JobQueue, LostLease
from atlas.migrations import (
    SchemaNotReady,
    adopt_legacy,
    config,
    ensure_ready,
    lock,
    revision,
    upgrade,
)
from atlas.pg_retrieval import CacheIntegrityError, PersistentHybridIndex, chunks, corpora
from atlas.store import Conflict, Store


class PrivateURL(str):
    def __repr__(self):
        return "<private local PostgreSQL URL>"


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.getenv("ATLAS_POSTGRES_CONFIG"),
        reason="Real PostgreSQL integration config not supplied",
    ),
]


@pytest.fixture
def postgres_url():
    config = json.loads(Path(os.environ["ATLAS_POSTGRES_CONFIG"]).read_text())
    # Never point destructive fixture cleanup at an arbitrary external database.
    if config["host"] != "127.0.0.1" or config["dbname"] != "portfolio_integration":
        pytest.fail("Integration tests require the dedicated local portfolio database")
    url = URL.create(
        "postgresql+psycopg",
        username=config["user"],
        password=config["password"],
        host=config["host"],
        port=config["port"],
        database=config["dbname"],
        query={"sslmode": config["sslmode"]},
    )
    admin = create_engine(url)
    namespace = "atlas_test_" + uuid4().hex
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{namespace}"')
    scoped = url.update_query_dict({"options": "-csearch_path=" + namespace + ",public"})
    migrated = create_engine(scoped)
    upgrade(migrated)
    migrated.dispose()
    try:
        yield PrivateURL(scoped.render_as_string(hide_password=False))
    finally:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{namespace}" CASCADE')
        admin.dispose()


class SyntheticEncoder:
    """384-dimensional authored vectors for persistence correctness, not AI quality."""

    recipe_sha256 = sha256(b"synthetic-persistence-correctness-v1").hexdigest()
    maximum = 256

    def __init__(self):
        self.calls = []

    def token_count(self, value):
        return len(value.split())

    def encode(self, values):
        self.calls.append(list(values))
        rows = []
        for value in values:
            row = np.zeros(384, dtype=np.float32)
            row[0] = int("encrypt" in value.lower())
            row[1] = int("saml" in value.lower())
            if not row.any():
                row[383] = 1
            rows.append(row)
        return np.asarray(rows)


def persistence_documents():
    return [
        Document(
            id="encryption",
            title="Encryption",
            text="AES encryption protects stored data.",
            kind="knowledge",
        ),
        Document(
            id="saml", title="SSO", text="SAML single sign on is available.", kind="knowledge"
        ),
    ]


def test_postgres_persistent_vectors_reopen_without_reembedding_and_isolate_tenants(store):
    documents = persistence_documents()
    first_encoder = SyntheticEncoder()
    first = PersistentHybridIndex(store.engine, "a", documents, first_encoder)
    assert not first.cache_reused and len(first_encoder.calls) == 1
    reopened_encoder = SyntheticEncoder()
    reopened = PersistentHybridIndex(store.engine, "a", documents, reopened_encoder)
    assert reopened.cache_reused and reopened_encoder.calls == []
    hits = reopened.search("SAML authentication", method="semantic")
    assert hits[0].source.document_id == "saml" and hits[0].score == pytest.approx(1)
    assert all(
        hit.source.matches(next(d for d in documents if d.id == hit.source.document_id))
        for hit in hits
    )
    assert reopened.search("SAML authentication", method="hybrid")[0].source.document_id == "saml"
    other = PersistentHybridIndex(store.engine, "b", documents, SyntheticEncoder())
    assert not other.cache_reused and other.corpus_id == first.corpus_id
    changed = [
        documents[0].model_copy(update={"text": "New encryption specification."}),
        documents[1],
    ]
    assert (
        PersistentHybridIndex(store.engine, "a", changed, SyntheticEncoder()).corpus_id
        != first.corpus_id
    )
    with store.engine.connect() as connection:
        assert len(connection.execute(select(corpora)).all()) == 3


def test_postgres_persistent_cache_atomic_rollback_and_concurrent_publication(store):
    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO retrieval_chunks"):
            raise RuntimeError("Authored cache failure after corpus insert")

    event.listen(store.engine, "before_cursor_execute", fail)
    with pytest.raises(RuntimeError):
        PersistentHybridIndex(store.engine, "a", persistence_documents(), SyntheticEncoder())
    event.remove(store.engine, "before_cursor_execute", fail)
    with store.engine.connect() as connection:
        assert connection.execute(select(corpora)).all() == []
    with ThreadPoolExecutor(max_workers=4) as pool:
        caches = list(
            pool.map(
                lambda _: PersistentHybridIndex(
                    store.engine, "a", persistence_documents(), SyntheticEncoder()
                ),
                range(4),
            )
        )
    assert len({cache.corpus_id for cache in caches}) == 1
    with store.engine.connect() as connection:
        assert len(connection.execute(select(corpora)).all()) == 1
        assert len(connection.execute(select(chunks)).all()) == 2


def test_postgres_persistent_cache_rejects_tampered_sources_and_preserves_data_on_downgrade(store):
    index = PersistentHybridIndex(store.engine, "a", persistence_documents(), SyntheticEncoder())
    with store.engine.begin() as connection:
        row = connection.execute(select(chunks).where(chunks.c.tenant == "a")).mappings().first()
        forged = {**row["citation"], "quote": "forged"}
        connection.execute(chunks.update().where(chunks.c.id == row["id"]).values(citation=forged))
    with pytest.raises(CacheIntegrityError):
        PersistentHybridIndex(store.engine, "a", persistence_documents(), SyntheticEncoder())
    with pytest.raises(RuntimeError, match="contains data"):
        with store.engine.begin() as connection:
            lock(connection)
            command.downgrade(config(connection), "0002")
    with store.engine.connect() as connection:
        assert revision(connection) == "0005"
        assert connection.execute(select(corpora.c.id)).scalar_one() == index.corpus_id


@pytest.mark.embeddings
@pytest.mark.skipif(
    not Path(".cache/models/minilm/model.safetensors").exists(),
    reason="Pinned local embedding model not prepared",
)
def test_postgres_real_cpu_encoder_retrieval_and_new_process_cache_reuse(store, postgres_url):
    from atlas.semantic import LocalEncoder
    from chaoslab.retrieval import score

    dataset = json.loads(Path("datasets/retrieval.json").read_text())
    documents = [Document.model_validate(value) for value in dataset["documents"]]
    encoder = LocalEncoder()
    first = PersistentHybridIndex(store.engine, "a", documents, encoder)
    assert not first.cache_reused
    for query in dataset["queries"]:
        hits = first.search(query["query"], method="hybrid")
        ranked = [hit.source.document_id for hit in hits]
        assert score(ranked, query["relevant_document_ids"], 3)["recall_at_k"] == 1
        assert all(
            hit.source.matches(next(d for d in documents if d.id == hit.source.document_id))
            for hit in hits
        )
    # A separate process must use stored vectors rather than silently rebuilding sources.
    code = """import json,sys
from pathlib import Path
from sqlalchemy import create_engine
from atlas.domain import Document
from atlas.semantic import LocalEncoder
from atlas.pg_retrieval import PersistentHybridIndex
request=json.load(sys.stdin)
documents=[Document.model_validate(d) for d in json.loads(Path('datasets/retrieval.json').read_text())['documents']]
encoder=LocalEncoder()
def reject_source_encoding(values):
    raise RuntimeError('Source vectors should have been reused')
encoder.encode=reject_source_encoding
engine=create_engine(request['url'])
cache=PersistentHybridIndex(engine,'a',documents,encoder)
print(json.dumps({'cache_reused':cache.cache_reused,'corpus_id':cache.corpus_id,'chunks':len(cache.sources)}))
engine.dispose()
"""
    child = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps({"url": postgres_url}),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 0, "Isolated real-encoder cache-reuse process failed"
    result = json.loads(child.stdout)
    assert result == {
        "cache_reused": True,
        "corpus_id": first.corpus_id,
        "chunks": len(first.sources),
    }


@pytest.fixture
def body():
    return json.loads(Path("datasets/demo.json").read_text())


@pytest.fixture
def store(postgres_url):
    store = Store(postgres_url)
    DocumentStore(store)
    yield store
    store.engine.dispose()


def test_postgres_tenant_scoping_idempotency_and_review_race(store, body):
    payload = execute(body)
    first = store.save("a", "pg-request", "digest", payload, "alice")
    assert store.save("a", "pg-request", "digest", payload, "alice")["id"] == first["id"]
    assert store.list("b") == []
    item = next(a for a in first["assessments"] if a["status"] == "evidence_found")

    def review(actor):
        try:
            store.review(
                "a",
                actor,
                first["id"],
                item["requirement"]["id"],
                1,
                "approved",
                "Synthetic source checked",
            )
            return "accepted"
        except Conflict:
            return "stale"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(review, ["alice", "bob", "carol", "dan"]))
    assert outcomes.count("accepted") == 1 and outcomes.count("stale") == 3
    assert len(store.events("a", first["id"])) == 2


def test_postgres_competing_workers_publish_each_job_once(store, body):
    queue = JobQueue(store)
    submitted = [queue.submit("a", "alice", f"pg-job-{n:03}", body)["id"] for n in range(24)]

    def consume(_):
        published = []
        while claim := queue.claim(60):
            queue.complete(claim, execute(claim.input))
            published.append(claim.id)
        return published

    with ThreadPoolExecutor(max_workers=8) as pool:
        processed = [identifier for batch in pool.map(consume, range(8)) for identifier in batch]
    assert sorted(processed) == sorted(submitted)
    assert len(set(processed)) == 24 and len(store.list("a")) == 24
    assert all(queue.get("a", identifier)["attempts"] == 1 for identifier in submitted)


def test_postgres_expired_lease_and_cancellation_fence_old_owners(store, body):
    now = datetime(2040, 1, 1, tzinfo=UTC)
    queue = JobQueue(store, clock=lambda: now)
    first = queue.submit("a", "alice", "pg-lease-recovery", body)
    stale = queue.claim(5)
    now += timedelta(seconds=6)
    current = queue.claim(5)
    with pytest.raises(LostLease):
        queue.complete(stale, execute(body))
    queue.complete(current, execute(body))
    assert queue.get("a", first["id"])["attempts"] == 2
    second = queue.submit("a", "alice", "pg-cancellation", body)
    cancelled = queue.claim(5)
    queue.cancel("a", "alice", second["id"])
    with pytest.raises(LostLease):
        queue.complete(cancelled, execute(body))
    assert len(store.list("a")) == 1


def test_postgres_atomic_publication_rolls_back_result_and_state(store, body, monkeypatch):
    queue = JobQueue(store)
    job = queue.submit("a", "alice", "pg-rollback", body)
    claim = queue.claim()
    original = store.persist_snapshot

    def fail(connection, *args):
        original(connection, *args)
        raise RuntimeError("Authored publication failure")

    monkeypatch.setattr(store, "persist_snapshot", fail)
    with pytest.raises(RuntimeError):
        queue.complete(claim, execute(body))
    assert store.list("a") == []
    assert queue.get("a", job["id"])["status"] == "running"
    assert not any(event["action"] == "job.succeeded" for event in queue.events("a", job["id"]))
    monkeypatch.setattr(store, "persist_snapshot", original)
    queue.complete(claim, execute(body))
    assert queue.get("a", job["id"])["status"] == "succeeded"


def test_postgres_duplicate_submission_and_storage_quota_races(store, body):
    queue = JobQueue(store)
    with ThreadPoolExecutor(max_workers=8) as pool:
        admitted = list(
            pool.map(lambda _: queue.submit("a", "alice", "pg-one-key", body)["id"], range(8))
        )
    assert len(set(admitted)) == 1
    raw = Path("datasets/documents/municipal-rfp.pdf").read_bytes()
    document = extract_document(raw, "pdf", "RFP", "rfp")
    documents = DocumentStore(store, maximum_bytes=len(raw), maximum_count=1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        saved = list(pool.map(lambda _: documents.save("a", "alice", document, raw), range(4)))
    assert all(d == document for d in saved)
    with store.engine.connect() as connection:
        row = connection.execute(select(quotas)).mappings().one()
        assert row["bytes"] == len(raw) and row["count"] == 1
    with pytest.raises(ResourceBudgetExceeded):
        documents.save("a", "alice", document.model_copy(update={"id": "another"}), raw)


def test_postgres_http_upload_and_job_publication(runtime_roles):
    principals = {
        "reviewer": {"tenant": "a", "actor": "alice", "role": "reviewer"},
        "other": {"tenant": "b", "actor": "bob", "role": "reviewer"},
    }
    app = create_app(runtime_roles["api"], principals)
    headers = {"Authorization": "Bearer reviewer", "Idempotency-Key": "pg-http-job"}
    with TestClient(app) as client:
        documents = []
        for filename, format, kind in [
            ("municipal-rfp.pdf", "pdf", "rfp"),
            ("capability-register.docx", "docx", "knowledge"),
        ]:
            response = client.post(
                "/api/documents",
                params={"format": format, "kind": kind, "title": filename},
                content=Path("datasets/documents", filename).read_bytes(),
                headers=headers,
            )
            assert response.status_code == 201
            documents.append(response.json())
        job = client.post(
            "/api/jobs", json={"rfp": documents[0], "knowledge": [documents[1]]}, headers=headers
        ).json()
        worker_store = Store(runtime_roles["worker"], purpose="worker")
        worker_queue = JobQueue(worker_store)
        claim = worker_queue.claim()
        worker_queue.complete(claim, execute(claim.input))
        worker_store.engine.dispose()
        status = client.get("/api/jobs/" + job["id"], headers=headers).json()
        assert status["status"] == "succeeded"
        assert (
            client.get(
                "/api/runs/" + status["result_id"], headers={"Authorization": "Bearer other"}
            ).status_code
            == 404
        )
    app.state.store.engine.dispose()


def test_pgvector_extension_persists_and_searches_vectors(postgres_url):
    engine = create_engine(postgres_url)
    try:
        with engine.begin() as connection:
            # Extension belongs to the disposable test schema, never a shared application schema.
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            connection.exec_driver_sql(
                "CREATE TABLE vector_fixture (id text PRIMARY KEY, embedding vector(3))"
            )
            connection.execute(
                text(
                    "INSERT INTO vector_fixture VALUES ('a', '[1,0,0]'), ('b', '[0,1,0]'), ('c', '[0,0,1]')"
                )
            )
            ranked = (
                connection.execute(
                    text("SELECT id FROM vector_fixture ORDER BY embedding <=> '[1,0.1,0]' LIMIT 2")
                )
                .scalars()
                .all()
            )
            assert ranked == ["a", "b"]
    finally:
        engine.dispose()


def test_postgres_index_migration_rollback_preserves_revision_and_rows(store):
    with store.engine.begin() as connection:
        lock(connection)
        command.downgrade(config(connection), "0001")
        connection.execute(
            text(
                "INSERT INTO audit VALUES ('migration-fixture','a','alice','fixture','resource','2026-10-14',:details)"
            ),
            {"details": json.dumps({"synthetic": True})},
        )
    with pytest.raises(SchemaNotReady):
        ensure_ready(store.engine)

    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("CREATE INDEX ix_audit_tenant_resource_time"):
            raise RuntimeError("Authored PostgreSQL migration failure")

    event.listen(store.engine, "before_cursor_execute", fail)
    with pytest.raises(RuntimeError):
        upgrade(store.engine)
    event.remove(store.engine, "before_cursor_execute", fail)
    with store.engine.connect() as connection:
        assert revision(connection) == "0001"
        assert "ix_runs_tenant_created" not in {
            index["name"] for index in inspect(connection).get_indexes("runs")
        }
        assert (
            connection.execute(
                text("SELECT count(*) FROM audit WHERE id='migration-fixture'")
            ).scalar_one()
            == 1
        )
    upgrade(store.engine)
    ensure_ready(store.engine)


def test_postgres_verified_legacy_adoption_preserves_existing_audit(store):
    with store.engine.begin() as connection:
        lock(connection)
        command.downgrade(config(connection), "0001")
        connection.exec_driver_sql("DROP TABLE alembic_version")
        connection.execute(
            text(
                "INSERT INTO audit VALUES ('legacy-preserved','a','alice','fixture','resource','2026-10-14',:details)"
            ),
            {"details": json.dumps({"synthetic": True})},
        )
    with pytest.raises(SchemaNotReady):
        ensure_ready(store.engine)
    adopt_legacy(store.engine)
    ensure_ready(store.engine)
    with store.engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM audit WHERE id='legacy-preserved'")
            ).scalar_one()
            == 1
        )


def test_postgres_membership_cas_revocation_and_audit(store):
    from atlas.security.memberships import MembershipChange, MembershipRegistry, memberships
    from atlas.security.tokens import VerifiedSubject
    from atlas.store import audit

    registry = MembershipRegistry(store)
    body = {
        "issuer": "https://identity.example.test",
        "subject": "alice",
        "tenant": "a",
        "role": "viewer",
        "active": True,
        "expected_version": 0,
    }
    registry.change(MembershipChange(**body))
    subject = VerifiedSubject(body["issuer"], "alice", 2000000000)
    assert registry.resolve(subject, "a")["role"] == "viewer"
    assert registry.resolve(subject, "b") is None
    assert registry.resolve(VerifiedSubject("https://other.test", "alice", 2000000000), "a") is None

    def attempt(number):
        try:
            registry.change(MembershipChange(**{**body, "expected_version": 1, "role": "admin"}))
            return True
        except Conflict:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(16))) == 1
    registry.change(MembershipChange(**{**body, "expected_version": 2, "active": False}))
    assert registry.resolve(subject, "a") is None
    with store.engine.connect() as connection:
        assert connection.execute(select(memberships.c.version)).scalar_one() == 3
        assert len(connection.execute(select(audit)).all()) == 3
    with pytest.raises(RuntimeError, match="contains data"):
        with store.engine.begin() as connection:
            lock(connection)
            command.downgrade(config(connection), "0003")
    with store.engine.connect() as connection:
        assert revision(connection) == "0005"
        assert connection.execute(select(memberships.c.version)).scalar_one() == 3


@pytest.fixture
def runtime_roles(postgres_url):
    """Real SCRAM logins, not SET ROLE on an administrator session."""
    url = make_url(postgres_url)
    admin = create_engine(url)
    names = {purpose: "atlas_test_" + purpose + "_" + uuid4().hex for purpose in ("api", "worker")}
    passwords = {purpose: secrets.token_urlsafe(32) for purpose in names}
    api = {
        "runs": "SELECT, INSERT",
        "reviews": "SELECT, INSERT, UPDATE",
        "audit": "SELECT, INSERT",
        "jobs": "SELECT, INSERT, UPDATE",
        "documents": "SELECT, INSERT",
        "document_quotas": "SELECT, INSERT, UPDATE",
        "retrieval_corpora": "SELECT, INSERT",
        "retrieval_chunks": "SELECT, INSERT",
        "memberships": "SELECT",
        "alembic_version": "SELECT",
    }
    worker = {
        "runs": "SELECT, INSERT",
        "reviews": "SELECT, INSERT",
        "audit": "SELECT, INSERT",
        "jobs": "SELECT, UPDATE",
        "documents": "SELECT",
        "alembic_version": "SELECT",
        "retrieval_corpora": "SELECT, INSERT",
        "retrieval_chunks": "SELECT, INSERT",
    }
    created = []
    try:
        with admin.begin() as connection:
            schema = connection.execute(text("SELECT current_schema()")).scalar_one()
            driver = connection.connection.driver_connection
            for purpose, privileges in (("api", api), ("worker", worker)):
                role = sql.Identifier(names[purpose])
                bypass = sql.SQL("BYPASSRLS" if purpose == "worker" else "NOBYPASSRLS")
                driver.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT {} PASSWORD {}"
                    ).format(role, bypass, sql.Literal(passwords[purpose]))
                )
                created.append(names[purpose])
                driver.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), role)
                )
                for table, permission in privileges.items():
                    driver.execute(
                        sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                            sql.SQL(permission), sql.Identifier(schema, table), role
                        )
                    )
        yield {
            purpose: PrivateURL(
                url.set(username=names[purpose], password=passwords[purpose]).render_as_string(
                    hide_password=False
                )
            )
            for purpose in names
        }
    finally:
        with admin.begin() as connection:
            driver = connection.connection.driver_connection
            for name in created:
                driver.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(name)))
                driver.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))
        admin.dispose()


def test_postgres_restricted_login_row_policies_and_pool_reset(store, runtime_roles, body):
    from sqlalchemy.exc import DBAPIError

    from atlas.db_scope import scoped_transaction
    from atlas.jobs import jobs
    from atlas.store import runs

    payload = execute(body)
    a = store.save("a", "scope-a", "hash-a", payload, "alice")
    b = store.save("b", "scope-b", "hash-b", payload, "bob")
    app = Store(runtime_roles["api"], purpose="api")
    try:
        assert [row["id"] for row in app.list("a")] == [a["id"]]
        assert [row["id"] for row in app.list("b")] == [b["id"]]
        queue = JobQueue(app)
        ja = queue.submit("a", "alice", "scope-job-a", body)
        jb = queue.submit("b", "bob", "scope-job-b", body)
        indexed = PersistentHybridIndex(
            app.engine, "a", persistence_documents(), SyntheticEncoder()
        )
        PersistentHybridIndex(app.engine, "b", persistence_documents(), SyntheticEncoder())
        assert indexed.search("SAML single sign on")[0].source.document_id == "saml"
        with scoped_transaction(app.engine, "a") as connection:
            backend = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
            assert connection.execute(select(runs.c.tenant)).scalars().all() == ["a"]
            assert connection.execute(select(corpora.c.tenant)).scalars().all() == ["a"]
            assert set(connection.execute(select(chunks.c.tenant)).scalars()) == {"a"}
            connection.execute(text("SELECT set_config('atlas.worker','true',true)"))
            assert connection.execute(select(jobs.c.tenant)).scalars().all() == ["a"]
            assert (
                connection.execute(
                    jobs.update().where(jobs.c.id == jb["id"]).values(status="cancelled")
                ).rowcount
                == 0
            )
        with app.engine.connect() as connection:
            assert connection.execute(text("SELECT pg_backend_pid()")).scalar_one() == backend
            assert connection.execute(select(runs.c.id)).all() == []
        with pytest.raises(DBAPIError):
            with scoped_transaction(app.engine, "a") as connection:
                connection.execute(jobs.update().where(jobs.c.id == ja["id"]).values(tenant="b"))
        with pytest.raises(RuntimeError, match="Injected rollback"):
            with scoped_transaction(app.engine, "b") as connection:
                assert connection.execute(select(runs.c.tenant)).scalars().all() == ["b"]
                raise RuntimeError("Injected rollback")
        with app.engine.connect() as connection:
            assert connection.execute(select(runs.c.id)).all() == []
        assert queue.get("a", ja["id"])["status"] == "queued"
    finally:
        app.engine.dispose()


def test_postgres_restricted_membership_and_worker_grants(store, runtime_roles):
    from sqlalchemy.exc import DBAPIError

    from atlas.db_scope import scoped_transaction
    from atlas.security.memberships import MembershipChange, MembershipRegistry, memberships
    from atlas.security.tokens import VerifiedSubject
    from atlas.store import reviews

    registry = MembershipRegistry(store)
    base = {
        "issuer": "https://identity.example.test",
        "subject": "alice",
        "tenant": "a",
        "role": "reviewer",
        "active": True,
        "expected_version": 0,
    }
    for overrides in (
        {},
        {"tenant": "b"},
        {"subject": "bob"},
        {"issuer": "https://other.example.test"},
    ):
        registry.change(MembershipChange(**{**base, **overrides}))
    app = Store(runtime_roles["api"], purpose="api")
    worker = Store(runtime_roles["worker"], purpose="worker")
    try:
        subject = VerifiedSubject(base["issuer"], "alice", 2000000000)
        app_registry = MembershipRegistry(app)
        assert app_registry.resolve(subject, None) is None
        assert app_registry.resolve(subject, "a")["tenant"] == "a"
        with scoped_transaction(
            app.engine, issuer=subject.issuer, subject=subject.subject
        ) as connection:
            rows = connection.execute(select(memberships)).mappings().all()
            assert {row["tenant"] for row in rows} == {"a", "b"}
            assert {row["issuer"] for row in rows} == {subject.issuer}
            assert {row["subject"] for row in rows} == {"alice"}
        with app.engine.connect() as connection:
            assert connection.execute(select(memberships)).all() == []
        with pytest.raises(DBAPIError):
            app_registry.change(
                MembershipChange(**{**base, "expected_version": 1, "role": "admin"})
            )
        registry.change(MembershipChange(**{**base, "expected_version": 1, "active": False}))
        assert app_registry.resolve(subject, "a") is None
        assert app_registry.resolve(subject, None)["tenant"] == "b"
        with pytest.raises(DBAPIError):
            with worker.engine.begin() as connection:
                connection.execute(select(memberships))
        with pytest.raises(DBAPIError):
            with worker.engine.begin() as connection:
                connection.execute(reviews.update().values(decision="approved"))
        with pytest.raises(DBAPIError):
            with app.engine.begin() as connection:
                connection.execute(text("TRUNCATE runs"))
    finally:
        app.engine.dispose()
        worker.engine.dispose()


def test_postgres_runtime_role_guard_and_policy_drift(store, runtime_roles, postgres_url):
    from atlas.db_scope import UnsafeDatabaseRole, check_runtime_role
    from atlas.migration_scripts.versions.r0005_row_security import expression

    app = create_engine(runtime_roles["api"])
    worker = create_engine(runtime_roles["worker"])
    try:
        with pytest.raises(UnsafeDatabaseRole):
            create_app(postgres_url, {})
        with pytest.raises(UnsafeDatabaseRole):
            check_runtime_role(worker, "api")
        with pytest.raises(UnsafeDatabaseRole):
            check_runtime_role(app, "worker")
        with store.engine.begin() as connection:
            connection.connection.driver_connection.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(make_url(runtime_roles["worker"]).username),
                    sql.Identifier(make_url(runtime_roles["api"]).username),
                )
            )
        with pytest.raises(UnsafeDatabaseRole):
            check_runtime_role(app, "api")
    finally:
        app.dispose()
        worker.dispose()
    changes = [
        (
            "ALTER TABLE runs DISABLE ROW LEVEL SECURITY",
            "ALTER TABLE runs ENABLE ROW LEVEL SECURITY",
        ),
        (
            "ALTER TABLE runs NO FORCE ROW LEVEL SECURITY",
            "ALTER TABLE runs FORCE ROW LEVEL SECURITY",
        ),
        (
            "ALTER POLICY atlas_identity ON runs USING (true)",
            "ALTER POLICY atlas_identity ON runs USING (" + expression("runs") + ")",
        ),
        (
            "CREATE POLICY extra_permissive ON runs USING (true)",
            "DROP POLICY extra_permissive ON runs",
        ),
    ]
    for change, restore in changes:
        with store.engine.begin() as connection:
            connection.execute(text(change))
        try:
            with pytest.raises(SchemaNotReady, match="row policy drift"):
                ensure_ready(store.engine)
        finally:
            with store.engine.begin() as connection:
                connection.execute(text(restore))
        ensure_ready(store.engine)


def test_postgres_model_jobs_pinned_publication_review_and_rollback(runtime_roles):
    """Real restricted database sessions; controlled model output, no provider calls."""
    from copy import deepcopy

    from test_model_jobs import spec

    from atlas.execution import prepare_model_publication
    from atlas.models.intelligence import MODEL_PIPELINE_VERSION
    from atlas.store import NotFound
    from atlas.worker import process_once

    api_store = Store(runtime_roles["api"], purpose="api")
    worker_store = Store(runtime_roles["worker"], purpose="worker")
    admission, worker = JobQueue(api_store), JobQueue(worker_store)
    body = {
        "rfp": {
            "id": "r",
            "title": "Synthetic RFP",
            "kind": "rfp",
            "text": "The platform must support SAML federation.",
        },
        "knowledge": [
            {
                "id": "k",
                "title": "Synthetic policy",
                "kind": "knowledge",
                "text": "The platform supports SAML federation.",
            }
        ],
    }

    def controlled(claim):
        report = execute(claim.input)
        report.update(pipeline_version=MODEL_PIPELINE_VERSION, live_model=True)
        report["provisional_relations"] = {
            a["requirement"]["id"]: "supported" for a in report["assessments"]
        }
        return prepare_model_publication(claim.input, report, estimated_cost_usd=None)

    try:
        job = admission.submit(
            "a",
            "alice",
            "pinned-model",
            body,
            pipeline_version=MODEL_PIPELINE_VERSION,
            model_spec=spec(),
        )
        assert not process_once(worker)
        assert process_once(worker, model_executor=controlled)
        status = admission.get("a", job["id"])
        assert status["status"] == "succeeded" and status["attempts"] == 1
        result = api_store.get("a", status["result_id"])
        assert result["model_config_sha256"] == job["model_config_sha256"]
        assert result["model_cost_usd"] is None
        item = result["assessments"][0]
        assert item["review_state"] == "pending"
        with pytest.raises(NotFound):
            api_store.get("b", result["id"])
        api_store.review(
            "a",
            "alice",
            result["id"],
            item["requirement"]["id"],
            1,
            "approved",
            "Reviewed synthetic source.",
        )
        assert api_store.get("a", result["id"])["assessments"][0]["review_state"] == "approved"
        forged = admission.submit(
            "a",
            "alice",
            "forged-model",
            body,
            pipeline_version=MODEL_PIPELINE_VERSION,
            model_spec=spec(),
        )

        def tampered(claim):
            payload = deepcopy(controlled(claim))
            payload["model_config_sha256"] = "a" * 64
            return payload

        assert process_once(worker, model_executor=tampered)
        assert admission.get("a", forged["id"])["status"] == "failed"
        assert len(api_store.list("a")) == 1
        assert api_store.list("b") == []
    finally:
        api_store.engine.dispose()
        worker_store.engine.dispose()
