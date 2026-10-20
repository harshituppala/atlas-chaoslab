"""Managed API trust boundary with real signed tokens, SQLite and controlled JWKS."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import jwt
import pytest
from alembic import command
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from atlas.api import create_app
from atlas.migrations import HEAD, config, revision
from atlas.security.memberships import MembershipChange, MembershipRegistry, memberships
from atlas.security.tokens import AccessTokenVerifier, TokenTrust
from atlas.store import Conflict, Store, audit

TRUST = TokenTrust(
    "https://identity.example.test", "atlas-resource", "https://keys.example.test/jwks"
)


def change(tenant="a", role="reviewer", active=True, version=0):
    return MembershipChange(
        issuer=TRUST.issuer,
        subject="alice",
        tenant=tenant,
        role=role,
        active=active,
        expected_version=version,
    )


@pytest.fixture
def managed(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), "kid": "one"}
    verifier = AccessTokenVerifier(
        TRUST, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [jwk]}))
    )
    app = create_app(
        "sqlite:///" + str(tmp_path / "managed.db"),
        {"dev-token": {"tenant": "a", "actor": "dev", "role": "admin"}},
        verifier,
    )
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": TRUST.issuer,
            "aud": TRUST.audience,
            "sub": "alice",
            "iat": now,
            "exp": now + 600,
            "role": "admin",
            "tenant": "forged",
        },
        key,
        algorithm="RS256",
        headers={"typ": "at+jwt", "kid": "one"},
    )
    with TestClient(app) as client:
        yield app, client, {"Authorization": "Bearer " + token}
    verifier.close()


def test_api_requires_membership_ignores_forged_claims_and_disables_dev_fallback(managed):
    app, client, headers = managed
    assert client.get("/api/me", headers=headers).status_code == 403
    assert client.get("/api/me", headers={"Authorization": "Bearer dev-token"}).status_code == 401
    app.state.memberships.change(change(role="viewer"))
    response = client.get("/api/me", headers=headers)
    assert response.json() == {
        "tenant": "a",
        "actor": "alice",
        "role": "viewer",
        "authentication": "managed-access-token",
    }
    demo = json.loads(Path("datasets/demo.json").read_text())
    assert (
        client.post(
            "/api/jobs", headers={**headers, "Idempotency-Key": "managed-test-01"}, json=demo
        ).status_code
        == 403
    )
    assert client.get("/api/me", headers={**headers, "X-Workspace-ID": "forged"}).status_code == 403


def test_workspace_selection_and_immediate_revocation(managed):
    app, client, headers = managed
    registry = app.state.memberships
    registry.change(change())
    registry.change(change(tenant="b", role="analyst"))
    assert client.get("/api/me", headers=headers).status_code == 403
    assert (
        client.get("/api/me", headers={**headers, "X-Workspace-ID": "b"}).json()["role"]
        == "analyst"
    )
    registry.change(change(tenant="b", role="analyst", active=False, version=1))
    assert client.get("/api/me", headers={**headers, "X-Workspace-ID": "b"}).status_code == 403
    assert client.get("/api/me", headers=headers).json()["tenant"] == "a"
    registry.change(change(active=False, version=1))
    assert client.get("/api/me", headers=headers).status_code == 403


def test_membership_cas_and_audit_survive_restart(tmp_path):
    url = "sqlite:///" + str(tmp_path / "registry.db")
    store = Store(url)
    registry = MembershipRegistry(store)
    assert registry.change(change()) == 1
    with pytest.raises(Conflict):
        registry.change(change())
    assert registry.change(change(role="viewer", version=1)) == 2
    with pytest.raises(Conflict):
        registry.change(change(active=False, version=1))
    store.engine.dispose()
    reopened = Store(url)
    with reopened.engine.connect() as connection:
        assert connection.execute(select(memberships.c.version)).scalar_one() == 2
        rows = connection.execute(select(audit)).mappings().all()
        assert len(rows) == 2 and {row["action"] for row in rows} == {"membership.changed"}
    reopened.engine.dispose()


def test_audit_failure_rolls_back_permission_change(tmp_path):
    store = Store("sqlite:///" + str(tmp_path / "registry.db"))
    registry = MembershipRegistry(store)
    registry.change(change())

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit"):
            raise RuntimeError("Injected audit failure")

    event.listen(store.engine, "before_cursor_execute", fail)
    with pytest.raises(RuntimeError, match="Injected"):
        registry.change(change(role="admin", version=1))
    event.remove(store.engine, "before_cursor_execute", fail)
    with store.engine.connect() as connection:
        row = connection.execute(select(memberships)).mappings().one()
        assert row["role"] == "reviewer" and row["version"] == 1
    store.engine.dispose()


def test_concurrent_permission_changes_have_one_winner(tmp_path):
    store = Store("sqlite:///" + str(tmp_path / "registry.db"))
    registry = MembershipRegistry(store)
    registry.change(change())

    def attempt(number):
        try:
            registry.change(change(role="viewer" if number % 2 else "admin", version=1))
            return True
        except Conflict:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(16))) == 1
    with store.engine.connect() as connection:
        assert len(connection.execute(select(audit)).all()) == 2
    store.engine.dispose()


def test_membership_downgrade_preserves_registry(tmp_path):
    store = Store("sqlite:///" + str(tmp_path / "registry.db"))
    MembershipRegistry(store).change(change())
    with pytest.raises(RuntimeError, match="contains data"):
        with store.engine.begin() as connection:
            command.downgrade(config(connection), "0003")
    with store.engine.connect() as connection:
        assert revision(connection) == HEAD
        assert connection.execute(select(memberships.c.subject)).scalar_one() == "alice"
    store.engine.dispose()


def test_key_service_failure_is_unavailability_without_local_fallback(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = AccessTokenVerifier(
        TRUST, transport=httpx.MockTransport(lambda _: httpx.Response(503))
    )
    app = create_app("sqlite:///" + str(tmp_path / "managed.db"), {}, verifier)
    now = int(time.time())
    value = jwt.encode(
        {"iss": TRUST.issuer, "aud": TRUST.audience, "sub": "alice", "iat": now, "exp": now + 600},
        key,
        algorithm="RS256",
        headers={"typ": "at+jwt", "kid": "one"},
    )
    try:
        with TestClient(app) as client:
            result = client.get("/api/me", headers={"Authorization": "Bearer " + value})
            assert result.status_code == 503 and result.headers["retry-after"] == "10"
            assert value not in result.text
    finally:
        verifier.close()
