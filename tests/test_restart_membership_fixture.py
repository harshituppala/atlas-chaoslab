"""Restart fixtures preserve server-owned grants and cannot silently revive revocations."""

import importlib.util
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from atlas.security.memberships import MembershipChange, MembershipRegistry, memberships
from atlas.store import Store

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture = load("login_browser_fixture")


@pytest.fixture
def prepared(tmp_path):
    # Reuse only certificate generation; no listener, provider or worker is started.
    import sys
    from unittest.mock import patch

    with patch.dict(sys.modules, {"login_browser_fixture": fixture}):
        # The runner also imports its sibling PG/supervisor modules at import time.
        with patch.dict(
            sys.modules,
            {
                "login_postgres_fixture": load("login_postgres_fixture"),
                "run_managed_workbench": load("run_managed_workbench"),
            },
        ):
            cert, key, _ = load("verify_browser_login_https").certificate(tmp_path)
    owner = Store("sqlite:///" + str(tmp_path / "atlas.db"))
    operator = MembershipRegistry(owner)

    def make(**kwargs):
        return fixture.create_fixture(
            tmp_path,
            "http://127.0.0.1:1",
            cert,
            rsa.generate_private_key(public_exponent=65537, key_size=2048),
            membership_operator=operator,
            **kwargs,
        )

    yield owner, operator, make
    owner.engine.dispose()
    key.unlink(missing_ok=True)


def current(owner):
    with owner.engine.connect() as connection:
        return tuple(connection.execute(select(memberships.c.version, memberships.c.active)).one())


def test_restart_does_not_regrant_or_increment_membership(prepared):
    owner, _, make = prepared
    _, _, close = make()
    close()
    assert current(owner) == (1, True)
    _, _, close = make(reuse_membership=True)
    close()
    assert current(owner) == (1, True)


def test_restart_refuses_revoked_membership(prepared):
    owner, operator, make = prepared
    _, _, close = make()
    close()
    operator.change(
        MembershipChange(
            issuer=fixture.PROVIDER,
            subject="synthetic-reviewer",
            tenant="fictional-team",
            role="reviewer",
            active=False,
            expected_version=1,
        )
    )
    with pytest.raises(ValueError, match="must not restore revoked"):
        make(reuse_membership=True)
    assert current(owner) == (2, False)


def test_restart_requires_operator_before_creating_settings(tmp_path):
    with pytest.raises(ValueError, match="separate membership operator"):
        fixture.create_fixture(tmp_path, None, None, None, reuse_membership=True)
    assert not (tmp_path / "managed-login.json").exists()
