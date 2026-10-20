import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atlas.api import create_app

PRINCIPALS = {
    "reviewer-token": {"tenant": "a", "actor": "alice", "role": "reviewer"},
    "analyst-token": {"tenant": "a", "actor": "bob", "role": "analyst"},
    "viewer-token": {"tenant": "a", "actor": "carol", "role": "viewer"},
    "other-token": {"tenant": "b", "actor": "mallory", "role": "reviewer"},
}


def auth(token="reviewer-token", key="unique-key-001"):
    return {"Authorization": "Bearer " + token, "Idempotency-Key": key}


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://", PRINCIPALS)) as client:
        yield client


@pytest.fixture
def demo():
    return json.loads(Path("datasets/demo.json").read_text())


def test_authentication_and_roles(client, demo):
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers=auth("bad-token")).status_code == 401
    assert client.post("/api/runs", json=demo, headers=auth("viewer-token")).status_code == 403


def test_tenant_isolation(client, demo):
    run = client.post("/api/runs", json=demo, headers=auth()).json()
    assert client.get("/api/runs/" + run["id"], headers=auth("other-token")).status_code == 404
    assert (
        client.get("/api/runs/" + run["id"] + "/audit", headers=auth("other-token")).status_code
        == 404
    )
    assert client.get("/api/runs", headers=auth("other-token")).json() == []


def test_idempotency_and_conflicting_content(client, demo):
    one = client.post("/api/runs", json=demo, headers=auth()).json()
    two = client.post("/api/runs", json=demo, headers=auth()).json()
    assert one["id"] == two["id"]
    demo["rfp"]["text"] += "\nChanged"
    assert client.post("/api/runs", json=demo, headers=auth()).status_code == 409


def test_review_compare_and_swap_and_audit(client, demo):
    run = client.post("/api/runs", json=demo, headers=auth()).json()
    item = next(a for a in run["assessments"] if a["status"] == "evidence_found")
    url = f"/api/runs/{run['id']}/reviews/{item['requirement']['id']}"
    body = {"version": 1, "decision": "approved", "note": "Source reviewed against requirement."}
    assert client.post(url, json=body, headers=auth("analyst-token")).status_code == 403
    assert client.post(url, json=body, headers=auth("other-token")).status_code == 404
    response = client.post(url, json=body, headers=auth())
    assert response.status_code == 200
    updated = next(
        a
        for a in response.json()["assessments"]
        if a["requirement"]["id"] == item["requirement"]["id"]
    )
    assert updated["version"] == 2 and updated["review_state"] == "approved"
    assert client.post(url, json=body, headers=auth()).status_code == 409
    events = client.get(f"/api/runs/{run['id']}/audit", headers=auth()).json()
    assert len(events) == 2 and events[-1]["actor"] == "alice"


def test_missing_evidence_cannot_be_approved(client, demo):
    run = client.post("/api/runs", json=demo, headers=auth()).json()
    item = next(a for a in run["assessments"] if a["status"] == "missing_evidence")
    url = f"/api/runs/{run['id']}/reviews/{item['requirement']['id']}"
    assert (
        client.post(
            url, json={"version": 1, "decision": "approved", "note": "Guess"}, headers=auth()
        ).status_code
        == 409
    )


def test_duplicate_document_ids_rejected(client, demo):
    demo["knowledge"][0]["id"] = demo["rfp"]["id"]
    assert client.post("/api/runs", json=demo, headers=auth()).status_code == 422


def test_persistence_after_reopening(tmp_path, demo):
    url = "sqlite:///" + str(tmp_path / "database.db")
    with TestClient(create_app(url, PRINCIPALS)) as client:
        run = client.post("/api/runs", json=demo, headers=auth()).json()
    with TestClient(create_app(url, PRINCIPALS)) as client:
        assert client.get("/api/runs/" + run["id"], headers=auth()).json()["id"] == run["id"]
    assert (tmp_path / "database.db").stat().st_mode & 0o777 == 0o600


def test_simultaneous_reviews_have_one_winner(tmp_path, demo):
    from concurrent.futures import ThreadPoolExecutor

    from atlas.store import Conflict

    app = create_app("sqlite:///" + str(tmp_path / "concurrent.db"), PRINCIPALS)
    with TestClient(app) as client:
        run = client.post("/api/runs", json=demo, headers=auth()).json()
    item = next(a for a in run["assessments"] if a["status"] == "evidence_found")

    def write(actor):
        try:
            app.state.store.review(
                "a", actor, run["id"], item["requirement"]["id"], 1, "approved", "Source checked"
            )
            return "accepted"
        except Conflict:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ["alice", "bob"]))
    assert sorted(outcomes) == ["accepted", "stale"]
    assert len(app.state.store.events("a", run["id"])) == 2


@pytest.mark.parametrize("field", ["id", "title", "text"])
def test_invalid_unicode_fails_before_storage(client, demo, field):
    demo["rfp"][field] = "private-contract-\ud800"
    # Use escaped JSON: a Python HTTP client's UTF-8 encoder correctly refuses the surrogate.
    response = client.post(
        "/api/jobs",
        content=json.dumps(demo),
        headers={**auth(), "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "private-contract" not in response.text
    assert client.get("/api/jobs", headers=auth()).json() == []


@pytest.mark.parametrize("mode", ["unknown-field", "wrong-type", "malformed-json", "invalid-note"])
def test_validation_errors_do_not_echo_private_input(client, demo, mode):
    secret = "CONFIDENTIAL-CUSTOMER-CONTRACT-123"
    url = "/api/jobs"
    if mode == "unknown-field":
        demo[secret] = secret
    elif mode == "wrong-type":
        demo["rfp"]["text"] = {secret: secret}
    elif mode == "invalid-note":
        url = "/api/runs/unknown/reviews/unknown"
        demo = {"version": 1, "decision": "approved", "note": {secret: secret}}
    body = json.dumps(demo) if mode != "malformed-json" else '{"' + secret + '":'
    response = client.post(
        url, content=body, headers={**auth(), "Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Request does not match the API schema"}
    assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_identity_and_explicit_workspace_selector(client):
    assert client.get("/api/me", headers=auth("viewer-token")).json() == {
        "tenant": "a",
        "actor": "carol",
        "role": "viewer",
        "authentication": "local-bearer",
    }
    assert client.get("/api/me", headers={**auth(), "X-Workspace-ID": "a"}).status_code == 200
    assert client.get("/api/me", headers={**auth(), "X-Workspace-ID": "b"}).status_code == 403


def test_nested_source_warning_invalid_unicode_is_rejected(client, demo):
    text = demo["rfp"]["text"]
    demo["rfp"]["source_map"] = {
        "format": "pdf",
        "raw_sha256": "0" * 64,
        "parser_version": "test",
        "segments": [{"unit": "page", "number": 1, "start": 0, "end": len(text)}],
        "warnings": ["private-warning-\ud800"],
    }
    response = client.post(
        "/api/jobs",
        content=json.dumps(demo),
        headers={**auth(), "Content-Type": "application/json"},
    )
    assert response.status_code == 422 and "private-warning" not in response.text


def test_public_live_reports_require_auth_and_exclude_private_discovery(
    client, tmp_path, monkeypatch
):
    import json

    monkeypatch.chdir(tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "baseline.json").write_text(json.dumps({"scope": "synthetic"}))
    (reports / "reasoning-live-v4.json").write_text(json.dumps({"scope": "published"}))
    (reports / "private-model-output.json").write_text(json.dumps({"secret": "private"}))
    assert client.get("/api/benchmarks").status_code == 401
    response = client.get("/api/benchmarks", headers=auth("viewer-token"))
    assert response.status_code == 200
    assert response.json()["live_reasoning"] == [{"scope": "published"}]
    assert "private" not in response.text
