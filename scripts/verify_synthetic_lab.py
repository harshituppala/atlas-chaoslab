"""Record a real baseline child through the local synthetic ASGI session boundary."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from atlas.models.provenance import source_manifest
from atlas.synthetic_lab import Sessions, create_lab
from chaoslab.artifacts import publish_report


def main():
    junit = Path("var/synthetic-lab-tests.xml").read_bytes()
    cases = list(ET.fromstring(junit).iter("testcase"))
    focused = [c for c in cases if c.attrib.get("classname", "").endswith("test_synthetic_lab")]
    if len(focused) != 25 or any(
        c.find(tag) is not None for c in focused for tag in ("failure", "error", "skipped")
    ):
        raise ValueError("Expected all 25 actually executed synthetic boundary checks")
    if any(c.find(tag) is not None for c in cases for tag in ("failure", "error")):
        raise ValueError("Native regression gate failed")
    source = source_manifest()
    recorder = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    clock = [1000.0]
    registry = Sessions(clock=lambda: clock[0], capacity=2, ttl=10)
    origin = "https://lab.example.test"
    headers = {"Origin": origin}
    app = create_lab(origin, sessions=registry)
    with TestClient(app, base_url=origin) as first:
        assert first.get("/api/lab/run").status_code == 401
        assert first.post("/api/lab/session", json={}).status_code == 403
        opened = first.post("/api/lab/session", json={}, headers=headers)
        assert opened.status_code == 200
        cookie_flags = all(
            v in opened.headers["set-cookie"]
            for v in ["HttpOnly", "Secure", "SameSite=strict", "Path=/"]
        )
        assert cookie_flags
        response = first.post("/api/lab/run", json={"case_id": "municipal"}, headers=headers)
        assert response.status_code == 200
        result = response.json()
        assert result["provider"] == "extractive-baseline" and result["model_cost_usd"] == 0
        assert len(result["assessments"]) == 8
        assert all(a["review_state"] == "pending" for a in result["assessments"])
        citations = sum(1 + len(a["evidence"]) for a in result["assessments"])
        assert (
            first.post("/api/lab/run", json={"case_id": "municipal"}, headers=headers).json()
            == result
        )
        item = next(a for a in result["assessments"] if a["status"] == "evidence_found")
        route = "/api/lab/reviews/" + item["requirement"]["id"]
        review = {"version": 1, "decision": "approved", "note_code": "excerpt_checked"}
        assert first.post(route, json=review, headers=headers).status_code == 200
        assert first.post(route, json=review, headers=headers).status_code == 409
        second = TestClient(app, base_url=origin)
        try:
            assert second.post("/api/lab/session", json={}, headers=headers).status_code == 200
            assert second.get("/api/lab/run").status_code == 404
            assert second.get("/api/runs/" + result["id"]).status_code == 404
        finally:
            second.close()
        clock[0] += 11
        registry.sweep()
        assert first.get("/api/lab/run").status_code == 401
        assert not registry.items
    assert registry.closed
    if (
        source != source_manifest()
        or recorder != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ):
        raise ValueError("Synthetic boundary verification source changed")
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Local ASGI/TestClient requests with a real bounded baseline child and simulated HTTPS origin/expiry clock. Cookie attributes are inspected, not tested in a real browser/TLS session. No socket, hosted provider or durable customer-service claim.",
        "boundary_tests_passed": len(focused),
        "native_suite": {
            "passed": sum(c.find("skipped") is None for c in cases),
            "skipped": sum(c.find("skipped") is not None for c in cases),
        },
        "checks": {
            "anonymous_read_status": 401,
            "missing_origin_write_status": 403,
            "other_session_empty_result_status": 404,
            "private_api_status": 404,
            "stale_review_status": 409,
            "expired_session_status": 401,
            "publication_validated_requirements": 8,
            "publication_validated_citations": citations,
            "all_reviews_initially_pending": True,
            "repeat_analysis_reuses_result": True,
            "expired_stores_removed": True,
            "secure_cookie_attributes_present": cookie_flags,
        },
        "source_sha256": source["source_sha256"],
        "source_scope": source["scope"],
        "source_unchanged": True,
        "recorder_sha256": recorder,
        "junit_sha256": hashlib.sha256(junit).hexdigest(),
        "test_source_sha256": hashlib.sha256(
            Path("tests/test_synthetic_lab.py").read_bytes()
        ).hexdigest(),
        "test_hash_scope": "Test/JUnit identities captured after testing. ASGI exercise source separately checked before/after. Not signed execution attestation.",
        "provider_calls": 0,
    }
    publish_report(Path("reports/synthetic-lab-boundary.json"), report)
    print(json.dumps({"boundary_tests_passed": len(focused), "checks": report["checks"]}))


if __name__ == "__main__":
    main()
