"""Durable at-least-once computation with fenced, atomic result publication.

The queue is the existing database. Claims use a conditional UPDATE rather than
requiring a second broker. Workers are trusted processes, never public clients.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    and_,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from .db_scope import scoped_transaction
from .execution import PIPELINE_VERSION, fingerprint, validate_model_snapshot, validate_publication
from .models.intelligence import MODEL_PIPELINE_VERSION
from .models.job_spec import ModelJobSpec
from .store import Conflict, NotFound, Store, metadata

TERMINAL = {"succeeded", "failed", "cancelled"}

jobs = Table(
    "jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("tenant", String, nullable=False),
    Column("key", String, nullable=False),
    Column("fingerprint", String, nullable=False),
    Column("actor", String, nullable=False),
    Column("pipeline_version", String, nullable=False),
    Column("input", JSON, nullable=False),
    Column("status", String, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("max_attempts", Integer, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("lease_until", DateTime(timezone=True)),
    Column("lease_token", String),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("result_id", String),
    Column("error_code", String),
    UniqueConstraint("tenant", "key", name="uq_jobs_tenant_key"),
)
Index("ix_jobs_claim", jobs.c.status, jobs.c.available_at, jobs.c.lease_until)
Index("ix_jobs_tenant_created", jobs.c.tenant, jobs.c.created_at)


class LostLease(Exception):
    """Ownership expired, was cancelled, or was replaced by another attempt."""


@dataclass(frozen=True)
class Claim:
    id: str
    tenant: str
    actor: str
    token: str
    attempts: int
    pipeline_version: str
    input: dict


def utcnow():
    return datetime.now(UTC)


class JobQueue:
    def __init__(self, store: Store, clock=utcnow):
        self.store, self.clock = store, clock

    def submit(
        self,
        tenant,
        actor,
        key,
        body,
        max_attempts=3,
        *,
        pipeline_version=PIPELINE_VERSION,
        model_spec=None,
    ):
        if pipeline_version not in {PIPELINE_VERSION, MODEL_PIPELINE_VERSION}:
            raise ValueError("Unsupported job pipeline")
        if "_model_spec" in body:
            raise ValueError("Internal execution settings cannot be supplied as source input")
        if pipeline_version == MODEL_PIPELINE_VERSION:
            spec = ModelJobSpec.model_validate(model_spec)
            spec.config().validate_live_price()
            body = {**body, "_model_spec": spec.model_dump(mode="json")}
            max_attempts = 1
        elif model_spec is not None:
            raise ValueError("Baseline jobs cannot carry model settings")
        if not 1 <= max_attempts <= 5:
            raise ValueError("Invalid attempt limit")
        digest = fingerprint({"input": body, "pipeline_version": pipeline_version})
        identifier, time = str(uuid4()), self.clock()
        try:
            with scoped_transaction(self.store.engine, tenant) as conn:
                conn.execute(
                    insert(jobs).values(
                        id=identifier,
                        tenant=tenant,
                        key=key,
                        fingerprint=digest,
                        actor=actor,
                        pipeline_version=pipeline_version,
                        input=body,
                        status="queued",
                        attempts=0,
                        max_attempts=max_attempts,
                        available_at=time,
                        created_at=time,
                        updated_at=time,
                    )
                )
                self.store._audit(
                    conn,
                    tenant,
                    actor,
                    "job.queued",
                    identifier,
                    {"pipeline_version": pipeline_version},
                )
        except IntegrityError:
            with scoped_transaction(self.store.engine, tenant) as conn:
                row = (
                    conn.execute(select(jobs).where(jobs.c.tenant == tenant, jobs.c.key == key))
                    .mappings()
                    .first()
                )
            if row is None or row["fingerprint"] != digest:
                raise Conflict(
                    "Idempotency key reused with different content or pipeline version"
                ) from None
            identifier = row["id"]
        return self.get(tenant, identifier)

    def get(self, tenant, identifier):
        with scoped_transaction(self.store.engine, tenant) as conn:
            row = (
                conn.execute(select(jobs).where(jobs.c.tenant == tenant, jobs.c.id == identifier))
                .mappings()
                .first()
            )
            if row is None:
                raise NotFound()
            return self._public(row)

    def list(self, tenant):
        with scoped_transaction(self.store.engine, tenant) as conn:
            return [
                self._public(row)
                for row in conn.execute(
                    select(jobs)
                    .where(jobs.c.tenant == tenant)
                    .order_by(jobs.c.created_at.desc(), jobs.c.id)
                    .limit(100)
                ).mappings()
            ]

    @staticmethod
    def _public(row):
        # Credentials/worker lease token and source input never appear in status APIs.
        public = {
            k: row[k]
            for k in (
                "id",
                "status",
                "attempts",
                "max_attempts",
                "available_at",
                "lease_until",
                "created_at",
                "updated_at",
                "result_id",
                "error_code",
                "pipeline_version",
            )
        }
        if row["pipeline_version"] == MODEL_PIPELINE_VERSION:
            raw_spec = row["input"].get("_model_spec")
            public["model_config_sha256"] = (
                ModelJobSpec.model_validate(raw_spec).digest() if raw_spec is not None else None
            )
        for key, value in public.items():
            if isinstance(value, datetime):
                public[key] = (
                    value.replace(tzinfo=UTC) if value.tzinfo is None else value
                ).isoformat()
        return public

    def _eligible(self, time):
        return and_(
            jobs.c.attempts < jobs.c.max_attempts,
            or_(
                and_(jobs.c.status.in_(["queued", "retry_wait"]), jobs.c.available_at <= time),
                and_(jobs.c.status == "running", jobs.c.lease_until <= time),
            ),
        )

    def claim(self, lease_seconds=60, *, pipeline_versions=None):
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        time, token = self.clock(), str(uuid4())
        with self.store.engine.begin() as conn:
            # An exhausted worker crash must not leave a permanently running job.
            exhausted = (
                conn.execute(
                    update(jobs)
                    .where(
                        jobs.c.status == "running",
                        jobs.c.lease_until <= time,
                        jobs.c.attempts >= jobs.c.max_attempts,
                    )
                    .values(
                        status="failed",
                        error_code="attempts_exhausted",
                        lease_token=None,
                        lease_until=None,
                        updated_at=time,
                    )
                    .returning(jobs.c.id, jobs.c.tenant)
                )
                .mappings()
                .all()
            )
            for row in exhausted:
                self.store._audit(
                    conn,
                    row["tenant"],
                    "worker",
                    "job.failed",
                    row["id"],
                    {"error_code": "attempts_exhausted"},
                )
            candidates = (
                conn.execute(
                    select(jobs.c.id)
                    .where(
                        self._eligible(time),
                        *(
                            [jobs.c.pipeline_version.in_(pipeline_versions)]
                            if pipeline_versions is not None
                            else []
                        ),
                    )
                    .order_by(jobs.c.available_at, jobs.c.created_at, jobs.c.id)
                    .limit(20)
                )
                .scalars()
                .all()
            )
            for identifier in candidates:
                row = (
                    conn.execute(
                        update(jobs)
                        .where(jobs.c.id == identifier, self._eligible(time))
                        .values(
                            status="running",
                            attempts=jobs.c.attempts + 1,
                            lease_token=token,
                            lease_until=time + timedelta(seconds=lease_seconds),
                            updated_at=time,
                            error_code=None,
                        )
                        .returning(jobs)
                    )
                    .mappings()
                    .first()
                )
                if row:
                    self.store._audit(
                        conn,
                        row["tenant"],
                        "worker",
                        "job.claimed",
                        identifier,
                        {"attempt": row["attempts"]},
                    )
                    return Claim(
                        identifier,
                        row["tenant"],
                        row["actor"],
                        token,
                        row["attempts"],
                        row["pipeline_version"],
                        row["input"],
                    )
        return None

    def _owned(self, claim, time):
        return and_(
            jobs.c.id == claim.id,
            jobs.c.tenant == claim.tenant,
            jobs.c.status == "running",
            jobs.c.lease_token == claim.token,
            jobs.c.lease_until > time,
        )

    def heartbeat(self, claim, lease_seconds=60):
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        time = self.clock()
        with self.store.engine.begin() as conn:
            changed = conn.execute(
                update(jobs)
                .where(self._owned(claim, time))
                .values(lease_until=time + timedelta(seconds=lease_seconds), updated_at=time)
            ).rowcount
            if changed != 1:
                raise LostLease()

    def complete(self, claim, payload):
        time, result_id = self.clock(), str(uuid4())
        with self.store.engine.begin() as conn:
            # Take the write lock via fencing before creating any result rows.
            row = (
                conn.execute(
                    update(jobs)
                    .where(self._owned(claim, time))
                    .values(
                        status="succeeded",
                        result_id=result_id,
                        lease_token=None,
                        lease_until=None,
                        updated_at=time,
                        error_code=None,
                    )
                    .returning(
                        jobs.c.fingerprint, jobs.c.input, jobs.c.actor, jobs.c.pipeline_version
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LostLease()
            if row["pipeline_version"] == PIPELINE_VERSION:
                payload = validate_publication(row["input"], payload)
            elif row["pipeline_version"] == MODEL_PIPELINE_VERSION:
                payload = validate_model_snapshot(row["input"], payload)
            else:
                raise ValueError("Stored job pipeline version differs from worker version")
            self.store.persist_snapshot(
                conn,
                result_id,
                claim.tenant,
                "job:" + claim.id,
                row["fingerprint"],
                payload,
                row["actor"],
            )
            self.store._audit(
                conn, claim.tenant, "worker", "job.succeeded", claim.id, {"result_id": result_id}
            )
        return result_id

    def fail(self, claim, error_code, retryable):
        if error_code not in {
            "upstream_unavailable",
            "invalid_output",
            "execution_error",
            "pipeline_version_unavailable",
            "resource_budget_exceeded",
        }:
            raise ValueError("Unknown public error code")
        time = self.clock()
        with self.store.engine.begin() as conn:
            row = conn.execute(select(jobs.c.max_attempts).where(self._owned(claim, time))).first()
            if row is None:
                raise LostLease()
            retry = retryable and claim.attempts < row.max_attempts
            status = "retry_wait" if retry else "failed"
            delay = min(60, 2**claim.attempts) if retry else 0
            changed = conn.execute(
                update(jobs)
                .where(self._owned(claim, time))
                .values(
                    status=status,
                    available_at=time + timedelta(seconds=delay),
                    updated_at=time,
                    lease_token=None,
                    lease_until=None,
                    error_code=error_code,
                )
            ).rowcount
            if changed != 1:
                raise LostLease()
            self.store._audit(
                conn,
                claim.tenant,
                "worker",
                "job." + status,
                claim.id,
                {"attempt": claim.attempts, "error_code": error_code},
            )

    def cancel(self, tenant, actor, identifier):
        time = self.clock()
        with scoped_transaction(self.store.engine, tenant) as conn:
            row = conn.execute(
                select(jobs.c.status).where(jobs.c.tenant == tenant, jobs.c.id == identifier)
            ).first()
            if row is None:
                raise NotFound()
            if row.status != "cancelled":
                changed = conn.execute(
                    update(jobs)
                    .where(
                        jobs.c.tenant == tenant,
                        jobs.c.id == identifier,
                        jobs.c.status.not_in(TERMINAL),
                    )
                    .values(
                        status="cancelled",
                        updated_at=time,
                        lease_token=None,
                        lease_until=None,
                        error_code=None,
                    )
                ).rowcount
                if changed != 1:
                    raise Conflict("Completed jobs cannot be cancelled")
                self.store._audit(conn, tenant, actor, "job.cancelled", identifier, {})
        return self.get(tenant, identifier)

    def events(self, tenant, identifier):
        self.get(tenant, identifier)
        from .store import audit

        with scoped_transaction(self.store.engine, tenant) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    select(audit)
                    .where(audit.c.tenant == tenant, audit.c.resource == identifier)
                    .order_by(audit.c.time)
                ).mappings()
            ]
