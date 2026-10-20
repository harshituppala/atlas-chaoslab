"""Tenant-owned immutable uploads, atomically admitted against storage quotas."""

from sqlalchemy import (
    JSON,
    Column,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from .db_scope import scoped_transaction
from .domain import Document, ResourceBudgetExceeded
from .store import Conflict, NotFound, now

metadata = MetaData()
uploads = Table(
    "documents",
    metadata,
    Column("tenant", String, primary_key=True),
    Column("id", String, primary_key=True),
    Column("created", String, nullable=False),
    Column("document", JSON, nullable=False),
    Column("original", LargeBinary, nullable=False),
)
quotas = Table(
    "document_quotas",
    metadata,
    Column("tenant", String, primary_key=True),
    Column("bytes", Integer, nullable=False),
    Column("count", Integer, nullable=False),
)
Index("ix_documents_tenant_created", uploads.c.tenant, uploads.c.created)


class DocumentStore:
    def __init__(self, store, maximum_bytes=20_000_000, maximum_count=200):
        self.store, self.engine = store, store.engine
        self.maximum_bytes, self.maximum_count = maximum_bytes, maximum_count

    def get(self, tenant, identifier):
        with scoped_transaction(self.engine, tenant) as connection:
            row = connection.execute(
                select(uploads.c.document).where(
                    uploads.c.tenant == tenant, uploads.c.id == identifier
                )
            ).first()
        if row is None:
            raise NotFound()
        return Document.model_validate(row.document)

    def original(self, tenant, identifier):
        with scoped_transaction(self.engine, tenant) as connection:
            row = (
                connection.execute(
                    select(uploads).where(uploads.c.tenant == tenant, uploads.c.id == identifier)
                )
                .mappings()
                .first()
            )
        if row is None:
            raise NotFound()
        return row["original"], Document.model_validate(row["document"])

    def list(self, tenant):
        with scoped_transaction(self.engine, tenant) as connection:
            rows = connection.execute(
                select(uploads.c.id, uploads.c.created, uploads.c.document)
                .where(uploads.c.tenant == tenant)
                .order_by(uploads.c.created.desc())
                .limit(200)
            ).mappings()
            return [
                {
                    "id": row["id"],
                    "created": row["created"],
                    "title": row["document"]["title"],
                    "kind": row["document"]["kind"],
                    "format": row["document"]["source_map"]["format"],
                }
                for row in rows
            ]

    def save(self, tenant, actor, document, original):
        try:
            return self.get(tenant, document.id)
        except NotFound:
            pass
        # Creating an empty quota row is harmless if parsing/publication is interrupted.
        try:
            with scoped_transaction(self.engine, tenant) as connection:
                connection.execute(insert(quotas).values(tenant=tenant, bytes=0, count=0))
        except IntegrityError:
            pass
        try:
            with scoped_transaction(self.engine, tenant) as connection:
                admitted = connection.execute(
                    update(quotas)
                    .where(
                        quotas.c.tenant == tenant,
                        quotas.c.bytes <= self.maximum_bytes - len(original),
                        quotas.c.count < self.maximum_count,
                    )
                    .values(bytes=quotas.c.bytes + len(original), count=quotas.c.count + 1)
                ).rowcount
                if admitted != 1:
                    # A concurrent identical upload may have consumed the final quota.
                    existing = connection.execute(
                        select(uploads.c.document).where(
                            uploads.c.tenant == tenant, uploads.c.id == document.id
                        )
                    ).first()
                    if existing:
                        return Document.model_validate(existing.document)
                    raise ResourceBudgetExceeded("Workspace document storage budget exceeded")
                connection.execute(
                    insert(uploads).values(
                        tenant=tenant,
                        id=document.id,
                        created=now(),
                        document=document.model_dump(),
                        original=original,
                    )
                )
                self.store._audit(
                    connection,
                    tenant,
                    actor,
                    "document.ingested",
                    document.id,
                    {
                        "raw_sha256": document.source_map.raw_sha256,
                        "parser_version": document.source_map.parser_version,
                        "bytes": len(original),
                    },
                )
        except IntegrityError:
            # Entire transaction, including quota increments/audit, rolls back for a duplicate.
            return self.get(tenant, document.id)
        return document

    def verify(self, tenant, document):
        if document.source_map is not None or document.id.startswith("upload-"):
            persisted = self.get(tenant, document.id)
            if persisted != document:
                raise Conflict("Uploaded document changed; reload its immutable source")
