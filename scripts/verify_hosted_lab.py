"""Exercise the public fictional lab over verified HTTPS; never export session cookies."""

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx

from chaoslab.artifacts import publish_report

ORIGIN = "https://atlas-review-lab.onrender.com"
REPORT = Path("reports/hosted-lab.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment-source", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{40}", args.deployment_source):
        parser.error("Use the full deployed source revision from the provider record")
    source = Path(__file__)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    headers = {"Origin": ORIGIN}
    observations = {}
    started = perf_counter()
    with httpx.Client(base_url=ORIGIN, timeout=45, trust_env=False) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["profile"] == "temporary-synthetic-lab"
        assert health.json()["production_validated"] is False
        navigation = {
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
        }
        entry = client.get("/", headers=navigation)
        assert entry.status_code == 200 and "set-cookie" not in entry.headers
        assert client.get("/api/lab/session", headers=navigation).status_code == 403
        assert (
            client.post("/api/lab/session", json={}, headers={**headers, **navigation}).status_code
            == 403
        )
        page = client.get("/")
        assert page.status_code == 200
        assert 'name="atlas-profile" content="temporary-synthetic-lab"' in page.text
        assert "connect-src 'self'" in page.headers["content-security-policy"]
        assert page.headers["cache-control"] == "no-store"
        assets = {}
        for url in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page.text):
            response = client.get(url)
            assert response.status_code == 200
            local = Path("apps/web/dist-lab") / url.lstrip("/")
            assert local.read_bytes() == response.content
            assets[url] = hashlib.sha256(response.content).hexdigest()
        assert len(assets) == 2
        assert client.get("/api/lab/run").status_code == 401
        assert client.post("/api/lab/session", json={}).status_code == 403
        session = client.post("/api/lab/session", json={}, headers=headers)
        assert session.status_code == 200
        cookie = session.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
        assert session.headers["set-cookie"].startswith("__Host-")
        try:
            response = client.post("/api/lab/run", json={"case_id": "municipal"}, headers=headers)
            assert response.status_code == 200
            run = response.json()
            assert run["provider"] == "extractive-baseline" and run["model_cost_usd"] == 0
            assert len(run["assessments"]) == 8
            assert all(a["review_state"] == "pending" for a in run["assessments"])
            documents = {d["id"]: d for d in run["documents"]}
            citations = [
                c for a in run["assessments"] for c in [a["requirement"]["source"], *a["evidence"]]
            ]
            for citation in citations:
                text = documents[citation["document_id"]]["text"]
                assert hashlib.sha256(text.encode()).hexdigest() == citation["digest"]
                assert 0 <= citation["start"] < citation["end"] <= len(text)
                assert text[citation["start"] : citation["end"]] == citation["quote"]
            assert (
                client.post("/api/lab/run", json={"case_id": "municipal"}, headers=headers).json()
                == run
            )
            item = next(a for a in run["assessments"] if a["status"] == "evidence_found")
            route = "/api/lab/reviews/" + item["requirement"]["id"]
            review = {"version": 1, "decision": "approved", "note_code": "excerpt_checked"}
            assert client.post(route, json=review, headers=headers).status_code == 200
            assert client.post(route, json=review, headers=headers).status_code == 409
            conflict = next(a for a in run["assessments"] if a["status"] == "conflicting_evidence")
            assert (
                client.post(
                    "/api/lab/reviews/" + conflict["requirement"]["id"],
                    json=review,
                    headers=headers,
                ).status_code
                == 409
            )
            assert client.get("/api/documents").status_code == 404
            assert (
                client.post("/api/lab/run", content="x" * 4097, headers=headers).status_code == 413
            )
            assert (
                client.post(
                    "/api/lab/session", json={}, headers={"Origin": "https://other.example.test"}
                ).status_code
                == 403
            )
            with httpx.Client(base_url=ORIGIN, timeout=20, trust_env=False) as other:
                assert other.post("/api/lab/session", json={}, headers=headers).status_code == 200
                try:
                    assert other.get("/api/lab/run").status_code == 404
                finally:
                    assert other.delete("/api/lab/session", headers=headers).status_code == 204
            observations = {
                "https_workflow": True,
                "cross_site_document_navigation": True,
                "cross_site_api_and_write_refused": True,
                "requirements": len(run["assessments"]),
                "independently_checked_source_spans": len(citations),
                "all_initial_reviews_pending": True,
                "human_review_and_stale_conflict": True,
                "conflicting_evidence_approval_refused": True,
                "session_isolation": True,
                "secure_httponly_strict_host_cookie": True,
                "origin_and_body_refusal": True,
                "private_upload_api_absent": True,
                "cached_analysis_reused": True,
                "served_assets_sha256": assets,
            }
        finally:
            assert client.delete("/api/lab/session", headers=headers).status_code == 204
        assert client.get("/api/lab/run").status_code == 401
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    report = {
        "schema_version": 1,
        "executed_at": datetime.now(UTC).isoformat(),
        "url": ORIGIN,
        "profile": "temporary-synthetic-lab",
        "deployment_source": args.deployment_source,
        "deployment_identity_scope": "Operator-supplied provider deployment record; not a runtime attestation.",
        "verification_source_sha256": before,
        "status": "passed",
        "elapsed_seconds": perf_counter() - started,
        "observations": observations,
        "limits": [
            "Small authored fictional baseline workflow; no model-quality claim.",
            "No hosted restart, cold-start, ten-minute expiry, load or invoice test in this run.",
            "Session/review history is intentionally temporary; full managed sign-in and durable service remain unfinished.",
            "TLS validated through the client trust store; no exhaustive transport or security audit.",
        ],
    }
    publish_report(REPORT, report)
    print(
        json.dumps(
            {"status": "passed", "url": ORIGIN, "requirements": 8, "source_spans": len(citations)}
        )
    )


if __name__ == "__main__":
    main()
