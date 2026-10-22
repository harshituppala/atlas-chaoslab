"""Operator entry-point admission, client ownership and controlled signed login."""

import json
from dataclasses import asdict
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from test_cognito_tokens import TRUST, signed
from test_login_exchange import CONFIG

from atlas import managed
from atlas.security.memberships import MembershipChange


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in (*managed.CONFLICTING_SETTINGS, "ATLAS_LOGIN_SETTINGS", "ATLAS_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)


def settings_file(tmp_path, raw=None):
    path = tmp_path / "login.json"
    path.write_text(raw if raw is not None else json.dumps(asdict(CONFIG)))
    path.chmod(0o600)
    return path


def test_private_settings_and_explicit_environment_factory(tmp_path, monkeypatch):
    path = settings_file(tmp_path)
    assert managed.read_settings(path) == CONFIG
    monkeypatch.setenv("ATLAS_LOGIN_SETTINGS", str(path))
    monkeypatch.setenv("ATLAS_DATABASE_URL", "sqlite://")
    with TestClient(
        managed.create_from_environment(), base_url="https://atlas.example.invalid"
    ) as client:
        assert client.get("/auth/config").status_code == 200
        assert (
            client.get("/api/me", headers={"Authorization": "Bearer local-demo"}).status_code == 401
        )


@pytest.mark.parametrize("kind", ["public", "oversize", "link", "directory", "missing"])
def test_settings_file_rejects_unbounded_or_unsafe_input(tmp_path, kind):
    path = settings_file(tmp_path)
    if kind == "public":
        path.chmod(0o644)
    elif kind == "oversize":
        path.write_bytes(b" " * (managed.MAX_SETTINGS_BYTES + 1))
    elif kind == "link":
        link = tmp_path / "link.json"
        link.symlink_to(path)
        path = link
    elif kind == "directory":
        path = tmp_path
    else:
        path.unlink()
    with pytest.raises(ValueError, match="private, bounded, valid JSON"):
        managed.read_settings(path)


@pytest.mark.parametrize(
    "raw",
    [
        "null",
        "[]",
        '{"trust":1,"trust":2}',
        "[" * 1100,
        json.dumps({**asdict(CONFIG), "client_secret": "PRIVATE-MARKER"}),
        json.dumps({**asdict(CONFIG), "trust": {**asdict(TRUST), "issuer": None}}),
        json.dumps({**asdict(CONFIG), "trust": {**asdict(TRUST), "profile": "rfc9068"}}),
        json.dumps(
            {**asdict(CONFIG), "trust": {**asdict(TRUST), "jwks_url": "https://other.invalid/keys"}}
        ),
        json.dumps({**asdict(CONFIG), "redirect_uri": "http://localhost/auth/callback"}),
    ],
)
def test_settings_rejection_does_not_echo_supplied_values(tmp_path, raw):
    with pytest.raises(ValueError) as failure:
        managed.read_settings(settings_file(tmp_path, raw))
    assert str(failure.value) == "Managed settings must be a private, bounded, valid JSON file"


@pytest.mark.parametrize("name", managed.CONFLICTING_SETTINGS)
def test_conflicting_modes_fail_before_opening_clients(monkeypatch, name):
    monkeypatch.setenv(name, "PRIVATE-MARKER")
    with pytest.raises(ValueError, match="conflicting"):
        managed.create_managed_app(CONFIG, "sqlite://")


@pytest.mark.parametrize("present", [None, "ATLAS_LOGIN_SETTINGS", "ATLAS_DATABASE_URL"])
def test_factory_requires_both_settings_and_database(monkeypatch, present):
    if present:
        monkeypatch.setenv(present, "PRIVATE-MARKER")
    with pytest.raises(ValueError, match="explicitly"):
        managed.create_from_environment()


class TrackedTransport(httpx.MockTransport):
    def __init__(self, handler):
        super().__init__(handler)
        self.closed = False

    def close(self):
        self.closed = True
        super().close()


def test_factory_closes_clients_when_application_construction_fails(monkeypatch):
    keys = TrackedTransport(lambda _: httpx.Response(500))
    tokens = TrackedTransport(lambda _: httpx.Response(500))

    def failure(*args, **kwargs):
        raise RuntimeError("controlled construction failure")

    monkeypatch.setattr(managed, "create_app", failure)
    with pytest.raises(RuntimeError, match="controlled construction failure"):
        managed.create_managed_app(CONFIG, "sqlite://", key_transport=keys, token_transport=tokens)
    assert keys.closed and tokens.closed


def test_controlled_signed_login_requires_separate_membership_and_closes_clients():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = {
        **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
        "kid": "access-key",
    }
    calls = []

    def keys(request):
        assert str(request.url) == TRUST.jwks_url
        calls.append("keys")
        return httpx.Response(200, json={"keys": [public]})

    def tokens(request):
        assert str(request.url) == CONFIG.provider_origin + "/oauth2/token"
        form = parse_qs(request.content.decode())
        assert form["client_id"] == [TRUST.client_id] and "code_verifier" in form
        calls.append("token")
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                json.dumps(
                    {"access_token": signed(key), "expires_in": 300, "token_type": "Bearer"}
                ).encode()
            ),
        )

    key_transport, token_transport = TrackedTransport(keys), TrackedTransport(tokens)
    app = managed.create_managed_app(
        CONFIG, "sqlite://", key_transport=key_transport, token_transport=token_transport
    )
    with TestClient(
        app, base_url="https://atlas.example.invalid", follow_redirects=False
    ) as client:
        start = client.post("/auth/start", headers={"Origin": "https://atlas.example.invalid"})
        state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
        callback = client.get("/auth/callback", params={"state": state, "code": "synthetic-code"})
        assert callback.status_code == 303 and callback.headers["location"] == "/"
        assert client.get("/auth/session").status_code == 200
        assert client.get("/api/me").status_code == 403
        app.state.memberships.change(
            MembershipChange(
                issuer=TRUST.issuer,
                subject="synthetic-alice",
                tenant="sample",
                role="reviewer",
                active=True,
                expected_version=0,
            )
        )
        assert client.get("/api/me").json()["role"] == "reviewer"
        assert not key_transport.closed and not token_transport.closed
    assert calls == ["token", "keys"]
    assert key_transport.closed and token_transport.closed
