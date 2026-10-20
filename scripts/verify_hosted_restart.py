"""Hold a fictional session in memory across an operator-triggered provider restart."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

import httpx

from chaoslab.artifacts import publish_report

ORIGIN = "https://atlas-review-lab.onrender.com"


def main():
    before = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    headers = {"Origin": ORIGIN}
    with httpx.Client(base_url=ORIGIN, timeout=45, trust_env=False) as client:
        assert client.post("/api/lab/session", json={}, headers=headers).status_code == 200
        try:
            initial = client.post("/api/lab/run", json={"case_id": "municipal"}, headers=headers)
            assert initial.status_code == 200
            assert len(initial.json()["assessments"]) == 8
            metadata = client.get("/api/lab/session")
            assert metadata.status_code == 200
            remaining = metadata.json()["expires_in_seconds"]
            started = monotonic()
            print(
                "READY: restart this free lab service, wait until it is live, then enter continue.",
                flush=True,
            )
            if input().strip() != "continue":
                raise ValueError("Restart verification not confirmed")
            elapsed = monotonic() - started
            assert elapsed + 10 < remaining, "Session expiry would confound the restart check"
            assert client.get("/healthz").status_code == 200
            assert client.get("/api/lab/session").status_code == 401
            assert client.get("/api/lab/run").status_code == 401
            client.cookies.clear()
            assert client.post("/api/lab/session", json={}, headers=headers).status_code == 200
            response = client.post("/api/lab/run", json={"case_id": "municipal"}, headers=headers)
            assert response.status_code == 200
            result = response.json()
            assert len(result["assessments"]) == 8
            assert all(a["review_state"] == "pending" for a in result["assessments"])
            docs = {d["id"]: d["text"] for d in result["documents"]}
            citations = [
                c
                for a in result["assessments"]
                for c in [a["requirement"]["source"], *a["evidence"]]
            ]
            for citation in citations:
                text = docs[citation["document_id"]]
                assert hashlib.sha256(text.encode()).hexdigest() == citation["digest"]
                assert text[citation["start"] : citation["end"]] == citation["quote"]
            report = {
                "schema_version": 1,
                "executed_at": datetime.now(UTC).isoformat(),
                "url": ORIGIN,
                "status": "passed",
                "old_session_rejected_before_original_expiry": True,
                "restart_wait_seconds": elapsed,
                "new_analysis_requirements": 8,
                "validated_source_spans": len(citations),
                "all_new_reviews_pending": True,
                "verification_source_sha256": before,
                "limits": [
                    "Operator-triggered free-provider restart; not a crash, durable recovery, cold-start or availability benchmark.",
                    "Old cookie remains in process memory only and is not exported.",
                ],
            }
            assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == before
            publish_report(Path("reports/hosted-lab-restart.json"), report)
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "old_session_rejected": True,
                        "fresh_analysis_succeeded": True,
                    }
                )
            )
        finally:
            client.delete("/api/lab/session", headers=headers)


if __name__ == "__main__":
    main()
