from fastapi.testclient import TestClient

from atlas.api import create_app


def test_auth_errors_private_data_and_body_limit_errors_are_not_cached():
    app = create_app("sqlite://", {"viewer": {"tenant": "a", "actor": "alice", "role": "viewer"}})
    with TestClient(app) as client:
        responses = [
            client.get("/api/documents"),
            client.get("/api/documents", headers={"Authorization": "Bearer viewer"}),
            client.post("/api/jobs", content=b"x" * 1_500_001),
        ]
        assert [r.status_code for r in responses] == [401, 200, 413]
        for response in responses:
            assert response.headers["cache-control"] == "no-store"
            assert {name.strip() for name in response.headers["vary"].split(",")} == {
                "Authorization",
                "Cookie",
            }
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["x-frame-options"] == "DENY"


def test_workbench_html_blocks_unapproved_script_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frontend = tmp_path / "apps/web/dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<html><body>Fixture</body></html>")
    with TestClient(create_app("sqlite://", {})) as client:
        response = client.get("/")
        assert response.status_code == 200
        policy = response.headers["content-security-policy"]
        assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
        assert "unsafe-inline" not in policy
        assert policy.endswith("form-action 'self'")
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 200


def test_form_origin_rejects_csp_directive_injection():
    import pytest

    from atlas.http_privacy import ResponsePrivacy

    for origin in (
        "https://example.invalid;script-src:*",
        "https://*.example.invalid",
        "http://example.invalid",
    ):
        with pytest.raises(ValueError):
            ResponsePrivacy(None, form_origin=origin)


def test_pinned_provider_policy_does_not_expand_script_or_connect_sources():
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    from atlas.http_privacy import ResponsePrivacy

    app = FastAPI()
    app.add_middleware(ResponsePrivacy, form_origin="https://identity.example.invalid")

    @app.get("/")
    def page():
        return HTMLResponse("<html><body>Fixture</body></html>")

    with TestClient(app) as client:
        policy = client.get("/").headers["content-security-policy"]
        assert policy.endswith("form-action 'self' https://identity.example.invalid")
        assert "script-src 'self';" in policy and "connect-src 'self';" in policy
