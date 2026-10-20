"""Server-owned grants with compare-and-swap changes and transactional audit.

Only a trusted operator with database access can grant/revoke membership. There is
no public self-enrollment route, and signed token profile claims are never used.
"""

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import Field
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from atlas.db_scope import scoped_transaction
from atlas.domain import StrictModel
from atlas.migration_scripts.versions.r0004_memberships import add_schema
from atlas.store import Conflict, Store, audit, now

from .tokens import VerifiedSubject

metadata = add_schema()
memberships = metadata.tables["memberships"]


class MembershipChange(StrictModel):
    issuer: str = Field(min_length=1, max_length=2048)
    subject: str = Field(min_length=1, max_length=256)
    tenant: str = Field(min_length=1, max_length=128)
    role: str = Field(pattern=r"^(viewer|analyst|reviewer|admin)$")
    active: bool = Field(strict=True)
    expected_version: int = Field(ge=0, strict=True)


class MembershipRegistry:
    def __init__(self, store):
        self.engine = store.engine

    def resolve(self, subject: VerifiedSubject, tenant: str | None):
        # Deliberately queried on every authenticated request: revocation is not cached.
        condition = (
            (memberships.c.issuer == subject.issuer)
            & (memberships.c.subject == subject.subject)
            & memberships.c.active.is_(True)
        )
        if tenant is not None:
            condition &= memberships.c.tenant == tenant
        with scoped_transaction(
            self.engine, issuer=subject.issuer, subject=subject.subject
        ) as connection:
            rows = (
                connection.execute(select(memberships).where(condition).limit(2)).mappings().all()
            )
        if len(rows) != 1:
            return None
        return {"tenant": rows[0]["tenant"], "actor": subject.subject, "role": rows[0]["role"]}

    def change(self, change: MembershipChange):
        values = change.model_dump(exclude={"expected_version"})
        version = change.expected_version + 1
        condition = (
            (memberships.c.issuer == change.issuer)
            & (memberships.c.subject == change.subject)
            & (memberships.c.tenant == change.tenant)
        )
        try:
            with self.engine.begin() as connection:
                if change.expected_version == 0:
                    connection.execute(insert(memberships).values(**values, version=version))
                else:
                    result = connection.execute(
                        update(memberships)
                        .where(condition, memberships.c.version == change.expected_version)
                        .values(role=change.role, active=change.active, version=version)
                    )
                    if result.rowcount != 1:
                        raise Conflict("Membership version changed or entry does not exist")
                connection.execute(
                    insert(audit).values(
                        id=str(uuid4()),
                        tenant=change.tenant,
                        actor="trusted-local-operator",
                        action="membership.changed",
                        resource=change.subject,
                        time=now(),
                        details={
                            "issuer": change.issuer,
                            "role": change.role,
                            "active": change.active,
                            "version": version,
                        },
                    )
                )
        except IntegrityError:
            raise Conflict("Membership already exists or change is invalid") from None
        return version


def main():
    parser = argparse.ArgumentParser(
        description="Apply a trusted membership change from a private JSON file"
    )
    parser.add_argument("change_file")
    args = parser.parse_args()
    path = Path(args.change_file)
    if path.stat().st_mode & 0o077 or path.stat().st_size > 16384:
        raise SystemExit("Change file must be private (mode 600) and at most 16 KiB")
    change = MembershipChange.model_validate_json(path.read_text())
    store = Store(os.getenv("ATLAS_DATABASE_URL", "sqlite:///var/atlas.db"))
    try:
        version = MembershipRegistry(store).change(change)
        print(json.dumps({"membership_version": version, "active": change.active}))
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
