"""Transaction-local trusted identity context; never derived from request body fields."""

from contextlib import contextmanager

from sqlalchemy import text


def _bounded(value, maximum):
    if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= maximum):
        raise ValueError("Invalid trusted database identity")
    return value or ""


@contextmanager
def scoped_transaction(engine, tenant=None, *, issuer=None, subject=None):
    values = {
        "tenant": _bounded(tenant, 128),
        "issuer": _bounded(issuer, 2048),
        "subject": _bounded(subject, 256),
    }
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            for name, value in values.items():
                connection.execute(
                    text("SELECT set_config(:name, :value, true)"),
                    {"name": "atlas." + name, "value": value},
                )
        yield connection


class UnsafeDatabaseRole(Exception):
    pass


def check_runtime_role(engine, purpose):
    if purpose not in {"internal", "api", "worker"}:
        raise ValueError("Unknown database runtime purpose")
    if engine.dialect.name != "postgresql" or purpose == "internal":
        return
    with engine.connect() as connection:
        row = (
            connection.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
            .mappings()
            .one()
        )
        owns_tables = connection.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=current_schema() AND c.relkind='r' AND c.relowner="
                "(SELECT oid FROM pg_roles WHERE rolname=current_user))"
            )
        ).scalar_one()
        creates = connection.execute(
            text("SELECT has_schema_privilege(current_user, current_schema(), 'CREATE')")
        ).scalar_one()
        elevated_membership = connection.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_roles r WHERE r.rolname <> current_user "
                "AND pg_has_role(current_user, r.oid, 'MEMBER') AND (r.rolsuper OR r.rolbypassrls "
                "OR has_schema_privilege(r.oid, current_schema(), 'CREATE') "
                "OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=current_schema() AND c.relowner=r.oid)))"
            )
        ).scalar_one()
    if (
        row["rolsuper"]
        or owns_tables
        or creates
        or elevated_membership
        or (purpose == "api" and row["rolbypassrls"])
    ):
        raise UnsafeDatabaseRole("Runtime database role is overprivileged")
    if purpose == "worker" and not row["rolbypassrls"]:
        raise UnsafeDatabaseRole("Worker requires its dedicated cross-tenant database role")
