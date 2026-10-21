"""Controlled HTTPS requests for opt-in sessions; not real browser/provider acceptance."""

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from test_cognito_tokens import TRUST, signed, verifier
from test_login_exchange import CONFIG

from atlas.api import create_app
from atlas.security.browser import BINDING_COOKIE, CSRF_HEADER, SESSION_COOKIE
from atlas.security.login import LoginExchange
from atlas.security.memberships import MembershipChange

ORIGIN = "https://atlas.example.invalid"


@pytest.fixture(scope="module")
def key():
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def browser_app(key):
    requests = []

    def token(request):
        requests.append(request)
        form = parse_qs(request.content.decode())
        if form["code"] != ["sample-code"]:
            return httpx.Response(400, stream=httpx.ByteStream(b"PRIVATE-PROVIDER-ERROR"))
        import json

        payload = {"access_token": signed(key), "expires_in": 300, "token_type": "Bearer"}
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(payload).encode()))

    tokens = verifier(key)
    exchange = LoginExchange(CONFIG, tokens, transport=httpx.MockTransport(token))
    app = create_app("sqlite://", token_verifier=tokens, login_exchange=exchange)
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
    try:
        with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
            yield client, app, requests
    finally:
        tokens.close()


def login(client):
    response = client.post("/auth/start", headers={"Origin": ORIGIN})
    assert response.status_code == 303
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    response = client.get("/auth/callback", params={"state": state, "code": "sample-code"})
    assert response.status_code == 303 and response.headers["location"] == "/"
    return response


def csrf(client):
    response = client.get("/auth/session")
    assert response.status_code == 200
    assert set(response.json()) == {"csrf_token", "expires_at"}
    return response.json()["csrf_token"]


def test_full_controlled_callback_sets_secure_cookies_without_exposing_tokens(browser_app):
    client, app, requests = browser_app
    response = client.post("/auth/start", headers={"Origin": ORIGIN})
    binding = response.headers["set-cookie"]
    assert (
        BINDING_COOKIE in binding
        and "HttpOnly" in binding
        and "Secure" in binding
        and "SameSite=lax" in binding
    )
    query = parse_qs(urlsplit(response.headers["location"]).query)
    response = client.get(
        "/auth/callback", params={"state": query["state"][0], "code": "sample-code"}
    )
    assert response.headers["location"] == "/"
    cookies = response.headers.get_list("set-cookie")
    assert any(
        SESSION_COOKIE in value
        and "HttpOnly" in value
        and "Secure" in value
        and "SameSite=strict" in value
        and "Domain=" not in value
        for value in cookies
    )
    assert any(BINDING_COOKIE in value and "Max-Age=0" in value for value in cookies)
    me = client.get("/api/me")
    assert me.status_code == 200 and me.json()["role"] == "reviewer"
    for result in [response, me, client.get("/auth/session")]:
        assert result.headers["cache-control"] == "no-store"
        assert result.headers["referrer-policy"] == "no-referrer"
        assert "Cookie" in result.headers["vary"]
        assert "access_token" not in result.text and "sample-code" not in result.text
    assert len(requests) == 1


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "https://other.invalid"}, {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"}],
)
def test_signin_start_requires_the_exact_browser_origin(browser_app, headers):
    client, _, requests = browser_app
    response = client.post("/auth/start", headers=headers)
    assert response.status_code == 403 and not response.headers.get("set-cookie")
    assert not requests


@pytest.mark.parametrize(
    "mutation", ["missing_origin", "foreign_origin", "missing_csrf", "wrong_csrf", "nonascii_csrf"]
)
def test_cookie_authenticated_writes_require_origin_and_csrf(browser_app, mutation):
    client, _, _ = browser_app
    login(client)
    headers = {"Origin": ORIGIN, CSRF_HEADER: csrf(client)}
    if mutation == "missing_origin":
        del headers["Origin"]
    elif mutation == "foreign_origin":
        headers["Origin"] = "https://other.invalid"
    elif mutation == "missing_csrf":
        del headers[CSRF_HEADER]
    elif mutation == "nonascii_csrf":
        headers[CSRF_HEADER] = b"\xff" * 43
    else:
        headers[CSRF_HEADER] = "x" * 43
    response = client.post("/api/jobs", json={}, headers=headers)
    assert response.status_code == 403


def test_valid_csrf_write_still_passes_through_the_ordinary_api_schema(browser_app):
    client, _, _ = browser_app
    login(client)
    response = client.post(
        "/api/jobs", json={}, headers={"Origin": ORIGIN, CSRF_HEADER: csrf(client)}
    )
    assert response.status_code == 422


def test_cookie_requests_cannot_mix_bearer_auth_or_cross_site_reads(browser_app):
    client, _, _ = browser_app
    login(client)
    assert (
        client.get("/api/me", headers={"Authorization": "Bearer another-credential"}).status_code
        == 400
    )
    assert client.get("/api/me", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_membership_is_rechecked_and_revocation_does_not_block_logout(browser_app):
    client, app, _ = browser_app
    login(client)
    app.state.memberships.change(
        MembershipChange(
            issuer=TRUST.issuer,
            subject="synthetic-alice",
            tenant="sample",
            role="reviewer",
            active=False,
            expected_version=1,
        )
    )
    assert client.get("/api/me").status_code == 403
    response = client.post("/auth/logout", headers={"Origin": ORIGIN, CSRF_HEADER: csrf(client)})
    assert response.status_code == 204
    assert client.get("/api/me").status_code == 401


def test_logout_removes_server_state_and_a_captured_cookie_cannot_return(browser_app):
    client, _, _ = browser_app
    login(client)
    old = client.cookies.get(SESSION_COOKIE)
    assert client.post("/auth/logout", headers={"Origin": ORIGIN}).status_code == 403
    assert (
        client.post(
            "/auth/logout", headers={"Origin": ORIGIN, CSRF_HEADER: csrf(client)}
        ).status_code
        == 204
    )
    client.cookies.set(SESSION_COOKIE, old)
    assert client.get("/api/me").status_code == 401


def test_expiry_and_service_close_invalidate_sessions(browser_app, monkeypatch):
    client, app, _ = browser_app
    login(client)
    manager = app.state.browser_login
    now = manager._clock()
    monkeypatch.setattr(manager, "_clock", lambda: now + 901)
    assert client.get("/api/me").status_code == 401
    monkeypatch.undo()
    login(client)
    manager.close()
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "query",
    [
        "state=unknown&code=sample-code",
        "state=one&state=two&code=sample-code",
        "error=access_denied&state=unknown",
        "state=unknown&code=" + "x" * 4096,
    ],
)
def test_rejected_callback_drops_query_secrets_and_never_calls_provider(browser_app, query):
    client, _, requests = browser_app
    response = client.get("/auth/callback?" + query)
    assert response.status_code == 303 and response.headers["location"] == "/?signin=failed"
    assert "sample-code" not in response.text and "access_denied" not in response.text
    assert not requests


def test_duplicate_session_cookies_are_rejected(browser_app):
    client, _, _ = browser_app
    login(client)
    value = client.cookies.get(SESSION_COOKIE)
    assert (
        client.get(
            "/api/me", headers={"Cookie": f"{SESSION_COOKIE}={value}; {SESSION_COOKIE}={value}"}
        ).status_code
        == 401
    )


def test_login_routes_are_absent_from_the_default_profile():
    app = create_app("sqlite://", {})
    assert not any(getattr(route, "path", "").startswith("/auth/") for route in app.routes)


def test_session_can_submit_a_real_job_and_viewer_membership_still_cannot(browser_app):
    import json
    from pathlib import Path

    client, app, _ = browser_app
    login(client)
    headers = {"Origin": ORIGIN, CSRF_HEADER: csrf(client), "Idempotency-Key": "session-job-one"}
    body = json.loads(Path("datasets/demo.json").read_text())
    response = client.post("/api/jobs", json=body, headers=headers)
    assert response.status_code == 202 and response.json()["status"] == "queued"
    app.state.memberships.change(
        MembershipChange(
            issuer=TRUST.issuer,
            subject="synthetic-alice",
            tenant="sample",
            role="viewer",
            active=True,
            expected_version=1,
        )
    )
    headers["Idempotency-Key"] = "session-job-two"
    assert client.post("/api/jobs", json=body, headers=headers).status_code == 403


def test_reauthentication_rotates_the_cookie_and_invalidates_the_old_session(browser_app):
    client, _, _ = browser_app
    login(client)
    old = client.cookies.get(SESSION_COOKIE)
    login(client)
    assert client.cookies.get(SESSION_COOKIE) != old
    assert client.get("/api/me", headers={"Cookie": f"{SESSION_COOKIE}={old}"}).status_code == 401
    assert client.get("/api/me").status_code == 200


def test_capacity_refusal_preserves_existing_sessions(browser_app):
    client, app, _ = browser_app
    app.state.browser_login._capacity = 1
    login(client)
    other = TestClient(app, base_url=ORIGIN, follow_redirects=False)
    try:
        response = other.post("/auth/start", headers={"Origin": ORIGIN})
        state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        response = other.get("/auth/callback", params={"state": state, "code": "sample-code"})
        assert response.headers["location"] == "/?signin=busy"
        assert other.cookies.get(SESSION_COOKIE) is None
        assert client.get("/api/me").status_code == 200
    finally:
        other.close()


def test_provider_refusal_creates_no_session_and_exposes_no_provider_error(browser_app):
    client, _, requests = browser_app
    response = client.post("/auth/start", headers={"Origin": ORIGIN})
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    response = client.get("/auth/callback", params={"state": state, "code": "bad-code"})
    assert response.headers["location"] == "/?signin=failed"
    assert "PRIVATE-PROVIDER-ERROR" not in response.text
    assert client.cookies.get(SESSION_COOKIE) is None
    assert client.get("/auth/session").status_code == 401
    assert len(requests) == 1


@pytest.mark.parametrize(
    "url,headers",
    [
        ("http://atlas.example.invalid/auth/start", {"Origin": ORIGIN}),
        ("/auth/start", {"Origin": ORIGIN, "Host": "other.invalid"}),
    ],
)
def test_login_routes_reject_http_and_unpinned_hosts(browser_app, url, headers):
    client, _, requests = browser_app
    assert client.post(url, headers=headers).status_code == 403
    assert not requests
