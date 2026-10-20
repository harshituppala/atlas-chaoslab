"""Tenant-scoped transactional persistence. Reviews use compare-and-swap."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.pool import StaticPool

from .db_scope import check_runtime_role, scoped_transaction

metadata = MetaData()
runs = Table(
    "runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant", String, nullable=False),
    Column("key", String, nullable=False),
    Column("fingerprint", String, nullable=False),
    Column("created", String, nullable=False),
    Column("payload", JSON, nullable=False),
    UniqueConstraint("tenant", "key"),
)
reviews = Table(
    "reviews",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("requirement_id", String, primary_key=True),
    Column("tenant", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("decision", String, nullable=False),
    Column("note", Text, nullable=False),
)
audit = Table(
    "audit",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant", String, nullable=False),
    Column("actor", String, nullable=False),
    Column("action", String, nullable=False),
    Column("resource", String, nullable=False),
    Column("time", String, nullable=False),
    Column("details", JSON, nullable=False),
)
Index("ix_runs_tenant_created", runs.c.tenant, runs.c.created)
Index("ix_audit_tenant_resource_time", audit.c.tenant, audit.c.resource, audit.c.time)


def now():
    return datetime.now(UTC).isoformat()


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class Store:
    def __init__(self, url, *, purpose="internal"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if url == "sqlite://":
            kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, **(kwargs if url.startswith("sqlite") else {}))
        from .migrations import ensure_ready

        try:
            ensure_ready(self.engine)
            check_runtime_role(self.engine, purpose)
        except Exception:
            self.engine.dispose()
            raise
        if self.engine.dialect.name == "sqlite" and self.engine.url.database not in {
            None,
            ":memory:",
        }:
            # Local source snapshots and retained originals are private to this OS user.
            Path(self.engine.url.database).chmod(0o600)

    def lookup_key(self, tenant, key):
        with scoped_transaction(self.engine, tenant) as conn:
            row = (
                conn.execute(select(runs).where(runs.c.tenant == tenant, runs.c.key == key))
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def save(self, tenant, key, fingerprint, payload, actor):
        identifier = str(uuid4())
        from sqlalchemy.exc import IntegrityError

        try:
            with scoped_transaction(self.engine, tenant) as conn:
                self.persist_snapshot(conn, identifier, tenant, key, fingerprint, payload, actor)
        except IntegrityError:
            existing = self.lookup_key(tenant, key)
            if existing is None or existing["fingerprint"] != fingerprint:
                raise Conflict("Idempotency key reused with different content") from None
            identifier = existing["id"]
        return self.get(tenant, identifier)

    def persist_snapshot(self, conn, identifier, tenant, key, fingerprint, payload, actor):
        """Caller owns the transaction so a job can publish its result atomically."""
        conn.execute(
            insert(runs).values(
                id=identifier,
                tenant=tenant,
                key=key,
                fingerprint=fingerprint,
                created=now(),
                payload=payload,
            )
        )
        for item in payload["assessments"]:
            conn.execute(
                insert(reviews).values(
                    run_id=identifier,
                    requirement_id=item["requirement"]["id"],
                    tenant=tenant,
                    version=1,
                    decision="pending",
                    note="",
                )
            )
        self._audit(
            conn, tenant, actor, "analysis.created", identifier, {"fingerprint": fingerprint}
        )

    def get(self, tenant, identifier):
        with scoped_transaction(self.engine, tenant) as conn:
            row = (
                conn.execute(select(runs).where(runs.c.tenant == tenant, runs.c.id == identifier))
                .mappings()
                .first()
            )
            if row is None:
                raise NotFound()
            payload = dict(row["payload"])
            decisions = {
                r["requirement_id"]: r
                for r in conn.execute(
                    select(reviews).where(
                        reviews.c.tenant == tenant, reviews.c.run_id == identifier
                    )
                ).mappings()
            }
            for item in payload["assessments"]:
                item["review_state"] = decisions[item["requirement"]["id"]]["decision"]
                item["version"] = decisions[item["requirement"]["id"]]["version"]
                item["review_note"] = decisions[item["requirement"]["id"]]["note"]
            return {"id": identifier, "created": row["created"], **payload}

    def list(self, tenant):
        with scoped_transaction(self.engine, tenant) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    select(runs.c.id, runs.c.created)
                    .where(runs.c.tenant == tenant)
                    .order_by(runs.c.created.desc())
                    .limit(100)
                ).mappings()
            ]

    def review(self, tenant, actor, run_id, requirement_id, version, decision, note):
        payload = self.get(tenant, run_id)
        item = next(
            (i for i in payload["assessments"] if i["requirement"]["id"] == requirement_id), None
        )
        if item is None:
            raise NotFound()
        if decision == "approved" and item["status"] != "evidence_found":
            raise Conflict("Resolve missing or conflicting evidence before approval")
        with scoped_transaction(self.engine, tenant) as conn:
            changed = conn.execute(
                update(reviews)
                .where(
                    reviews.c.tenant == tenant,
                    reviews.c.run_id == run_id,
                    reviews.c.requirement_id == requirement_id,
                    reviews.c.version == version,
                )
                .values(version=version + 1, decision=decision, note=note)
            ).rowcount
            if changed != 1:
                raise Conflict("Review changed; refresh before retrying")
            self._audit(
                conn,
                tenant,
                actor,
                "review." + decision,
                run_id,
                {"requirement_id": requirement_id, "version": version + 1, "note": note},
            )
        return self.get(tenant, run_id)

    def _audit(self, conn, tenant, actor, action, resource, details):
        conn.execute(
            insert(audit).values(
                id=str(uuid4()),
                tenant=tenant,
                actor=actor,
                action=action,
                resource=resource,
                time=now(),
                details=details,
            )
        )

    def events(self, tenant, identifier):
        self.get(tenant, identifier)
        with scoped_transaction(self.engine, tenant) as conn:
            return [
                dict(r)
                for r in conn.execute(
                    select(audit)
                    .where(audit.c.tenant == tenant, audit.c.resource == identifier)
                    .order_by(audit.c.time)
                ).mappings()
            ]
