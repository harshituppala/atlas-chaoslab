"""Opt-in HTTP login/session boundary. No routes exist unless explicitly attached.

Access tokens remain in process memory. Application membership is resolved by
ATLAS on every API request; a session never stores or grants a workspace role.
"""

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from .login import LoginCapacity, LoginRejected

BINDING_COOKIE = "__Host-atlas-login"
SESSION_COOKIE = "__Host-atlas-session"
CSRF_HEADER = "X-Atlas-CSRF"


@dataclass(frozen=True, repr=False)
class BrowserSession:
    access_token: str
    csrf: str
    deadline: float
    expires_at: int


def cookie_key(value):
    if (
        not isinstance(value, str)
        or len(value) != 43
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in value
        )
    ):
        return None
    return hashlib.sha256(value.encode()).digest()


class BrowserLogin:
    def __init__(self, exchange, *, capacity=128, monotonic=time.monotonic, wall_time=time.time):
        if type(capacity) is not int or not 1 <= capacity <= 256:
            raise ValueError("Browser session capacity must be 1..256")
        self.exchange = exchange
        callback = urlsplit(exchange.config.redirect_uri)
        self.origin = callback.scheme + "://" + callback.netloc
        self.host = callback.netloc.lower()
        self._clock, self._wall = monotonic, wall_time
        self._capacity, self._items = capacity, {}
        self._lock, self._closed = threading.Lock(), False

    def close(self):
        with self._lock:
            self._items.clear()
            self._closed = True
        self.exchange.close()

    def _secure_host(self, request):
        if request.url.scheme != "https" or request.headers.get("host", "").lower() != self.host:
            raise HTTPException(403, "Login origin rejected")

    def _origin(self, request, *, required=False):
        self._secure_host(request)
        origin = request.headers.get("origin")
        if (required or origin is not None) and origin != self.origin:
            raise HTTPException(403, "Login origin rejected")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Cross-site session request rejected")

    def _cookie(self, request, name):
        # Reject duplicate cookie names instead of relying on parser precedence.
        count = sum(
            part.strip().startswith(name + "=")
            for header in request.headers.getlist("cookie")
            for part in header.split(";")
        )
        if count != 1:
            return None
        return request.cookies.get(name)

    def has_session_cookie(self, request):
        return SESSION_COOKIE in request.cookies

    def _sweep(self):
        now, wall = self._clock(), self._wall()
        self._items = {
            key: value
            for key, value in self._items.items()
            if value.deadline > now and value.expires_at > wall
        }

    def credential(self, request):
        self._origin(request, required=request.method not in {"GET", "HEAD", "OPTIONS"})
        key = cookie_key(self._cookie(request, SESSION_COOKIE))
        with self._lock:
            self._sweep()
            session = self._items.get(key) if not self._closed else None
        if session is None:
            raise HTTPException(401, "Sign in again")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            csrf = request.headers.get(CSRF_HEADER, "")
            if cookie_key(csrf) is None or not secrets.compare_digest(csrf, session.csrf):
                raise HTTPException(403, "Session request rejected")
        return session

    def _create(self, result, old_cookie):
        lifetime = min(900, result.expires_at - int(self._wall()))
        if lifetime <= 0:
            raise LoginRejected("Sign-in attempt rejected")
        with self._lock:
            self._sweep()
            old_key = cookie_key(old_cookie)
            if self._closed or (len(self._items) >= self._capacity and old_key not in self._items):
                raise LoginCapacity("Browser session capacity reached")
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self._items.pop(old_key, None)
            self._items[cookie_key(token)] = BrowserSession(
                result.access_token, csrf, self._clock() + lifetime, int(self._wall()) + lifetime
            )
        return token, lifetime

    @staticmethod
    def _clear_binding(response):
        response.delete_cookie(BINDING_COOKIE, path="/", secure=True, httponly=True, samesite="lax")

    def attach(self, app):
        @app.post("/auth/start")
        def start(request: Request):
            self._origin(request, required=True)
            try:
                attempt = self.exchange.begin()
            except (LoginCapacity, LoginRejected):
                raise HTTPException(
                    503, "Sign-in is temporarily unavailable", headers={"Retry-After": "30"}
                ) from None
            response = RedirectResponse(attempt.authorization_url, status_code=303)
            response.set_cookie(
                BINDING_COOKIE,
                attempt.browser_binding,
                max_age=300,
                path="/",
                secure=True,
                httponly=True,
                samesite="lax",
            )
            return response

        @app.get("/auth/callback")
        def callback(request: Request):
            self._secure_host(request)
            response = RedirectResponse("/?signin=failed", status_code=303)
            self._clear_binding(response)
            if len(request.scope.get("query_string", b"")) > 4096:
                return response
            values = request.query_params
            names = list(values.keys())
            if set(names) != {"state", "code"} or any(
                len(values.getlist(name)) != 1 for name in names
            ):
                return response
            try:
                result = self.exchange.finish(
                    values["state"], self._cookie(request, BINDING_COOKIE), values["code"]
                )
                token, lifetime = self._create(result, self._cookie(request, SESSION_COOKIE))
            except LoginRejected:
                return response
            except LoginCapacity:
                response.headers["location"] = "/?signin=busy"
                return response
            response.headers["location"] = "/"
            response.set_cookie(
                SESSION_COOKIE,
                token,
                max_age=lifetime,
                path="/",
                secure=True,
                httponly=True,
                samesite="strict",
            )
            return response

        @app.get("/auth/session")
        def current(request: Request):
            session = self.credential(request)
            return JSONResponse(
                {
                    "csrf_token": session.csrf,
                    "expires_at": session.expires_at,
                }
            )

        @app.post("/auth/logout")
        def logout(request: Request):
            self._origin(request, required=True)
            # Existing sessions need CSRF proof. Expired/unknown cookies can be
            # cleared with same-origin admission without trusting their content.
            try:
                self.credential(request)
            except HTTPException as exc:
                if exc.status_code != 401:
                    raise
            key = cookie_key(self._cookie(request, SESSION_COOKIE))
            with self._lock:
                self._items.pop(key, None)
            response = Response(status_code=204)
            response.delete_cookie(
                SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict"
            )
            self._clear_binding(response)
            return response
