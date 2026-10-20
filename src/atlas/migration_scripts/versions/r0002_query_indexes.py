"""Index the existing tenant-scoped history and audit access patterns."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_runs_tenant_created", "runs", ["tenant", "created"]),
    ("ix_audit_tenant_resource_time", "audit", ["tenant", "resource", "time"]),
    ("ix_jobs_tenant_created", "jobs", ["tenant", "created_at"]),
    ("ix_documents_tenant_created", "documents", ["tenant", "created"]),
]


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
