"""Controlled public discovery probes; no user credentials or live cloud requests."""

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from test_login_exchange import CONFIG

from atlas.security.provider import ProviderCheckFailed, check_provider

ROOT = Path(__file__).resolve().parents[1]
METADATA = {
    "issuer": CONFIG.trust.issuer,
    "jwks_uri": CONFIG.trust.jwks_url,
    "authorization_endpoint": CONFIG.provider_origin + "/oauth2/authorize",
    "token_endpoint": CONFIG.provider_origin + "/oauth2/token",
    "response_types_supported": ["code", "token"],
}


@pytest.fixture(scope="module")
def public_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), "kid": "probe-key"}


class Transport(httpx.MockTransport):
    def __init__(self, handler):
        super().__init__(handler)
        self.closed = False

    def close(self):
        self.closed = True
        super().close()


def response(raw):
    return httpx.Response(200, stream=httpx.ByteStream(raw))


def test_public_checks_pin_both_urls_and_close_clients_without_authentication(public_key):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert not request.headers.get("authorization") and not request.headers.get("cookie")
        if len(requests) == 1:
            assert str(request.url) == CONFIG.trust.issuer + "/.well-known/openid-configuration"
            return response(json.dumps(METADATA).encode())
        assert str(request.url) == CONFIG.trust.jwks_url
        return httpx.Response(200, json={"keys": [public_key]})

    metadata, keys = Transport(handler), Transport(handler)
    result = check_provider(CONFIG, metadata_transport=metadata, key_transport=keys)
    assert result == {
        "pinned_discovery_endpoints_match": True,
        "authorization_code_advertised": True,
        "supported_public_signing_keys": 1,
        "user_login_verified": False,
    }
    assert len(requests) == 2 and metadata.closed and keys.closed


@pytest.mark.parametrize(
    "field", ["issuer", "jwks_uri", "authorization_endpoint", "token_endpoint"]
)
def test_discovery_cannot_redirect_pinned_authority_or_key_requests(field):
    calls = []

    def handler(request):
        calls.append(request)
        return response(json.dumps({**METADATA, field: "https://PRIVATE-MARKER.invalid"}).encode())

    metadata = Transport(handler)
    keys = Transport(lambda _: pytest.fail("Keys must not be fetched after mismatched discovery"))
    with pytest.raises(ProviderCheckFailed) as error:
        check_provider(CONFIG, metadata_transport=metadata, key_transport=keys)
    assert str(error.value) == "Pinned provider discovery check failed"
    assert len(calls) == 1 and metadata.closed


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b"[]",
        b"PRIVATE-MARKER",
        b"\xff",
        b"[" * 1100,
        b'{"issuer":1,"issuer":2}',
        b" " * 65537,
        json.dumps({**METADATA, "response_types_supported": "code"}).encode(),
        json.dumps({**METADATA, "response_types_supported": ["token"]}).encode(),
        json.dumps({**METADATA, "unknown": float("nan")}).encode(),
    ],
)
def test_malformed_discovery_produces_fixed_failure_and_skips_keys(raw):
    keys = Transport(lambda _: pytest.fail("Keys must not be fetched"))
    with pytest.raises(ProviderCheckFailed, match="^Pinned provider discovery check failed$"):
        check_provider(
            CONFIG, metadata_transport=Transport(lambda _: response(raw)), key_transport=keys
        )


@pytest.mark.parametrize("kind", ["redirect", "compressed", "status", "timeout", "stream"])
def test_discovery_transport_failures_are_bounded_and_do_not_leak_details(kind):
    def handler(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("PRIVATE-MARKER", request=request)
        if kind == "stream":
            raise httpx.StreamError("PRIVATE-MARKER")
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "https://PRIVATE-MARKER.invalid"})
        if kind == "status":
            return httpx.Response(500, text="PRIVATE-MARKER")
        return httpx.Response(200, headers={"content-encoding": "gzip"})

    transport = Transport(handler)
    with pytest.raises(ProviderCheckFailed, match="^Pinned provider discovery check failed$"):
        check_provider(CONFIG, metadata_transport=transport)
    assert transport.closed


@pytest.mark.parametrize("raw", [b'{"keys":[]}', b"[" * 1100, b"PRIVATE-MARKER"])
def test_bad_signing_keys_are_reported_without_granting_or_claiming_login(raw):
    metadata = Transport(lambda _: response(json.dumps(METADATA).encode()))
    keys = Transport(lambda _: response(raw))
    with pytest.raises(ProviderCheckFailed, match="^Pinned provider signing-key check failed$"):
        check_provider(CONFIG, metadata_transport=metadata, key_transport=keys)
    assert metadata.closed and keys.closed


def test_offline_cli_records_scope_and_provenance_without_provider_access(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(asdict(CONFIG)))
    path.chmod(0o600)
    result = subprocess.run(
        [sys.executable, "scripts/check_managed_provider.py", "--settings", str(path)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["scope"] == "Offline settings admission"
    assert report["checks"] == {"settings_valid": True, "user_login_verified": False}
    assert len(report["configuration_sha256"]) == 64 and len(report["files_sha256"]) == 5
    assert (
        CONFIG.provider_origin not in result.stdout and CONFIG.trust.client_id not in result.stdout
    )


def test_invalid_settings_cli_returns_nonzero_without_a_success_report(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"client_secret":"PRIVATE-MARKER"}')
    path.chmod(0o600)
    result = subprocess.run(
        [sys.executable, "scripts/check_managed_provider.py", "--settings", str(path)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0 and result.stdout == ""
    assert "PRIVATE-MARKER" not in result.stderr and "Traceback" not in result.stderr
