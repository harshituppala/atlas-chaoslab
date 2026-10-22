"""Read-only checks of pinned discovery metadata and public signing keys."""

import json
import time

import httpx

from .login import invalid_number, unique_object
from .tokens import AccessTokenVerifier, KeyServiceUnavailable


class ProviderCheckFailed(Exception):
    """Fixed operator error; never include provider bodies or configuration values."""


def check_provider(config, *, metadata_transport=None, key_transport=None):
    """Check public endpoints only; never follow metadata-supplied URLs.

    This does not exchange a code, inspect a user, verify a token or establish
    client/scope registration. Only an actual user flow can test those steps.
    """
    deadline = time.monotonic() + 5
    try:
        with httpx.Client(
            transport=metadata_transport,
            timeout=5,
            follow_redirects=False,
            trust_env=False,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        ) as client:
            with client.stream(
                "GET", config.trust.issuer.rstrip("/") + "/.well-known/openid-configuration"
            ) as response:
                if response.status_code != 200 or response.headers.get(
                    "content-encoding", "identity"
                ).lower() not in {"", "identity"}:
                    raise ValueError
                raw = bytearray()
                for block in response.iter_raw():
                    if time.monotonic() >= deadline or len(raw) + len(block) > 65536:
                        raise ValueError
                    raw.extend(block)
        if time.monotonic() >= deadline:
            raise ValueError
        metadata = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_number)
        expected = {
            "issuer": config.trust.issuer,
            "jwks_uri": config.trust.jwks_url,
            "authorization_endpoint": config.provider_origin + "/oauth2/authorize",
            "token_endpoint": config.provider_origin + "/oauth2/token",
        }
        if not isinstance(metadata, dict) or any(
            metadata.get(key) != value for key, value in expected.items()
        ):
            raise ValueError
        response_types = metadata.get("response_types_supported")
        if not isinstance(response_types, list) or "code" not in response_types:
            raise ValueError
    except (httpx.HTTPError, httpx.StreamError, ValueError, TypeError, RecursionError):
        raise ProviderCheckFailed("Pinned provider discovery check failed") from None

    verifier = AccessTokenVerifier(config.trust, transport=key_transport)
    try:
        # Use the same key admission as access-token verification. This deliberately
        # leaves the verifier's runtime key cache untouched and validates no JWT.
        count = len(verifier._fetch())
    except KeyServiceUnavailable:
        raise ProviderCheckFailed("Pinned provider signing-key check failed") from None
    finally:
        verifier.close()
    return {
        "pinned_discovery_endpoints_match": True,
        "authorization_code_advertised": True,
        "supported_public_signing_keys": count,
        "user_login_verified": False,
    }
