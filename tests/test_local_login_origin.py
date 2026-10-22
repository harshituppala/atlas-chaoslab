"""Unprivileged loopback admission; provider endpoints retain their original pins."""

import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from test_login_exchange import CONFIG

from atlas.managed import create_managed_app, read_settings
from atlas.security.login import https_url

ORIGIN = "https://127.0.0.1:8443"


def local_config():
    return replace(
        CONFIG,
        trust=replace(
            CONFIG.trust, audience=ORIGIN + "/api", required_scopes=(ORIGIN + "/api/review",)
        ),
        redirect_uri=ORIGIN + "/auth/callback",
    )


def test_loopback_exception_does_not_change_default_url_or_provider_admission():
    config = local_config()
    assert not https_url(config.redirect_uri)
    assert https_url(config.redirect_uri, allow_loopback_port=True)
    with pytest.raises(ValueError, match="provider"):
        replace(config, provider_origin=ORIGIN)


@pytest.mark.parametrize(
    "origin",
    [
        "https://localhost:8443",
        "https://[::1]:8443",
        "https://127.0.0.2:8443",
        "https://example.invalid:8443",
        "http://127.0.0.1:8443",
        "https://127.0.0.1:8444",
        "https://user@127.0.0.1:8443",
    ],
)
def test_only_the_exact_reviewed_loopback_origin_is_admitted(origin):
    with pytest.raises(ValueError):
        replace(
            CONFIG,
            trust=replace(CONFIG.trust, audience=origin + "/api"),
            redirect_uri=origin + "/auth/callback",
        )


@pytest.mark.parametrize(
    "audience", ["https://127.0.0.1/api", "https://example.invalid/api", ORIGIN + "/different"]
)
def test_loopback_resource_must_match_callback_origin_and_api_path(audience):
    with pytest.raises(ValueError, match="origins must match"):
        replace(local_config(), trust=replace(CONFIG.trust, audience=audience))


def test_private_settings_and_start_route_keep_exact_host_and_origin_checks(tmp_path):
    config = local_config()
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "provider_origin": config.provider_origin,
                "redirect_uri": config.redirect_uri,
                "trust": vars(config.trust),
            }
        )
    )
    path.chmod(0o600)
    loaded = read_settings(path)
    assert loaded == config

    def no_provider_call(_):
        pytest.fail("Start admission must not contact the provider")

    app = create_managed_app(
        loaded,
        "sqlite://",
        key_transport=httpx.MockTransport(no_provider_call),
        token_transport=httpx.MockTransport(no_provider_call),
    )
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        for wrong in ("https://127.0.0.1", "https://localhost:8443", "null"):
            assert client.post("/auth/start", headers={"Origin": wrong}).status_code == 403
        assert (
            client.post("/auth/start", headers={"Origin": ORIGIN, "Host": "127.0.0.1"}).status_code
            == 403
        )
        response = client.post("/auth/start", headers={"Origin": ORIGIN})
        assert response.status_code == 303
        query = parse_qs(urlsplit(response.headers["location"]).query)
        assert query["redirect_uri"] == [ORIGIN + "/auth/callback"]
        assert query["resource"] == [ORIGIN + "/api"]
        assert query["code_challenge_method"] == ["S256"]
