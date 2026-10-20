"""Explicitly paid one-case synthetic backend validation; not a browser/deployment test."""

import argparse
import json
import os
import re
import secrets
from functools import partial
from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient

from atlas.api import create_app
from atlas.artifacts import write_private_json
from atlas.models.contracts import BedrockConfig
from atlas.models.job_spec import job_spec
from atlas.models.provenance import source_manifest
from atlas.worker import execute_model_isolated, process_once
from chaoslab.artifacts import publish_report
from chaoslab.reasoning import inputs, score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--session-budget", default="var/bedrock/campaign-budget.json")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid or re.fullmatch(r"[a-z0-9-]{1,64}", args.name) is None:
        parser.error("Explicit paid opt-in and a bounded lowercase run name are required")
    directory = Path("var/model-jobs")
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / f"{args.name}.db"
    if database.exists():
        parser.error("Preserve the existing validation; choose a new name")
    raw = Path("datasets/reasoning.json").read_bytes()
    case = json.loads(raw)["cases"][0]
    body = inputs(case)
    os.environ["ATLAS_ENABLE_BEDROCK_JOBS"] = "1"
    spec_path = directory / f"{args.name}.spec.json"
    spec = job_spec(BedrockConfig.model_validate_json(Path(args.config).read_bytes()))
    write_private_json(spec_path, spec.model_dump(mode="json"))
    os.environ["ATLAS_MODEL_JOB_SPEC"] = str(spec_path)
    token = secrets.token_urlsafe(32)
    tenant = "synthetic-backend-validation"
    app = create_app(
        "sqlite:///" + str(database),
        {token: {"tenant": tenant, "actor": "validation-reviewer", "role": "reviewer"}},
    )
    source = source_manifest()
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": args.name}
    with TestClient(app) as client:
        submitted = client.post(
            "/api/jobs",
            json={
                **body,
                "execution_mode": "bedrock",
                "expected_model_config_sha256": spec.digest(),
            },
            headers=headers,
        )
        assert submitted.status_code == 202
        job = submitted.json()
        process_once(
            app.state.queue,
            model_executor=partial(
                execute_model_isolated, config_path=args.config, session_budget=args.session_budget
            ),
        )
        status = client.get("/api/jobs/" + job["id"], headers=headers).json()
        report = {
            "schema_version": 1,
            "scope": "One synthetic in-process FastAPI TestClient submission through a real isolated Bedrock worker and SQLite publication/readback. Not a browser, PostgreSQL, cloud deployment, load or production reliability validation.",
            "status": status["status"],
            "attempts": status["attempts"],
            "pipeline_version": status["pipeline_version"],
            "dataset_sha256": sha256(raw).hexdigest(),
            "source_sha256": source["source_sha256"],
            "source_unchanged": source_manifest()["source_sha256"] == source["source_sha256"],
            "case_id": case["id"],
            "cost_is_invoice": False,
        }
        if status["status"] == "succeeded":
            response = client.get("/api/runs/" + status["result_id"], headers=headers)
            assert response.status_code == 200
            run = response.json()
            assert run["model_config_sha256"] == job["model_config_sha256"]
            report["model_config_sha256"] = run["model_config_sha256"]
            report["checks"] = score(case, run)
            report["estimated_model_cost_usd"] = run["model_cost_usd"]
            report["provider"] = run["provider"]
            report["authenticated_readback"] = True
        write_private_json(directory / f"{args.name}.json", report)
        if report["source_unchanged"]:
            publish_report(Path("reports/model-job-backend.json"), report)
        print(json.dumps({k: report[k] for k in ("status", "attempts", "source_unchanged")}))


if __name__ == "__main__":
    main()
