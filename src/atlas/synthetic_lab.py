"""Local preparation of a bounded, temporary synthetic lab; no private API mount."""

import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .domain import StrictModel
from .execution import fingerprint, validate_publication
from .http_privacy import ResponsePrivacy
from .limits import BodyLimit
from .store import Conflict, NotFound, Store
from .worker import execute_isolated

SEED_SHA256 = "11a0330cabcb9a3b576bc26b22312f4112d2437ec5ca327e3b3c6a5a0cce2c3d"
NOTES = {
    "excerpt_checked": "Synthetic exercise: source excerpt checked against the obligation.",
    "needs_followup": "Synthetic exercise: further evidence is needed before responding.",
}


@dataclass
class Session:
    store: Store
    expires: float
    active: bool = False
    run_id: str | None = None
    attempts: int = 0
    reviews: int = 0


class Sessions:
    """Process-local capacity and absolute expiry; active stores close on release."""

    def __init__(self, *, clock=time.monotonic, capacity=4, ttl=600):
        if (
            type(capacity) is not int
            or not 1 <= capacity <= 8
            or type(ttl) is not int
            or not 1 <= ttl <= 600
        ):
            raise ValueError("Invalid synthetic session limits")
        self.clock, self.capacity, self.ttl = clock, capacity, ttl
        self.items = {}
        self.lock = threading.Lock()
        self.closed = False
        self.window_start, self.starts = clock(), 0
        self.compute = threading.BoundedSemaphore(1)

    def _sweep(self):
        now = self.clock()
        for key, session in list(self.items.items()):
            if not session.active and (self.closed or session.expires <= now):
                session.store.engine.dispose()
                del self.items[key]

    def sweep(self):
        with self.lock:
            self._sweep()

    def close(self):
        with self.lock:
            self.closed = True
            self._sweep()

    def create(self):
        with self.lock:
            self._sweep()
            if self.closed or len(self.items) >= self.capacity:
                raise HTTPException(
                    503, "Synthetic session capacity unavailable", headers={"Retry-After": "60"}
                )
            token = secrets.token_urlsafe(32)
            self.items[hashlib.sha256(token.encode()).hexdigest()] = Session(
                Store("sqlite://"), self.clock() + self.ttl
            )
            return token

    @contextmanager
    def use(self, token):
        if not isinstance(token, str) or len(token) != 43:
            raise HTTPException(401, "Start a new synthetic session")
        key = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            self._sweep()
            session = self.items.get(key)
            if self.closed or session is None or session.expires <= self.clock():
                raise HTTPException(401, "Start a new synthetic session")
            if session.active:
                raise HTTPException(409, "Synthetic session is busy")
            session.active = True
        try:
            yield session
        finally:
            with self.lock:
                session.active = False
                self._sweep()

    def check(self, session):
        if self.closed or session.expires <= self.clock():
            raise HTTPException(401, "Start a new synthetic session")

    def reserve_start(self, session):
        with self.lock:
            self.check(session)
            if self.clock() - self.window_start >= 600:
                self.window_start, self.starts = self.clock(), 0
            if session.attempts >= 2 or self.starts >= 8:
                raise HTTPException(
                    429, "Synthetic analysis budget exhausted", headers={"Retry-After": "600"}
                )
            session.attempts += 1
            self.starts += 1


class SessionRequest(StrictModel):
    pass


class CaseRequest(StrictModel):
    case_id: Literal["municipal"]


class ReviewRequest(StrictModel):
    version: int = Field(ge=1, le=100)
    decision: Literal["approved", "rejected"]
    note_code: Literal["excerpt_checked", "needs_followup"]


class OriginPolicy:
    def __init__(self, app, origin):
        self.app, self.origin = app, origin

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.lower(): v for k, v in scope["headers"]}
            if headers.get(b"sec-fetch-site") == b"cross-site" or (
                scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}
                and headers.get(b"origin") != self.origin.encode()
            ):
                return await JSONResponse(
                    {"detail": "Same-origin request required"}, status_code=403
                )(scope, receive, send)
        await self.app(scope, receive, send)


def create_lab(origin, *, sessions=None, executor=None, web_root=None, execution_timeout_seconds=5):
    if type(execution_timeout_seconds) is not int or not 1 <= execution_timeout_seconds <= 30:
        raise ValueError("Synthetic execution deadline must be between 1 and 30 seconds")
    parsed = urlsplit(origin)
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError("Invalid synthetic origin port") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"})
    ):
        raise ValueError("Explicit HTTPS origin or loopback HTTP origin required")
    if any(
        os.getenv(k)
        for k in (
            "ATLAS_DATABASE_URL",
            "ATLAS_PRINCIPALS",
            "ATLAS_TOKEN_TRUST",
            "ATLAS_MODEL_JOB_SPEC",
            "ATLAS_ENABLE_BEDROCK_JOBS",
        )
    ):
        raise ValueError("Synthetic lab must not inherit private service configuration")
    raw = (Path(__file__).resolve().parents[2] / "datasets/demo.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SEED_SHA256:
        raise ValueError("Synthetic seed differs from reviewed bytes")
    frontend = Path(web_root).resolve() if web_root is not None else None
    if frontend is not None and (
        frontend.name != "dist-lab"
        or not (frontend / "index.html").is_file()
        or 'name="atlas-profile" content="temporary-synthetic-lab"'
        not in (frontend / "index.html").read_text()
    ):
        raise ValueError("Only the dedicated synthetic lab build may be mounted")
    registry = sessions if sessions is not None else Sessions()
    execute = executor or partial(execute_isolated, timeout_seconds=execution_timeout_seconds)
    secure = parsed.scheme == "https"
    cookie = "__Host-atlas-lab" if secure else "atlas-lab-local"

    @asynccontextmanager
    async def lifespan(app):
        async def sweep():
            while True:
                await asyncio.sleep(1)
                registry.sweep()

        task = asyncio.create_task(sweep())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            registry.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.sessions = registry
    app.add_middleware(
        BodyLimit, maximum=4096, timeout_seconds=3, maximum_chunks=128, maximum_inflight=4
    )
    app.add_middleware(OriginPolicy, origin=origin)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[parsed.hostname])
    app.add_middleware(ResponsePrivacy)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse(
            {"detail": "Request does not match the synthetic API schema"}, status_code=422
        )

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie, Origin"
        return response

    def token(request):
        return request.cookies.get(cookie)

    @app.get("/healthz")
    def health():
        return {"status": "ok", "profile": "temporary-synthetic-lab", "production_validated": False}

    @app.post("/api/lab/session")
    def start(body: SessionRequest, request: Request, response: Response):
        if token(request):
            try:
                with registry.use(token(request)) as session:
                    return {
                        "expires_in_seconds": math.ceil(session.expires - registry.clock()),
                        "synthetic_only": True,
                        "state_resets_on_restart": True,
                    }
            except HTTPException as exc:
                if exc.status_code != 401:
                    raise
        value = registry.create()
        response.set_cookie(
            cookie,
            value,
            httponly=True,
            secure=secure,
            samesite="strict",
            max_age=registry.ttl,
            path="/",
        )
        return {
            "expires_in_seconds": registry.ttl,
            "synthetic_only": True,
            "state_resets_on_restart": True,
        }

    @app.get("/api/lab/session")
    def session_metadata(request: Request):
        with registry.use(token(request)) as session:
            return {
                "expires_in_seconds": math.ceil(session.expires - registry.clock()),
                "synthetic_only": True,
                "state_resets_on_restart": True,
            }

    @app.delete("/api/lab/session", status_code=204)
    def end(request: Request, response: Response):
        with registry.use(token(request)) as session:
            session.expires = 0
        response.delete_cookie(cookie, path="/", secure=secure, httponly=True, samesite="strict")

    @app.get("/api/lab/run")
    def result(request: Request):
        with registry.use(token(request)) as session:
            if session.run_id is None:
                raise HTTPException(404, "Run the synthetic case first")
            return session.store.get("synthetic", session.run_id)

    @app.post("/api/lab/run")
    def analyze(body: CaseRequest, request: Request):
        with registry.use(token(request)) as session:
            if session.run_id is not None:
                return session.store.get("synthetic", session.run_id)
            if not registry.compute.acquire(blocking=False):
                raise HTTPException(503, "Synthetic analysis is busy", headers={"Retry-After": "5"})
            try:
                registry.reserve_start(session)
                seed = json.loads(raw)
                try:
                    output = validate_publication(seed, execute(json.loads(raw)))
                except TimeoutError:
                    logging.getLogger(__name__).warning("Synthetic analysis deadline exceeded")
                    raise HTTPException(503, "Synthetic analysis could not complete") from None
                except Exception:
                    logging.getLogger(__name__).warning(
                        "Synthetic analysis failed validation or execution"
                    )
                    raise HTTPException(503, "Synthetic analysis could not complete") from None
                registry.check(session)
                saved = session.store.save(
                    "synthetic", "municipal", fingerprint(seed), output, "synthetic-reviewer"
                )
                session.run_id = saved["id"]
                return saved
            finally:
                registry.compute.release()

    @app.post("/api/lab/reviews/{requirement_id}")
    def review(requirement_id: str, body: ReviewRequest, request: Request):
        with registry.use(token(request)) as session:
            if session.run_id is None:
                raise HTTPException(404, "Run the synthetic case first")
            if session.reviews >= 16:
                raise HTTPException(429, "Synthetic review budget exhausted")
            try:
                saved = session.store.review(
                    "synthetic",
                    "synthetic-reviewer",
                    session.run_id,
                    requirement_id,
                    body.version,
                    body.decision,
                    NOTES[body.note_code],
                )
            except NotFound:
                raise HTTPException(404, "Synthetic requirement not found") from None
            except Conflict:
                raise HTTPException(409, "Review changed or evidence requires follow-up") from None
            session.reviews += 1
            return saved

    if frontend is not None:
        app.mount("/", StaticFiles(directory=frontend, html=True), name="synthetic-web")
    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8133)
    parser.add_argument("--web-root")
    args = parser.parse_args()
    uvicorn.run(
        create_lab(f"http://127.0.0.1:{args.port}", web_root=args.web_root),
        host="127.0.0.1",
        port=args.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
