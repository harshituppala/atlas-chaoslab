"""Bounded resource-access JWT verification. No tenant/role authorization is inferred.

The deployment operator pins issuer, resource audience, and HTTPS JWKS endpoint.
RS256 resource access tokens use an explicit operator-selected profile. The default
requires at+jwt. Cognito resource-bound access tokens additionally pin the app
client and required scopes. Neither profile accepts ID tokens or grants membership.
"""

import json
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey


class InvalidAccessToken(Exception):
    """Credential rejected; callers must not expose provider details or the token."""


class KeyServiceUnavailable(Exception):
    """No current trusted key set is available; fail closed, separately from bad credentials."""


@dataclass(frozen=True)
class TokenTrust:
    issuer: str
    audience: str
    jwks_url: str
    profile: str = "rfc9068"
    client_id: str | None = None
    required_scopes: tuple[str, ...] = ()

    def __post_init__(self):
        for value in (self.issuer, self.jwks_url):
            url = urlsplit(value)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.fragment
                or url.query
                or len(value) > 2048
            ):
                raise ValueError("Trust endpoints must be explicit HTTPS URLs without credentials")
        if not isinstance(self.audience, str) or not self.audience or len(self.audience) > 256:
            raise ValueError("A bounded resource audience is required")
        if not isinstance(self.profile, str) or self.profile not in {"rfc9068", "cognito-resource"}:
            raise ValueError("Unknown access-token profile")
        if self.profile == "rfc9068":
            if self.client_id is not None or self.required_scopes:
                raise ValueError("Provider fields require the explicit Cognito profile")
            return
        if not isinstance(self.client_id, str) or not 1 <= len(self.client_id) <= 128:
            raise ValueError("Cognito profile requires a bounded app client")
        if self.jwks_url != self.issuer.rstrip("/") + "/.well-known/jwks.json":
            raise ValueError("Cognito keys must be bound to the pinned issuer")
        if (
            not isinstance(self.required_scopes, (tuple, list))
            or not 1 <= len(self.required_scopes) <= 20
        ):
            raise ValueError("Cognito profile requires explicit API scopes")
        if any(
            not isinstance(scope, str)
            or not 1 <= len(scope) <= 256
            or any(not 33 <= ord(c) <= 126 or c in {'"', "\\"} for c in scope)
            for scope in self.required_scopes
        ):
            raise ValueError("Invalid required API scope")
        if len(set(self.required_scopes)) != len(self.required_scopes):
            raise ValueError("Duplicate required API scope")
        object.__setattr__(self, "required_scopes", tuple(self.required_scopes))


@dataclass(frozen=True)
class VerifiedSubject:
    issuer: str
    subject: str
    expires_at: int


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


class AccessTokenVerifier:
    MAX_TOKEN_BYTES = 8192
    MAX_JWKS_BYTES = 65536
    CACHE_SECONDS = 300
    REFRESH_INTERVAL = 10

    def __init__(self, trust: TokenTrust, *, transport=None, monotonic=time.monotonic):
        self.trust = trust
        self._clock = monotonic
        self._lock = threading.Lock()
        self._keys = {}
        self._expires = 0.0
        self._last_attempt = float("-inf")
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(3.0),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            follow_redirects=False,
            trust_env=False,
        )

    def close(self):
        self._client.close()

    def _fetch(self):
        try:
            deadline = time.monotonic() + 3.0
            with self._client.stream(
                "GET",
                self.trust.jwks_url,
                headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            ) as response:
                response.raise_for_status()
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise ValueError("Compressed key sets are not supported")
                data = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() > deadline:
                        raise ValueError("Key service deadline exceeded")
                    data.extend(chunk)
                    if len(data) > self.MAX_JWKS_BYTES:
                        raise ValueError("Key set exceeds byte budget")
            payload = json.loads(data, object_pairs_hook=_unique_object)
            entries = payload["keys"]
            if not isinstance(entries, list) or not 1 <= len(entries) <= 16:
                raise ValueError("Key set exceeds key budget")
            keys = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("Malformed key")
                if entry.get("kty") != "RSA" or entry.get("use", "sig") != "sig":
                    continue
                if entry.get("alg", "RS256") != "RS256":
                    continue
                if entry.get("key_ops", ["verify"]) != ["verify"]:
                    continue
                kid = entry.get("kid")
                if not isinstance(kid, str) or not 1 <= len(kid) <= 128 or kid in keys:
                    raise ValueError("Key identity missing or duplicated")
                if any(field in entry for field in ("d", "p", "q", "dp", "dq", "qi", "oth")):
                    raise ValueError("Private material in public key set")
                key = jwt.PyJWK(entry, algorithm="RS256").key
                if not isinstance(key, RSAPublicKey) or not 2048 <= key.key_size <= 4096:
                    raise ValueError("Unsupported RSA key size")
                if key.public_numbers().e != 65537:
                    raise ValueError("Unsupported RSA exponent")
                keys[kid] = key
            if not keys:
                raise ValueError("No supported verification keys")
            return keys
        except (httpx.HTTPError, ValueError, TypeError, KeyError, jwt.PyJWTError):
            raise KeyServiceUnavailable("Trusted signing keys unavailable") from None

    def _key(self, kid, *, force=False):
        # One refresh globally per interval, including failure and arbitrary unknown kids.
        # No attacker-controlled negative-cache dictionary is retained.
        with self._lock:
            now = self._clock()
            current = now < self._expires
            if current and kid in self._keys and not force:
                return self._keys[kid]
            if now - self._last_attempt >= self.REFRESH_INTERVAL:
                self._last_attempt = now
                try:
                    keys = self._fetch()
                except KeyServiceUnavailable:
                    if not current:
                        raise
                else:
                    self._keys = keys
                    self._expires = self._clock() + self.CACHE_SECONDS
                    current = True
            if not current:
                raise KeyServiceUnavailable("Trusted signing keys unavailable")
            if kid not in self._keys:
                raise InvalidAccessToken("Invalid access token")
            return self._keys[kid]

    def verify(self, token: str) -> VerifiedSubject:
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= self.MAX_TOKEN_BYTES:
                raise ValueError("Token size invalid")
            token.encode("ascii")
            # Reject ambiguous duplicate JSON members before the library's ordinary
            # JSON parser. This parsing supplies no trusted identity or permissions.
            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError("Malformed compact token")
            for part in parts[:2]:
                parsed = json.loads(
                    jwt.utils.base64url_decode(part), object_pairs_hook=_unique_object
                )
                if not isinstance(parsed, dict):
                    raise ValueError("Token components must be JSON objects")
            header = jwt.get_unverified_header(token)
            if (
                header.get("alg") != "RS256"
                or header.get("typ")
                not in (
                    {"at+jwt", "application/at+jwt"}
                    if self.trust.profile == "rfc9068"
                    else {None, "JWT"}
                )
                or any(field in header for field in ("jku", "x5u", "jwk", "crit", "b64"))
                or not isinstance(header.get("kid"), str)
                or not 1 <= len(header["kid"]) <= 128
            ):
                raise ValueError("Unsupported token header")
            key = self._key(header["kid"])
            try:
                claims = self._decode(token, key)
            except jwt.InvalidSignatureError:
                # Support key replacement under the same kid, subject to the same refresh gate.
                claims = self._decode(token, self._key(header["kid"], force=True))
            if self.trust.profile == "cognito-resource":
                if (
                    claims.get("token_use") != "access"
                    or claims.get("client_id") != self.trust.client_id
                ):
                    raise ValueError("Wrong Cognito token purpose or app client")
                scope = claims.get("scope")
                if (
                    not isinstance(scope, str)
                    or not 1 <= len(scope) <= 2048
                    or any(not 32 <= ord(c) <= 126 or c in {'"', "\\"} for c in scope)
                ):
                    raise ValueError("Invalid OAuth scope claim")
                supplied = scope.split(" ")
                if "" in supplied or not set(self.trust.required_scopes) <= set(supplied):
                    raise ValueError("Required API scope missing")
            for field in ("exp", "iat", "nbf"):
                if field in claims and type(claims[field]) is not int:
                    raise ValueError("NumericDate must be an integer")
            if claims["exp"] <= claims["iat"]:
                raise ValueError("Invalid validity interval")
            subject = claims["sub"]
            if not isinstance(subject, str) or not 1 <= len(subject.encode("utf-8")) <= 256:
                raise ValueError("Invalid subject")
            return VerifiedSubject(self.trust.issuer, subject, claims["exp"])
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, UnicodeError):
            raise InvalidAccessToken("Invalid access token") from None

    def _decode(self, token, key):
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=self.trust.issuer,
            audience=self.trust.audience,
            leeway=0,
            options={"require": ["iss", "aud", "sub", "iat", "exp"], "strict_aud": True},
        )
