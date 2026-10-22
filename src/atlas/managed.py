"""Explicit operator entry point for the private managed-sign-in application."""

import json
import os
import stat
from contextlib import asynccontextmanager

from .api import create_app
from .security.login import LoginConfig, LoginExchange, https_url, unique_object
from .security.tokens import AccessTokenVerifier, TokenTrust

MAX_SETTINGS_BYTES = 8192
CONFLICTING_SETTINGS = (
    "ATLAS_DEMO",
    "ATLAS_PRINCIPALS",
    "ATLAS_TOKEN_TRUST",
    "ATLAS_MODEL_JOB_SPEC",
)


def read_settings(path):
    """Read bounded, private operator settings without echoing their contents."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_mode & 0o077
                or info.st_size > MAX_SETTINGS_BYTES
            ):
                raise ValueError
            raw = source.read(MAX_SETTINGS_BYTES + 1)
        if len(raw) > MAX_SETTINGS_BYTES:
            raise ValueError
        value = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(value, dict) or set(value) != {
            "provider_origin",
            "redirect_uri",
            "trust",
        }:
            raise ValueError
        trust = value["trust"]
        if not isinstance(trust, dict) or set(trust) != {
            "issuer",
            "audience",
            "jwks_url",
            "profile",
            "client_id",
            "required_scopes",
        }:
            raise ValueError
        if not (
            all(https_url(trust[key]) for key in ("issuer", "jwks_url"))
            and https_url(trust["audience"], allow_loopback_port=True)
        ):
            raise ValueError
        return LoginConfig(TokenTrust(**trust), value["provider_origin"], value["redirect_uri"])
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("Managed settings must be a private, bounded, valid JSON file") from None


def create_managed_app(config, database_url, *, key_transport=None, token_transport=None):
    """Own both HTTP clients; preserve per-request database membership checks.

    Transport injection is for controlled acceptance tests. Normal operation uses
    standard certificate validation, pinned endpoints and no environment proxy.
    """
    if any(name in os.environ for name in CONFLICTING_SETTINGS):
        raise ValueError("Remove conflicting demo, bearer-trust or model settings")
    if not isinstance(config, LoginConfig) or not isinstance(database_url, str) or not database_url:
        raise ValueError("Explicit login configuration and database are required")
    verifier = AccessTokenVerifier(config.trust, transport=key_transport)
    exchange = None
    try:
        exchange = LoginExchange(config, verifier, transport=token_transport)
        app = create_app(
            database_url, principals={}, token_verifier=verifier, login_exchange=exchange
        )
    except BaseException:
        try:
            if exchange is not None:
                exchange.close()
        finally:
            verifier.close()
        raise

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with original_lifespan(app):
                yield
        finally:
            try:
                verifier.close()
            finally:
                app.state.store.engine.dispose()

    app.router.lifespan_context = lifespan
    return app


def create_from_environment():
    """Uvicorn --factory target. No default database or credential fallback."""
    path = os.environ.get("ATLAS_LOGIN_SETTINGS")
    database_url = os.environ.get("ATLAS_DATABASE_URL")
    if not path or not database_url:
        raise ValueError("Set ATLAS_LOGIN_SETTINGS and ATLAS_DATABASE_URL explicitly")
    return create_managed_app(read_settings(path), database_url)
