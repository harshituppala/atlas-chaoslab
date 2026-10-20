"""Freeze the existing six-table prototype schema; never import mutable app models."""

from alembic import op
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def schema():
    metadata = MetaData()
    Table(
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
    Table(
        "reviews",
        metadata,
        Column("run_id", String, primary_key=True),
        Column("requirement_id", String, primary_key=True),
        Column("tenant", String, nullable=False),
        Column("version", Integer, nullable=False),
        Column("decision", String, nullable=False),
        Column("note", Text, nullable=False),
    )
    Table(
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
    Table(
        "documents",
        metadata,
        Column("tenant", String, primary_key=True),
        Column("id", String, primary_key=True),
        Column("created", String, nullable=False),
        Column("document", JSON, nullable=False),
        Column("original", LargeBinary, nullable=False),
    )
    Table(
        "document_quotas",
        metadata,
        Column("tenant", String, primary_key=True),
        Column("bytes", Integer, nullable=False),
        Column("count", Integer, nullable=False),
    )
    return metadata


def upgrade():
    schema().create_all(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError(
        "Baseline downgrade would delete user data; use a verified backup restore instead"
    )
