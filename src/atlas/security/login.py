"""Single-use authorization-code exchanges for an explicitly configured Cognito client.

This is a backend component, not an enabled browser-login route. The HTTP caller
must bind each attempt to an HttpOnly browser cookie, avoid logging callback
queries, and apply workspace membership independently after token verification.
"""

import base64
import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit

import httpx

from .tokens import InvalidAccessToken, KeyServiceUnavailable, TokenTrust, VerifiedSubject


class LoginRejected(Exception):
    """Fixed public failure; never attach provider responses or credentials."""


class LoginCapacity(Exception):
    pass


def https_url(value, *, origin=False):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        return False
    if any(ord(character) < 33 or ord(character) == 127 for character in value) or any(
        character in value for character in "\\?#"
    ):
        return False
    try:
        parsed = urlsplit(value)
        valid = (
            isinstance(value, str)
            and 1 <= len(value) <= 2048
            and parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.port in {None, 443}
            and not any(character.isspace() for character in value)
        )
        return valid and (not origin or parsed.path in {"", "/"})
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class LoginConfig:
    trust: TokenTrust
    provider_origin: str
    redirect_uri: str

    def __post_init__(self):
        if self.trust.profile != "cognito-resource":
            raise ValueError("Browser exchange requires the explicit Cognito resource profile")
        if not https_url(self.provider_origin, origin=True):
            raise ValueError("Login provider must be a pinned HTTPS origin")
        if not https_url(self.redirect_uri) or urlsplit(self.redirect_uri).path != "/auth/callback":
            raise ValueError("Login callback must be an exact HTTPS /auth/callback URL")
        if not https_url(self.trust.audience):
            raise ValueError("Login requires an HTTPS resource audience")
        object.__setattr__(self, "provider_origin", self.provider_origin.rstrip("/"))


@dataclass(frozen=True, repr=False)
class LoginStart:
    authorization_url: str
    browser_binding: str = field(repr=False)


@dataclass(frozen=True, repr=False)
class LoginResult:
    subject: VerifiedSubject
    access_token: str = field(repr=False)
    expires_at: int


@dataclass(frozen=True, repr=False)
class PendingAttempt:
    binding_digest: bytes
    verifier: str
    deadline: float


def invalid_number(_):
    raise ValueError("Invalid provider number")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate provider member")
        result[key] = value
    return result


class LoginExchange:
    ATTEMPT_SECONDS = 300
    MAX_RESPONSE_BYTES = 32768

    def __init__(
        self,
        config,
        token_verifier,
        *,
        transport=None,
        capacity=128,
        monotonic=time.monotonic,
        wall_time=time.time,
    ):
        if type(capacity) is not int or not 1 <= capacity <= 256:
            raise ValueError("Login capacity must be 1..256")
        if token_verifier.trust != config.trust:
            raise ValueError("Login exchange and token verifier trust must match")
        self.config, self.verifier = config, token_verifier
        self._clock, self._wall_time = monotonic, wall_time
        self._capacity, self._pending, self._lock = capacity, {}, threading.Lock()
        self._closed = False
        self._slots = threading.BoundedSemaphore(2)
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(5.0),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            follow_redirects=False,
            trust_env=False,
            headers={"Accept-Encoding": "identity"},
        )

    def close(self):
        with self._lock:
            self._pending.clear()
            self._closed = True
        self._client.close()

    def begin(self):
        now = self._clock()
        with self._lock:
            if self._closed:
                raise LoginRejected("Sign-in attempt rejected")
            self._pending = {
                key: value for key, value in self._pending.items() if value.deadline > now
            }
            if len(self._pending) >= self._capacity:
                raise LoginCapacity("Login capacity reached")
            state, binding, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            self._pending[state] = PendingAttempt(
                hashlib.sha256(binding.encode()).digest(), verifier, now + self.ATTEMPT_SECONDS
            )
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.config.trust.client_id,
                "redirect_uri": self.config.redirect_uri,
                "state": state,
                "scope": " ".join(self.config.trust.required_scopes),
                "resource": self.config.trust.audience,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
            }
        )
        return LoginStart(self.config.provider_origin + "/oauth2/authorize?" + query, binding)

    def finish(self, state, binding, code):
        if any(
            not isinstance(value, str) or not 1 <= len(value) <= maximum
            for value, maximum in ((state, 128), (binding, 128), (code, 2048))
        ):
            raise LoginRejected("Sign-in attempt rejected")
        now = self._clock()
        with self._lock:
            attempt = self._pending.get(state)
            if attempt is None or attempt.deadline <= now:
                self._pending.pop(state, None)
                raise LoginRejected("Sign-in attempt rejected")
            if not secrets.compare_digest(
                attempt.binding_digest, hashlib.sha256(binding.encode()).digest()
            ):
                raise LoginRejected("Sign-in attempt rejected")
            # Consume before network access. Ambiguous failures require a new
            # sign-in; no automatic replay of a code after a provider timeout.
            if not self._slots.acquire(blocking=False):
                raise LoginCapacity("Login capacity reached")
            del self._pending[state]
        form = {
            "grant_type": "authorization_code",
            "client_id": self.config.trust.client_id,
            "redirect_uri": self.config.redirect_uri,
            "code": code,
            "code_verifier": attempt.verifier,
        }
        request_deadline = self._clock() + 5.0
        try:
            with self._client.stream(
                "POST", self.config.provider_origin + "/oauth2/token", data=form
            ) as response:
                if response.status_code != 200 or response.headers.get(
                    "content-encoding", ""
                ).lower() not in {"", "identity"}:
                    raise LoginRejected("Sign-in attempt rejected")
                raw = bytearray()
                for chunk in response.iter_raw():
                    if (
                        self._clock() >= request_deadline
                        or len(raw) + len(chunk) > self.MAX_RESPONSE_BYTES
                    ):
                        raise LoginRejected("Sign-in attempt rejected")
                    raw.extend(chunk)
            if self._clock() >= request_deadline:
                raise LoginRejected("Sign-in attempt rejected")
            payload = json.loads(
                raw, object_pairs_hook=unique_object, parse_constant=invalid_number
            )
            if not isinstance(payload, dict):
                raise ValueError("Invalid provider payload")
            token, lifetime = payload.get("access_token"), payload.get("expires_in")
            kind = payload.get("token_type")
            if (
                not isinstance(token, str)
                or not 1 <= len(token) <= 8192
                or not isinstance(kind, str)
                or kind.lower() != "bearer"
                or type(lifetime) is not int
                or not 1 <= lifetime <= 86400
            ):
                raise ValueError("Invalid access response")
            subject = self.verifier.verify(token)
            return LoginResult(
                subject, token, min(subject.expires_at, int(self._wall_time()) + lifetime)
            )
        except (
            httpx.HTTPError,
            httpx.StreamError,
            ValueError,
            UnicodeError,
            InvalidAccessToken,
            KeyServiceUnavailable,
        ):
            raise LoginRejected("Sign-in attempt rejected") from None
        finally:
            self._slots.release()
