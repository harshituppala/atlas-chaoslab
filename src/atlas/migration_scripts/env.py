"""Programmatic migrations share the caller's transaction and private connection."""

from alembic import context

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Use the ATLAS migration runner; no connection URL is logged or embedded")
context.configure(connection=connection)
with context.begin_transaction():
    context.run_migrations()
