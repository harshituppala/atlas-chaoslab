"""Server-owned workspace memberships; no permissions inferred from token claims."""

from alembic import op
from sqlalchemy import Boolean, CheckConstraint, Column, Integer, MetaData, String, Table, text

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def add_schema(metadata=None):
    metadata = metadata if metadata is not None else MetaData()
    Table(
        "memberships",
        metadata,
        Column("issuer", String(2048), primary_key=True),
        Column("subject", String(256), primary_key=True),
        Column("tenant", String(128), primary_key=True),
        Column("role", String(16), nullable=False),
        Column("active", Boolean, nullable=False),
        Column("version", Integer, nullable=False),
        CheckConstraint(
            "role IN ('viewer', 'analyst', 'reviewer', 'admin')", name="membership_role"
        ),
        CheckConstraint("version >= 1", name="membership_version"),
    )
    return metadata


def upgrade():
    add_schema().create_all(op.get_bind(), checkfirst=False)


def downgrade():
    if op.get_bind().execute(text("SELECT count(*) FROM memberships")).scalar_one():
        raise RuntimeError("Membership registry contains data; downgrade refused")
    op.drop_table("memberships")
