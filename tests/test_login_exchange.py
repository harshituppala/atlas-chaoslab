"""Offline authorization-code exchange: controlled HTTP, real signed access JWTs."""

import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from test_cognito_tokens import TRUST, signed, verifier

from atlas.security.login import LoginCapacity, LoginConfig, LoginExchange, LoginRejected
from atlas.security.tokens import TokenTrust

CONFIG = LoginConfig(
    TRUST, "https://login.example.invalid", "https://atlas.example.invalid/auth/callback"
)


@pytest.fixture(scope="module")
def key():
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def state(start):
    return parse_qs(urlsplit(start.authorization_url).query)["state"][0]


@pytest.fixture
def exchange(key):
    created = []

    def factory(*, handler=None, **kwargs):
        requests = []
        access = signed(key)

        def token(request):
            requests.append(request)
            response = (
                handler(request)
                if handler
                else httpx.Response(
                    200,
                    json={
                        "access_token": access,
                        "expires_in": 300,
                        "token_type": "Bearer",
                        "refresh_token": "IGNORED-REFRESH",
                    },
                )
            )
            if response.is_stream_consumed:
                return httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    stream=httpx.ByteStream(response.content),
                )
            return response

        tokens = verifier(key)
        service = LoginExchange(CONFIG, tokens, transport=httpx.MockTransport(token), **kwargs)
        created.append((service, tokens))
        return service, requests, access

    yield factory
    for service, tokens in created:
        service.close()
        tokens.close()


def test_pkce_exchange_uses_pinned_resource_and_returns_verified_access_only(exchange):
    service, requests, access = exchange()
    start = service.begin()
    query = parse_qs(urlsplit(start.authorization_url).query)
    assert query["response_type"] == ["code"]
    assert query["resource"] == [TRUST.audience]
    assert query["scope"] == ["https://atlas.example.invalid/api/review"]
    assert query["redirect_uri"] == [CONFIG.redirect_uri]
    assert query["code_challenge_method"] == ["S256"]
    assert start.browser_binding not in start.authorization_url
    result = service.finish(state(start), start.browser_binding, "PRIVATE-AUTH-CODE")
    form = parse_qs(requests[0].content.decode())
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert query["code_challenge"] == [challenge]
    assert form["code"] == ["PRIVATE-AUTH-CODE"]
    assert form["redirect_uri"] == [CONFIG.redirect_uri]
    assert str(requests[0].url) == CONFIG.provider_origin + "/oauth2/token"
    assert "authorization" not in requests[0].headers and "client_secret" not in form
    assert requests[0].headers["accept-encoding"] == "identity"
    assert result.access_token == access and result.subject.subject == "synthetic-alice"
    assert result.expires_at <= result.subject.expires_at
    assert not hasattr(result, "refresh_token") and not hasattr(result, "role")
    assert access not in repr(result) and start.browser_binding not in repr(start)


@pytest.mark.parametrize("changed", ["state", "binding", "missing", "long_code", "expired"])
def test_invalid_attempt_never_reaches_provider(exchange, changed):
    now = [0.0]
    service, requests, _ = exchange(monotonic=lambda: now[0])
    start = service.begin()
    values = [state(start), start.browser_binding, "private-code"]
    if changed == "state":
        values[0] = "unknown"
    elif changed == "binding":
        values[1] = "another-browser"
    elif changed == "missing":
        values[1] = None
    elif changed == "long_code":
        values[2] = "x" * 2049
    else:
        now[0] = 300.0
    with pytest.raises(LoginRejected):
        service.finish(*values)
    assert not requests


def test_wrong_browser_cannot_consume_the_legitimate_attempt(exchange):
    service, requests, _ = exchange()
    start = service.begin()
    with pytest.raises(LoginRejected):
        service.finish(state(start), "wrong-browser", "wrong-code")
    service.finish(state(start), start.browser_binding, "real-code")
    assert len(requests) == 1


def test_concurrent_callback_replay_is_consumed_once(exchange):
    service, requests, _ = exchange()
    start = service.begin()

    def callback(_):
        try:
            service.finish(state(start), start.browser_binding, "same-code")
            return "accepted"
        except LoginRejected:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(callback, range(2))) == ["accepted", "rejected"]
    assert len(requests) == 1


def test_capacity_reclaims_expired_attempts_and_close_discards_state(exchange):
    now = [0.0]
    service, requests, _ = exchange(capacity=1, monotonic=lambda: now[0])
    first = service.begin()
    with pytest.raises(LoginCapacity):
        service.begin()
    now[0] = 301.0
    second = service.begin()
    assert state(first) != state(second)
    service.close()
    with pytest.raises(LoginRejected):
        service.finish(state(second), second.browser_binding, "code")
    with pytest.raises(LoginRejected):
        service.begin()
    assert not requests


@pytest.mark.parametrize(
    "problem",
    [
        "redirect",
        "timeout",
        "html",
        "duplicate",
        "nan",
        "oversized",
        "compressed",
        "id-token",
        "wrong-client",
        "wrong-resource",
        "wrong-scope",
        "boolean-lifetime",
        "unknown-token-type",
    ],
)
def test_failed_exchange_is_opaque_and_not_retried(exchange, key, problem):
    def handler(request):
        payload = {"access_token": signed(key), "expires_in": 300, "token_type": "Bearer"}
        if problem == "redirect":
            return httpx.Response(302, headers={"Location": "https://other.invalid/PRIVATE-CANARY"})
        if problem == "timeout":
            raise httpx.ReadTimeout("PRIVATE-CANARY", request=request)
        if problem == "html":
            return httpx.Response(200, text="PRIVATE-CANARY")
        if problem == "duplicate":
            return httpx.Response(
                200, content=b'{"access_token":"PRIVATE-CANARY","access_token":"duplicate"}'
            )
        if problem == "nan":
            return httpx.Response(200, content=b'{"access_token":NaN}')
        if problem == "oversized":
            return httpx.Response(200, content=b"x" * 32769)
        if problem == "compressed":
            return httpx.Response(
                200, headers={"Content-Encoding": "identity-unknown"}, content=b"PRIVATE-CANARY"
            )
        if problem == "id-token":
            payload["access_token"] = signed(key, claims={"token_use": "id"})
        elif problem == "wrong-client":
            payload["access_token"] = signed(key, claims={"client_id": "other"})
        elif problem == "wrong-resource":
            payload["access_token"] = signed(key, claims={"aud": "https://other.invalid"})
        elif problem == "wrong-scope":
            payload["access_token"] = signed(key, claims={"scope": "openid"})
        elif problem == "boolean-lifetime":
            payload["expires_in"] = True
        else:
            payload["token_type"] = "unknown"
        return httpx.Response(200, json=payload)

    service, requests, _ = exchange(handler=handler)
    start = service.begin()
    for _ in range(2):
        with pytest.raises(LoginRejected) as caught:
            service.finish(state(start), start.browser_binding, "PRIVATE-CANARY")
        assert str(caught.value) == "Sign-in attempt rejected"
    assert len(requests) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_origin", "http://login.example.invalid"),
        ("provider_origin", "https://login.example.invalid/path"),
        ("provider_origin", "https://user:password@login.example.invalid"),
        ("provider_origin", "https://login.example.invalid?"),
        ("provider_origin", "\x00https://login.example.invalid"),
        ("provider_origin", None),
        ("redirect_uri", "http://127.0.0.1:8000/auth/callback"),
        ("redirect_uri", "https://atlas.example.invalid/elsewhere"),
        ("redirect_uri", "https://atlas.example.invalid/auth/callback#"),
    ],
)
def test_login_configuration_rejects_ambiguous_or_unsafe_endpoints(field, value):
    with pytest.raises(ValueError):
        replace(CONFIG, **{field: value})


def test_generic_access_profile_cannot_silently_enable_cognito_login():
    generic = TokenTrust(
        issuer="https://issuer.invalid", audience="atlas", jwks_url="https://issuer.invalid/keys"
    )
    with pytest.raises(ValueError):
        LoginConfig(generic, CONFIG.provider_origin, CONFIG.redirect_uri)


def test_slow_token_stream_is_closed_and_consumed_attempt_cannot_retry(exchange):
    now, closed = [0.0], []

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            for chunk in (b"{", b'"access_token":', b'"late"}'):
                now[0] += 2.0
                yield chunk

        def close(self):
            closed.append(True)

    service, requests, _ = exchange(
        monotonic=lambda: now[0], handler=lambda _: httpx.Response(200, stream=SlowStream())
    )
    start = service.begin()
    with pytest.raises(LoginRejected):
        service.finish(state(start), start.browser_binding, "code")
    assert closed and len(requests) == 1
    with pytest.raises(LoginRejected):
        service.finish(state(start), start.browser_binding, "code")
    assert len(requests) == 1


def test_inflight_token_exchanges_are_bounded_without_consuming_waiting_attempt(exchange, key):
    import threading

    ready, release = threading.Barrier(3), threading.Event()

    def handler(_):
        if len(requests) <= 2:
            ready.wait(timeout=3)
            assert release.wait(timeout=3)
        return httpx.Response(
            200, json={"access_token": signed(key), "token_type": "Bearer", "expires_in": 300}
        )

    service, requests, _ = exchange(handler=handler)
    starts = [service.begin() for _ in range(3)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(service.finish, state(start), start.browser_binding, "code")
            for start in starts[:2]
        ]
        try:
            ready.wait(timeout=3)
            with pytest.raises(LoginCapacity):
                service.finish(state(starts[2]), starts[2].browser_binding, "code")
            assert len(requests) == 2
        finally:
            release.set()
        assert all(future.result().subject.subject == "synthetic-alice" for future in futures)
    # A failed admission made no provider request and left this attempt usable.
    assert (
        service.finish(state(starts[2]), starts[2].browser_binding, "code").subject.subject
        == "synthetic-alice"
    )


@pytest.mark.parametrize("capacity", [0, 257, True, 1.5])
def test_pending_capacity_requires_a_bounded_integer(key, capacity):
    tokens = verifier(key)
    try:
        with pytest.raises(ValueError):
            LoginExchange(CONFIG, tokens, capacity=capacity)
    finally:
        tokens.close()


def test_exchange_cannot_use_a_verifier_with_different_trust(key):
    tokens = verifier(key, replace(TRUST, client_id="other-client"))
    try:
        with pytest.raises(ValueError, match="trust must match"):
            LoginExchange(CONFIG, tokens)
    finally:
        tokens.close()
