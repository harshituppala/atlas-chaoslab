import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from atlas.execution import execute
from atlas.synthetic_lab import Sessions, create_lab

ORIGIN = "https://lab.example.test"
HEADERS = {"Origin": ORIGIN}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in (
        "ATLAS_DATABASE_URL",
        "ATLAS_PRINCIPALS",
        "ATLAS_TOKEN_TRUST",
        "ATLAS_MODEL_JOB_SPEC",
        "ATLAS_ENABLE_BEDROCK_JOBS",
    ):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def output():
    return execute(json.loads(Path("datasets/demo.json").read_text()))


def start(c):
    return c.post("/api/lab/session", json={}, headers=HEADERS)


def analyze(c):
    return c.post("/api/lab/run", json={"case_id": "municipal"}, headers=HEADERS)


def test_real_child_cookie_review_conflicts_isolation_and_restart():
    app = create_lab(ORIGIN)
    with TestClient(app, base_url=ORIGIN) as a:
        r = start(a)
        assert r.status_code == 200 and r.json()["state_resets_on_restart"]
        assert all(
            v in r.headers["set-cookie"]
            for v in ["__Host-atlas-lab=", "HttpOnly", "Secure", "SameSite=strict", "Path=/"]
        )
        cookie = a.cookies.get("__Host-atlas-lab")
        response = analyze(a)
        assert response.status_code == 200
        result = response.json()
        assert len(result["assessments"]) == 8
        assert all(i["review_state"] == "pending" for i in result["assessments"])
        item = next(i for i in result["assessments"] if i["status"] == "evidence_found")
        review = {"version": 1, "decision": "approved", "note_code": "excerpt_checked"}
        url = "/api/lab/reviews/" + item["requirement"]["id"]
        assert a.post(url, json=review, headers=HEADERS).status_code == 200
        assert a.post(url, json=review, headers=HEADERS).status_code == 409
        conflict = next(i for i in result["assessments"] if i["status"] == "conflicting_evidence")
        assert (
            a.post(
                "/api/lab/reviews/" + conflict["requirement"]["id"], json=review, headers=HEADERS
            ).status_code
            == 409
        )
        b = TestClient(app, base_url=ORIGIN)
        try:
            assert start(b).status_code == 200
            assert b.get("/api/lab/run").status_code == 404
            assert b.get("/api/runs/" + result["id"]).status_code == 404
        finally:
            b.close()
    assert app.state.sessions.closed and not app.state.sessions.items
    with TestClient(create_lab(ORIGIN), base_url=ORIGIN) as c:
        c.cookies.set("__Host-atlas-lab", cookie)
        assert c.get("/api/lab/run").status_code == 401
        c.cookies.clear()
        assert start(c).status_code == 200
        assert c.delete("/api/lab/session", headers=HEADERS).status_code == 204
        assert c.get("/api/lab/run").status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "null"},
        {"Origin": "https://attacker.test"},
        {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_origin_rejection_before_state_creation(headers):
    app = create_lab(ORIGIN)
    with TestClient(app, base_url=ORIGIN) as c:
        r = c.post("/api/lab/session", json={}, headers=headers)
        assert r.status_code == 403 and r.headers["cache-control"] == "no-store"
        assert not app.state.sessions.items
        assert "access-control-allow-origin" not in r.headers


def test_no_private_routes_uploads_model_inputs_or_notes(output):
    with TestClient(
        create_lab(ORIGIN, executor=lambda _: copy.deepcopy(output)), base_url=ORIGIN
    ) as c:
        assert c.get("/api/lab/run").status_code == 401
        assert start(c).status_code == 200
        for path in ["/api/jobs", "/api/runs", "/api/documents", "/openapi.json"]:
            assert c.post(path, json={}, headers=HEADERS).status_code in {404, 405}
        for body in [{"case_id": "municipal", "rfp": "PRIVATE-CANARY"}, {"case_id": "bedrock"}]:
            r = c.post("/api/lab/run", json=body, headers=HEADERS)
            assert r.status_code == 422 and "PRIVATE-CANARY" not in r.text
        assert c.post("/api/lab/run", content="x" * 4097, headers=HEADERS).status_code == 413
        assert c.get("/healthz", headers={"Host": "attacker.test"}).status_code == 400
        body = analyze(c).json()
        item = body["assessments"][0]
        assert (
            c.post(
                "/api/lab/reviews/" + item["requirement"]["id"],
                json={
                    "version": 1,
                    "decision": "rejected",
                    "note_code": "needs_followup",
                    "note": "PRIVATE-CANARY",
                },
                headers=HEADERS,
            ).status_code
            == 422
        )


def test_expired_active_session_retains_capacity_until_release_and_cannot_publish(output):
    now = [1000.0]
    registry = Sessions(clock=lambda: now[0], capacity=1, ttl=10)
    entered, release = threading.Event(), threading.Event()

    def blocked(_):
        entered.set()
        assert release.wait(5)
        return copy.deepcopy(output)

    with TestClient(create_lab(ORIGIN, sessions=registry, executor=blocked), base_url=ORIGIN) as c:
        start(c)
        with ThreadPoolExecutor() as pool:
            future = pool.submit(analyze, c)
            assert entered.wait(5)
            assert c.get("/api/lab/run").status_code == 409
            now[0] += 11
            registry.sweep()
            assert len(registry.items) == 1
            assert start(c).status_code == 503
            release.set()
            assert future.result(timeout=5).status_code == 401
        assert not registry.items
        assert start(c).status_code == 200


def test_analysis_budgets_release_capacity_after_failure_and_redact_error():
    registry = Sessions()
    calls = []

    def fail(_):
        calls.append(1)
        raise RuntimeError("PRIVATE-ERROR-CANARY")

    with TestClient(create_lab(ORIGIN, sessions=registry, executor=fail), base_url=ORIGIN) as c:
        start(c)
        registry.compute.acquire()
        assert analyze(c).status_code == 503
        registry.compute.release()
        for _ in range(2):
            r = analyze(c)
            assert r.status_code == 503 and "PRIVATE-ERROR-CANARY" not in r.text
        assert analyze(c).status_code == 429 and len(calls) == 2


def test_global_start_budget_cannot_be_reset_by_session_churn():
    now = [1000.0]
    registry = Sessions(clock=lambda: now[0], capacity=1)
    for _ in range(8):
        token = registry.create()
        with registry.use(token) as session:
            registry.reserve_start(session)
            session.expires = 0
    token = registry.create()
    with registry.use(token) as session:
        with pytest.raises(HTTPException) as caught:
            registry.reserve_start(session)
        assert caught.value.status_code == 429
    now[0] += 601
    token = registry.create()
    with registry.use(token) as session:
        registry.reserve_start(session)
    registry.close()


def test_cached_analysis_and_review_write_limit(output):
    calls = []

    def executor(_):
        calls.append(1)
        return copy.deepcopy(output)

    with TestClient(create_lab(ORIGIN, executor=executor), base_url=ORIGIN) as c:
        start(c)
        body = analyze(c).json()
        assert analyze(c).json() == body and len(calls) == 1
        url = "/api/lab/reviews/" + body["assessments"][0]["requirement"]["id"]
        for version in range(1, 17):
            assert (
                c.post(
                    url,
                    json={
                        "version": version,
                        "decision": "rejected",
                        "note_code": "needs_followup",
                    },
                    headers=HEADERS,
                ).status_code
                == 200
            )
        assert (
            c.post(
                url,
                json={"version": 17, "decision": "rejected", "note_code": "needs_followup"},
                headers=HEADERS,
            ).status_code
            == 429
        )


def test_worker_forged_approval_cannot_publish(output):
    output["assessments"][0]["review_state"] = "approved"
    with TestClient(create_lab(ORIGIN, executor=lambda _: output), base_url=ORIGIN) as c:
        start(c)
        assert analyze(c).status_code == 503
        assert c.get("/api/lab/run").status_code == 404


@pytest.mark.parametrize(
    "name",
    [
        "ATLAS_DATABASE_URL",
        "ATLAS_PRINCIPALS",
        "ATLAS_TOKEN_TRUST",
        "ATLAS_MODEL_JOB_SPEC",
        "ATLAS_ENABLE_BEDROCK_JOBS",
    ],
)
def test_private_configuration_refused(name, monkeypatch):
    monkeypatch.setenv(name, "private")
    with pytest.raises(ValueError, match="private service"):
        create_lab(ORIGIN)


def test_session_start_is_idempotent_and_does_not_extend_absolute_ttl():
    now = [1000.0]
    sessions = Sessions(clock=lambda: now[0], capacity=1, ttl=10)
    with TestClient(create_lab(ORIGIN, sessions=sessions), base_url=ORIGIN) as c:
        assert start(c).status_code == 200
        cookie = c.cookies.get("__Host-atlas-lab")
        now[0] += 4
        response = start(c)
        assert response.status_code == 200 and response.json()["expires_in_seconds"] == 6
        assert c.cookies.get("__Host-atlas-lab") == cookie and len(sessions.items) == 1
        now[0] += 7
        assert c.get("/api/lab/run").status_code == 401
        assert not sessions.items


def test_idle_background_sweep_releases_expired_memory_without_another_request():
    import time

    now = [1000.0]
    sessions = Sessions(clock=lambda: now[0], capacity=1, ttl=10)
    with TestClient(create_lab(ORIGIN, sessions=sessions), base_url=ORIGIN) as c:
        start(c)
        now[0] += 11
        deadline = time.monotonic() + 3
        while sessions.items and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not sessions.items


@pytest.mark.parametrize(
    "origin",
    [
        "http://untrusted.test",
        "https://user:pass@lab.example.test",
        "https://lab.example.test/path",
        "https://lab.example.test:bad",
    ],
)
def test_origin_must_be_explicit_and_well_formed(origin):
    with pytest.raises(ValueError):
        create_lab(origin)


def test_seed_digest_refuses_unreviewed_dataset_bytes(monkeypatch):
    import atlas.synthetic_lab as lab

    monkeypatch.setattr(lab, "SEED_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="reviewed bytes"):
        lab.create_lab(ORIGIN)


def test_readonly_session_metadata_preserves_absolute_expiry():
    now = [1000.0]
    sessions = Sessions(clock=lambda: now[0], ttl=10)
    with TestClient(create_lab(ORIGIN, sessions=sessions), base_url=ORIGIN) as c:
        assert c.get("/api/lab/session").status_code == 401
        start(c)
        now[0] += 4
        response = c.get("/api/lab/session")
        assert response.status_code == 200
        assert response.json() == {
            "expires_in_seconds": 6,
            "synthetic_only": True,
            "state_resets_on_restart": True,
        }
        assert "set-cookie" not in response.headers
        now[0] += 7
        assert c.get("/api/lab/session").status_code == 401


def test_static_mount_requires_dedicated_lab_build_and_preserves_api_boundary(tmp_path):
    root = tmp_path / "dist-lab"
    root.mkdir()
    (root / "index.html").write_text("<html>Private workbench must not be mounted</html>")
    with pytest.raises(ValueError, match="dedicated"):
        create_lab(ORIGIN, web_root=root)
    (root / "index.html").write_text(
        '<html><head><meta name="atlas-profile" content="temporary-synthetic-lab"></head><body>Lab</body></html>'
    )
    with TestClient(create_lab(ORIGIN, web_root=root), base_url=ORIGIN) as c:
        response = c.get("/")
        assert response.status_code == 200
        assert "connect-src 'self'" in response.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "no-store"
        assert c.get("/api/lab/session").status_code == 401
        assert c.get("/api/documents").status_code == 404


@pytest.mark.parametrize("deadline", [0, 31, True, 5.5, float("inf"), "20"])
def test_execution_deadline_refuses_unbounded_or_wrong_typed_settings(deadline):
    with pytest.raises(ValueError, match="deadline"):
        create_lab(ORIGIN, execution_timeout_seconds=deadline)


def test_operator_deadline_and_timeout_release_preserve_private_errors(monkeypatch, output, caplog):
    import atlas.synthetic_lab as lab

    calls = []

    def run(body, timeout_seconds):
        calls.append(timeout_seconds)
        if len(calls) == 1:
            raise TimeoutError("private-source-canary")
        return output

    monkeypatch.setattr(lab, "execute_isolated", run)
    with TestClient(create_lab(ORIGIN, execution_timeout_seconds=20), base_url=ORIGIN) as client:
        start(client)
        failed = client.post("/api/lab/run", json={"case_id": "municipal"}, headers=HEADERS)
        assert failed.status_code == 503
        assert "private-source-canary" not in failed.text
        assert "private-source-canary" not in caplog.text
        assert "Synthetic analysis deadline exceeded" in caplog.text
        assert (
            client.post("/api/lab/run", json={"case_id": "municipal"}, headers=HEADERS).status_code
            == 200
        )
        assert calls == [20, 20]
