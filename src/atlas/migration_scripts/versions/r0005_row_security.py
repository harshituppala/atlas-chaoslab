"""Forced row policies supplement application filters; runtime roles must not bypass."""

from alembic import op
from sqlalchemy import text

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "runs",
    "reviews",
    "audit",
    "jobs",
    "documents",
    "document_quotas",
    "retrieval_corpora",
    "retrieval_chunks",
)


def expression(table):
    if table == "memberships":
        return "issuer = NULLIF(current_setting('atlas.issuer', true), '') AND subject = NULLIF(current_setting('atlas.subject', true), '')"
    return "tenant = NULLIF(current_setting('atlas.tenant', true), '')"


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return
    for table in (*TENANT_TABLES, "memberships"):
        connection.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        connection.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        predicate = expression(table)
        connection.execute(
            text(
                f'CREATE POLICY atlas_identity ON "{table}" USING ({predicate}) WITH CHECK ({predicate})'
            )
        )


def downgrade():
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return
    for table in (*TENANT_TABLES, "memberships"):
        connection.execute(text(f'DROP POLICY atlas_identity ON "{table}"'))
        connection.execute(text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
        connection.execute(text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
