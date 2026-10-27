"""Local synthetic identity fixture. Never mount these provider/control routes publicly."""

import base64
import hashlib
import json
import secrets
import ssl
import time
from dataclasses import asdict
from urllib.parse import parse_qs, urlencode

import httpx
import jwt
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from atlas.managed import create_managed_app, read_settings
from atlas.security.login import LoginConfig
from atlas.security.memberships import MembershipChange
from atlas.security.tokens import TokenTrust
from atlas.worker import process_once

APP = "https://127.0.0.1"
PROVIDER = "https://localhost"
SCOPE = APP + "/api/review"


def create_fixture(work, proxy, certificate, key, *, worker_control=None):
    context = ssl.create_default_context(cafile=str(certificate))
    trust = TokenTrust(
        issuer=PROVIDER,
        audience=APP + "/api",
        jwks_url=PROVIDER + "/.well-known/jwks.json",
        profile="cognito-resource",
        client_id="synthetic-browser-client",
        required_scopes=(SCOPE,),
    )
    settings = work / "managed-login.json"
    settings.write_text(json.dumps(asdict(LoginConfig(trust, PROVIDER, APP + "/auth/callback"))))
    settings.chmod(0o600)
    app = create_managed_app(
        read_settings(settings),
        "sqlite:///" + str(work / "atlas.db"),
        key_transport=httpx.HTTPTransport(verify=context, proxy=proxy),
        token_transport=httpx.HTTPTransport(verify=context, proxy=proxy),
    )
    exchange = app.state.browser_login.exchange
    version = 0
    metrics = {"authorized": 0, "token_exchanges": 0, "jwks_requests": 0, "pkce_rejections": 0}

    def membership(active):
        nonlocal version
        version = app.state.memberships.change(
            MembershipChange(
                issuer=PROVIDER,
                subject="synthetic-reviewer",
                tenant="fictional-team",
                role="reviewer",
                active=active,
                expected_version=version,
            )
        )

    membership(True)
    provider = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    attempts, codes = {}, {}
    public_key = {
        **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
        "kid": "fixture-key",
    }

    @provider.get("/.well-known/jwks.json")
    def keys():
        metrics["jwks_requests"] += 1
        return {"keys": [public_key]}

    @provider.get("/oauth2/authorize")
    def authorize(request: Request):
        metrics["external_referrer_absent"] = "referer" not in request.headers
        query = dict(request.query_params)
        if not (
            query.get("client_id") == trust.client_id
            and query.get("redirect_uri") == exchange.config.redirect_uri
            and query.get("response_type") == "code"
            and query.get("code_challenge_method") == "S256"
            and query.get("resource") == trust.audience
            and SCOPE in query.get("scope", "").split()
        ):
            return JSONResponse({"error": "fixture_authorization_rejected"}, status_code=400)
        ticket = secrets.token_urlsafe(32)
        attempts[ticket] = query
        # Only the random fixture ticket enters HTML; never interpolate request values.
        return HTMLResponse(
            '<h1>Synthetic identity provider</h1><form method="post" action="/complete">'
            f'<input type="hidden" name="ticket" value="{ticket}">'
            '<button name="decision" value="allow">Continue as synthetic reviewer</button>'
            '<button name="decision" value="deny">Deny sign-in</button></form>',
            headers={"Content-Security-Policy": f"default-src 'none'; form-action 'self' {APP}"},
        )

    @provider.post("/complete")
    async def complete(request: Request):
        form = parse_qs((await request.body()).decode())
        query = attempts.pop(form.get("ticket", [""])[0], None)
        if not query:
            return JSONResponse({"error": "fixture_attempt_rejected"}, status_code=400)
        if form.get("decision") != ["allow"]:
            return RedirectResponse(
                exchange.config.redirect_uri
                + "?"
                + urlencode({"state": query["state"], "error": "access_denied"}),
                status_code=303,
            )
        code = secrets.token_urlsafe(32)
        codes[code] = query
        metrics["authorized"] += 1
        return RedirectResponse(
            exchange.config.redirect_uri + "?" + urlencode({"state": query["state"], "code": code}),
            status_code=303,
        )

    @provider.post("/oauth2/token")
    async def token(request: Request):
        form = parse_qs((await request.body()).decode())
        query = codes.pop(form.get("code", [""])[0], None)
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(form.get("code_verifier", [""])[0].encode()).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        if not query or not (
            query["code_challenge"] == challenge
            and form.get("client_id") == [trust.client_id]
            and form.get("redirect_uri") == [exchange.config.redirect_uri]
            and form.get("grant_type") == ["authorization_code"]
        ):
            metrics["pkce_rejections"] += 1
            return JSONResponse({"error": "fixture_exchange_rejected"}, status_code=400)
        now = int(time.time())
        access = jwt.encode(
            {
                "iss": trust.issuer,
                "aud": trust.audience,
                "sub": "synthetic-reviewer",
                "iat": now,
                "exp": now + 300,
                "client_id": trust.client_id,
                "token_use": "access",
                "scope": "openid " + SCOPE,
            },
            key,
            algorithm="RS256",
            headers={"kid": "fixture-key"},
        )
        metrics["token_exchanges"] += 1
        return {"access_token": access, "expires_in": 300, "token_type": "Bearer"}

    @provider.get("/cross-site")
    def cross_site():
        return HTMLResponse(f'<a href="{APP}/api/me">Try cross-site workspace access</a>')

    @provider.get("/probe/{action}")
    def control(action: str):
        # Deliberately unauthenticated synthetic test controls, reachable only through
        # this runner's loopback server. They are not part of the ATLAS application.
        if action == "revoke":
            membership(False)
        elif action == "restore":
            membership(True)
        elif action == "expire":
            app.state.browser_login._clock = lambda: time.monotonic() + 901
        elif action == "reset-clock":
            app.state.browser_login._clock = time.monotonic
        elif action in {"pause-worker", "resume-worker"} and worker_control is not None:
            worker_control(action)
        elif action == "process":
            if worker_control is not None:
                return JSONResponse({"error": "manual processing disabled"}, status_code=409)
            process_once(app.state.queue)
        else:
            return JSONResponse({"error": "unknown fixture control"}, status_code=404)
        return {"fixture_control": action}

    async def routing(scope, receive, send):
        host = dict(scope.get("headers", [])).get(b"host", b"").decode().lower()
        if scope.get("path") == "/auth/start":
            headers = dict(scope.get("headers", []))
            metrics["same_origin_form_post"] = headers.get(b"origin") == APP.encode()
        target = provider if host == "localhost" else app
        await target(scope, receive, send)

    def close():
        app.state.browser_login.close()
        exchange.verifier.close()
        app.state.store.engine.dispose()

    return routing, metrics, close
