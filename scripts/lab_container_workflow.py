"""Inside the isolated lab image: real HTTP and restart-cookie boundary checks.

The before-phase cookie is a private protocol field. The host verifier must remove
it before reporting; it is passed back only through stdin after container restart.
"""

import hashlib
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

import httpx

from atlas.domain import Citation, Document

BASE = "http://127.0.0.1:8000"
HEADERS = {"Origin": BASE}


def ready(client):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if client.get("/healthz").status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Synthetic image did not become healthy")


def analyze(client):
    assert client.post("/api/lab/session", json={}, headers=HEADERS).status_code == 200
    response = client.post("/api/lab/run", json={"case_id": "municipal"}, headers=HEADERS)
    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "extractive-baseline" and result["model_cost_usd"] == 0
    assert len(result["assessments"]) == 8
    assert all(a["review_state"] == "pending" for a in result["assessments"])
    documents = {d["id"]: Document.model_validate(d) for d in result["documents"]}
    citations = [
        c for a in result["assessments"] for c in [a["requirement"]["source"], *a["evidence"]]
    ]
    assert all(Citation.model_validate(c).matches(documents[c["document_id"]]) for c in citations)
    return result, len(citations)


def main():
    assert os.getuid() == 10001
    interfaces = {name for _, name in socket.if_nameindex()}
    assert "lo" in interfaces
    # Kernel tunnel devices may exist while down in an isolated namespace.
    assert all(
        not int((Path("/sys/class/net") / name / "flags").read_text(), 16) & 1
        for name in interfaces - {"lo"}
    )
    assert len(Path("/proc/net/route").read_text().splitlines()) == 1
    with httpx.Client(base_url=BASE, trust_env=False, timeout=20) as client:
        ready(client)
        root = client.get("/")
        assert root.status_code == 200
        assert 'name="atlas-profile" content="temporary-synthetic-lab"' in root.text
        assert "connect-src 'self'" in root.headers["content-security-policy"]
        assets = {}
        for url in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', root.text):
            response = client.get(url)
            assert response.status_code == 200
            assert response.content == (Path("apps/web/dist-lab") / url.lstrip("/")).read_bytes()
            assets[url] = hashlib.sha256(response.content).hexdigest()
        assert len(assets) == 2
        if sys.argv[1] == "after":
            private = json.loads(sys.stdin.read(1024))
            client.cookies.set("atlas-lab-local", private["cookie"])
            assert client.get("/api/lab/session").status_code == 401
            assert client.get("/api/lab/run").status_code == 401
            client.cookies.clear()
            _, citations = analyze(client)
            print(
                json.dumps(
                    {
                        "old_cookie_rejected": True,
                        "new_analysis_succeeded": True,
                        "requirements": 8,
                        "validated_citations": citations,
                    }
                )
            )
            return
        assert sys.argv[1] == "before"
        assert client.get("/api/lab/session").status_code == 401
        assert client.post("/api/lab/session", json={}).status_code == 403
        result, citations = analyze(client)
        assert (
            client.post("/api/lab/run", json={"case_id": "municipal"}, headers=HEADERS).json()
            == result
        )
        item = next(a for a in result["assessments"] if a["status"] == "evidence_found")
        route = "/api/lab/reviews/" + item["requirement"]["id"]
        review = {"version": 1, "decision": "approved", "note_code": "excerpt_checked"}
        assert client.post(route, json=review, headers=HEADERS).status_code == 200
        assert client.post(route, json=review, headers=HEADERS).status_code == 409
        conflict = next(a for a in result["assessments"] if a["status"] == "conflicting_evidence")
        assert (
            client.post(
                "/api/lab/reviews/" + conflict["requirement"]["id"], json=review, headers=HEADERS
            ).status_code
            == 409
        )
        assert client.get("/api/documents").status_code == 404
        assert client.post("/api/lab/run", content="x" * 4097, headers=HEADERS).status_code == 413
        assert (
            client.post(
                "/api/lab/session", json={}, headers={"Origin": "https://other.example.test"}
            ).status_code
            == 403
        )
        assert client.get("/healthz", headers={"Host": "other.example.test"}).status_code == 400
        with httpx.Client(base_url=BASE, trust_env=False, timeout=5) as other:
            assert other.post("/api/lab/session", json={}, headers=HEADERS).status_code == 200
            assert other.get("/api/lab/run").status_code == 404
        writable_root = False
        try:
            Path("/app/.root-write-probe").write_text("not allowed")
            writable_root = True
        except OSError:
            pass
        assert not writable_root
        print(
            json.dumps(
                {
                    "requirements": 8,
                    "validated_citations": citations,
                    "all_reviews_initially_pending": True,
                    "human_review_and_stale_conflict_checked": True,
                    "conflicting_evidence_approval_refused": True,
                    "other_session_has_no_result": True,
                    "private_api_absent": True,
                    "origin_host_body_checks_passed": True,
                    "root_write_refused": True,
                    "served_assets_sha256": assets,
                    "restart_cookie": client.cookies.get("atlas-lab-local"),
                }
            )
        )


if __name__ == "__main__":
    main()
