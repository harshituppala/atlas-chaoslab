"""Offline Cognito resource-access profile: real signatures, controlled keys, real API RBAC."""

import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from atlas.api import create_app
from atlas.security.memberships import MembershipChange
from atlas.security.tokens import AccessTokenVerifier, InvalidAccessToken, TokenTrust

TRUST = TokenTrust(
    issuer="https://cognito-idp.ca-central-1.amazonaws.com/ca-central-1_example",
    audience="https://atlas.example.invalid/api",
    jwks_url="https://cognito-idp.ca-central-1.amazonaws.com/ca-central-1_example/.well-known/jwks.json",
    profile="cognito-resource",
    client_id="client123",
    required_scopes=("https://atlas.example.invalid/api/review",),
)


@pytest.fixture(scope="module")
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def signed(key, *, claims=None, missing=(), typ=None):
    now = int(time.time())
    body = {
        "iss": TRUST.issuer,
        "aud": TRUST.audience,
        "sub": "synthetic-alice",
        "iat": now,
        "exp": now + 600,
        "client_id": TRUST.client_id,
        "token_use": "access",
        "scope": "openid https://atlas.example.invalid/api/review",
    }
    body.update(claims or {})
    for name in missing:
        body.pop(name, None)
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": "access-key", "typ": typ})


def verifier(key, trust=TRUST):
    public = {
        **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
        "kid": "access-key",
    }

    def keys(request):
        assert str(request.url) == trust.jwks_url
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"keys": [public]})

    return AccessTokenVerifier(trust, transport=httpx.MockTransport(keys))


@pytest.mark.parametrize("typ", [None, "JWT"])
def test_explicit_cognito_profile_accepts_resource_bound_access_only(key, typ):
    client = verifier(key)
    try:
        assert client.verify(signed(key, typ=typ)).subject == "synthetic-alice"
    finally:
        client.close()


@pytest.mark.parametrize(
    "claims,missing,typ",
    [
        ({"token_use": "id"}, (), None),
        ({}, ("token_use",), None),
        ({"client_id": "other"}, (), None),
        ({}, ("client_id",), None),
        ({}, ("aud",), None),
        ({"aud": "other"}, (), None),
        ({"aud": [TRUST.audience]}, (), None),
        ({"scope": "openid"}, (), None),
        ({"scope": "openid https://atlas.example.invalid/api/reviewx"}, (), None),
        ({"scope": ["https://atlas.example.invalid/api/review"]}, (), None),
        ({"scope": "https://atlas.example.invalid/api/review\nadmin"}, (), None),
        ({"scope": " https://atlas.example.invalid/api/review"}, (), None),
        ({"scope": "https://atlas.example.invalid/api/review  openid"}, (), None),
        ({}, ("scope",), None),
        ({"iss": "https://other.example.invalid"}, (), None),
        ({"exp": 0}, (), None),
        ({"iat": True}, (), None),
        ({}, (), "at+jwt"),
        ({}, (), "id+jwt"),
    ],
)
def test_cognito_profile_rejects_wrong_purpose_client_resource_scope_or_type(
    key, claims, missing, typ
):
    client = verifier(key)
    try:
        with pytest.raises(InvalidAccessToken):
            client.verify(signed(key, claims=claims, missing=missing, typ=typ))
    finally:
        client.close()


def test_default_profile_does_not_implicitly_accept_cognito_headers(key):
    client = verifier(key, TokenTrust(TRUST.issuer, TRUST.audience, TRUST.jwks_url))
    try:
        with pytest.raises(InvalidAccessToken):
            client.verify(signed(key))
    finally:
        client.close()


@pytest.mark.parametrize(
    "update",
    [
        {"profile": "guess-provider"},
        {"profile": []},
        {"client_id": None},
        {"client_id": ""},
        {"required_scopes": ()},
        {"required_scopes": "https://atlas.example.invalid/api/review"},
        {
            "required_scopes": (
                "https://atlas.example.invalid/api/review",
                "https://atlas.example.invalid/api/review",
            )
        },
        {"required_scopes": ("https://atlas.example.invalid/api/review admin",)},
        {"jwks_url": "https://keys.example.invalid/jwks"},
        {"profile": "rfc9068"},
    ],
)
def test_cognito_operator_configuration_is_explicit_and_bounded(update):
    with pytest.raises(ValueError):
        replace(TRUST, **update)


def test_json_scope_list_is_frozen_to_immutable_configuration():
    scopes = ["https://atlas.example.invalid/api/review"]
    trust = replace(TRUST, required_scopes=scopes)
    scopes.append("mutated")
    assert trust.required_scopes == ("https://atlas.example.invalid/api/review",)


def test_cognito_signed_claims_still_require_server_owned_membership_and_observe_revocation(
    key, tmp_path
):
    checker = verifier(key)
    app = create_app(
        "sqlite:///" + str(tmp_path / "cognito.db"),
        {"local-token": {"tenant": "a", "actor": "local", "role": "admin"}},
        checker,
    )
    headers = {
        "Authorization": "Bearer "
        + signed(key, claims={"role": "admin", "tenant": "forged", "cognito:groups": ["admins"]})
    }
    change = MembershipChange(
        issuer=TRUST.issuer,
        subject="synthetic-alice",
        tenant="a",
        role="viewer",
        active=True,
        expected_version=0,
    )
    try:
        with TestClient(app) as client:
            assert client.get("/api/me", headers=headers).status_code == 403
            app.state.memberships.change(change)
            response = client.get("/api/me", headers=headers)
            assert response.json() == {
                "tenant": "a",
                "actor": "synthetic-alice",
                "role": "viewer",
                "authentication": "managed-access-token",
            }
            assert (
                client.get("/api/me", headers={"Authorization": "Bearer local-token"}).status_code
                == 401
            )
            body = json.loads(Path("datasets/demo.json").read_text())
            assert (
                client.post(
                    "/api/jobs",
                    headers={**headers, "Idempotency-Key": "cognito-test-001"},
                    json=body,
                ).status_code
                == 403
            )
            app.state.memberships.change(
                change.model_copy(update={"active": False, "expected_version": 1})
            )
            assert client.get("/api/me", headers=headers).status_code == 403
    finally:
        checker.close()


def test_cognito_profile_rejects_a_signature_from_an_untrusted_key(key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = verifier(key)
    try:
        with pytest.raises(InvalidAccessToken):
            client.verify(signed(other))
    finally:
        client.close()


def test_api_loads_explicit_cognito_profile_from_operator_json(key, monkeypatch):
    monkeypatch.setenv("ATLAS_TOKEN_TRUST", json.dumps(asdict(TRUST)))
    checker = verifier(key)

    def construct(trust):
        assert trust == TRUST
        return checker

    monkeypatch.setattr("atlas.api.AccessTokenVerifier", construct)
    app = create_app("sqlite://", {})
    app.state.memberships.change(
        MembershipChange(
            issuer=TRUST.issuer,
            subject="synthetic-alice",
            tenant="a",
            role="reviewer",
            active=True,
            expected_version=0,
        )
    )
    with TestClient(app) as client:
        response = client.get("/api/me", headers={"Authorization": "Bearer " + signed(key)})
        assert response.status_code == 200 and response.json()["role"] == "reviewer"
