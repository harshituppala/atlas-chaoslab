"""Persist source snapshots and bounded exact-search vectors, tenant scoped."""

from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, ForeignKeyConstraint, Integer, MetaData, String, Table, text

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def add_schema(metadata=None):
    metadata = metadata if metadata is not None else MetaData()
    Table(
        "retrieval_corpora",
        metadata,
        Column("tenant", String(128), primary_key=True),
        Column("id", String(64), primary_key=True),
        Column("recipe_sha256", String(64), nullable=False),
        Column("documents", JSON, nullable=False),
        Column("chunk_count", Integer, nullable=False),
    )
    Table(
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
    return metadata


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"))
    add_schema().create_all(connection, checkfirst=False)


def downgrade():
    if op.get_bind().execute(text("SELECT count(*) FROM retrieval_corpora")).scalar_one():
        raise RuntimeError(
            "Retrieval cache contains data; an explicit preservation/deletion decision is required"
        )
    op.drop_table("retrieval_chunks")
    op.drop_table("retrieval_corpora")
    # Never remove a shared vector extension during a table migration.
