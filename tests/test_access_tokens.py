"""Real RSA signatures and a controlled JWKS transport; no network/identity account."""

import json
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from atlas.security.tokens import (
    AccessTokenVerifier,
    InvalidAccessToken,
    KeyServiceUnavailable,
    TokenTrust,
)

TRUST = TokenTrust(
    "https://identity.example.test", "atlas-resource", "https://keys.example.test/jwks"
)


@pytest.fixture(scope="module")
def signing_keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


def public(key, kid="key-one"):
    value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {**value, "kid": kid, "use": "sig", "alg": "RS256"}


def token(key, *, claims=None, header=None):
    now = int(time.time())
    body = {
        "iss": TRUST.issuer,
        "aud": TRUST.audience,
        "sub": "alice",
        "iat": now,
        "exp": now + 600,
    }
    body.update(claims or {})
    return jwt.encode(
        body, key, algorithm="RS256", headers={"typ": "at+jwt", "kid": "key-one", **(header or {})}
    )


@pytest.fixture
def rig(signing_keys):
    state = {"keys": [public(signing_keys[0])], "requests": [], "clock": 1.0, "status": 200}

    def handle(request):
        state["requests"].append(request)
        assert str(request.url) == TRUST.jwks_url
        assert "authorization" not in request.headers
        return httpx.Response(state["status"], json={"keys": state["keys"]})

    verifier = AccessTokenVerifier(
        TRUST, transport=httpx.MockTransport(handle), monotonic=lambda: state["clock"]
    )
    yield verifier, state
    verifier.close()


def test_real_signature_and_claims_do_not_authorize_roles(rig, signing_keys):
    verifier, state = rig
    result = verifier.verify(token(signing_keys[0], claims={"role": "admin", "tenant": "other"}))
    assert result.subject == "alice" and result.issuer == TRUST.issuer
    assert not hasattr(result, "role") and not hasattr(result, "tenant")
    verifier.verify(token(signing_keys[0]))
    assert len(state["requests"]) == 1


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://attacker.test"},
        {"aud": "other"},
        {"aud": [TRUST.audience]},
        {"sub": ""},
        {"sub": "\ud800"},
        {"sub": "a" * 257},
        {"exp": 0},
        {"iat": int(time.time()) + 1000},
        {"nbf": int(time.time()) + 1000},
        {"exp": None},
        {"iat": True},
        {"exp": str(int(time.time()) + 600)},
    ],
)
def test_claim_rejections(rig, signing_keys, claims):
    verifier, _ = rig
    with pytest.raises(InvalidAccessToken):
        verifier.verify(token(signing_keys[0], claims=claims))


@pytest.mark.parametrize(
    "header",
    [
        {"typ": "JWT"},
        {"typ": "id+jwt"},
        {"jku": "https://attacker.test/keys"},
        {"x5u": "https://attacker.test/cert"},
        {"jwk": {}},
        {"crit": []},
        {"kid": "a" * 129},
    ],
)
def test_header_rejected_before_fetch(rig, signing_keys, header):
    verifier, state = rig
    with pytest.raises(InvalidAccessToken):
        verifier.verify(token(signing_keys[0], header=header))
    assert state["requests"] == []


def test_algorithm_confusion_and_size(rig):
    verifier, state = rig
    for value in [
        jwt.encode(
            {"sub": "alice"},
            "x" * 64,
            algorithm="HS256",
            headers={"typ": "at+jwt", "kid": "key-one"},
        ),
        "x" * 8193,
        "☃",
        "not.a.token",
    ]:
        with pytest.raises(InvalidAccessToken):
            verifier.verify(value)
    assert not state["requests"]


def test_rotation_unknown_kid_and_refresh_budget(rig, signing_keys):
    verifier, state = rig
    verifier.verify(token(signing_keys[0]))
    for number in range(100):
        with pytest.raises(InvalidAccessToken):
            verifier.verify(token(signing_keys[0], header={"kid": f"unknown-{number}"}))
    assert len(state["requests"]) == 1
    state["clock"] += 11
    state["keys"] = [public(signing_keys[1], "key-two")]
    verifier.verify(token(signing_keys[1], header={"kid": "key-two"}))
    assert len(state["requests"]) == 2
    with pytest.raises(InvalidAccessToken):
        verifier.verify(token(signing_keys[0]))


def test_same_kid_rotation_and_bad_signature(rig, signing_keys):
    verifier, state = rig
    verifier.verify(token(signing_keys[0]))
    with pytest.raises(InvalidAccessToken):
        verifier.verify(token(signing_keys[1]))
    state["clock"] += 11
    state["keys"] = [public(signing_keys[1])]
    verifier.verify(token(signing_keys[1]))
    assert len(state["requests"]) == 2


def test_outage_never_extends_expired_keys(rig, signing_keys):
    verifier, state = rig
    verifier.verify(token(signing_keys[0]))
    state["status"] = 503
    state["clock"] += 301
    for _ in range(2):
        with pytest.raises(KeyServiceUnavailable):
            verifier.verify(token(signing_keys[0]))
    assert len(state["requests"]) == 2
    state["clock"] += 11
    state["status"] = 200
    verifier.verify(token(signing_keys[0]))


def test_concurrent_cold_requests_share_one_fetch(rig, signing_keys):
    verifier, state = rig
    value = token(signing_keys[0])
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(result.subject == "alice" for result in pool.map(verifier.verify, [value] * 24))
    assert len(state["requests"]) == 1


@pytest.mark.parametrize("mode", ["duplicate", "private", "too-many", "weak", "wrong-alg"])
def test_invalid_public_key_sets_fail_closed(rig, signing_keys, mode):
    verifier, state = rig
    key = public(signing_keys[0])
    state["keys"] = {
        "duplicate": [key, key],
        "private": [{**key, "d": "private"}],
        "too-many": [{**key, "kid": str(i)} for i in range(17)],
        "weak": [public(rsa.generate_private_key(public_exponent=65537, key_size=1024))],
        "wrong-alg": [{**key, "alg": "HS256"}],
    }[mode]
    with pytest.raises(KeyServiceUnavailable):
        verifier.verify(token(signing_keys[0]))


@pytest.mark.parametrize("status", [302, 404, 500])
def test_key_http_failures_fail_closed(rig, signing_keys, status):
    verifier, state = rig
    state["status"] = status
    with pytest.raises(KeyServiceUnavailable):
        verifier.verify(token(signing_keys[0]))
    assert len(state["requests"]) == 1


def test_bounded_response_and_duplicate_json(signing_keys):
    for raw in [b" " * 65537, b'{"keys":[],"keys":[]}']:
        verifier = AccessTokenVerifier(
            TRUST,
            transport=httpx.MockTransport(lambda _, raw=raw: httpx.Response(200, content=raw)),
        )
        try:
            with pytest.raises(KeyServiceUnavailable):
                verifier.verify(token(signing_keys[0]))
        finally:
            verifier.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://identity.test",
        "https://user:pass@identity.test",
        "https://identity.test/#fragment",
        "https://identity.test/?secret=x",
    ],
)
def test_trust_configuration_rejected(url):
    with pytest.raises(ValueError):
        TokenTrust(url, "atlas", TRUST.jwks_url)


def test_duplicate_signed_claims_are_rejected_before_key_fetch(rig, signing_keys):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    verifier, state = rig
    ordinary = token(signing_keys[0]).split(".")
    payload = jwt.utils.base64url_decode(ordinary[1]).decode()
    payload = payload[:-1] + ',"sub":"mallory"}'
    message = ordinary[0].encode() + b"." + jwt.utils.base64url_encode(payload.encode())
    signature = signing_keys[0].sign(message, padding.PKCS1v15(), hashes.SHA256())
    value = (message + b"." + jwt.utils.base64url_encode(signature)).decode()
    with pytest.raises(InvalidAccessToken):
        verifier.verify(value)
    assert state["requests"] == []


def test_compressed_key_response_is_refused(signing_keys):
    verifier = AccessTokenVerifier(
        TRUST,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"keys": [public(signing_keys[0])]},
                headers={"content-encoding": "identity, gzip"},
            )
        ),
    )
    try:
        with pytest.raises(KeyServiceUnavailable):
            verifier.verify(token(signing_keys[0]))
    finally:
        verifier.close()
