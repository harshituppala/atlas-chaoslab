from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from test_api import PRINCIPALS, auth
from test_jobs import body as body
from test_jobs import queue as queue
from test_model_publication import publication as publication

from atlas.api import create_app
from atlas.execution import PIPELINE_VERSION, prepare_model_publication
from atlas.models.intelligence import MODEL_PIPELINE_VERSION
from atlas.store import Conflict
from atlas.worker import process_once


def spec():
    from datetime import UTC, datetime

    return {
        "model_id": "synthetic-model",
        "region": "ca-central-1",
        "limits": {
            "max_calls": 2,
            "max_input_tokens": 1000,
            "max_output_tokens": 100,
            "max_reserved_tokens": 2200,
            "max_estimated_cost_usd": "1",
        },
        "price_card": {
            "model_id": "synthetic-model",
            "region": "ca-central-1",
            "input_usd_per_million": "1",
            "output_usd_per_million": "2",
            "verified_on": datetime.now(UTC).date().isoformat(),
            "source": "https://aws.amazon.com/bedrock/pricing/",
        },
    }


def test_model_job_mode_is_bound_to_idempotency_and_baseline_workers_skip(queue, body):
    job = queue.submit(
        "tenant",
        "analyst",
        "model-key",
        body,
        pipeline_version=MODEL_PIPELINE_VERSION,
        model_spec=spec(),
    )
    assert job["max_attempts"] == 1
    assert not process_once(queue)
    assert queue.get("tenant", job["id"])["status"] == "queued"
    with pytest.raises(Conflict):
        queue.submit("tenant", "analyst", "model-key", body, pipeline_version=PIPELINE_VERSION)


def test_model_job_publishes_only_under_stored_model_identity(queue, publication):
    body, report = publication
    job = queue.submit(
        "tenant",
        "analyst",
        "model-key",
        body,
        pipeline_version=MODEL_PIPELINE_VERSION,
        model_spec=spec(),
    )
    payload = prepare_model_publication(
        {**body, "_model_spec": spec()}, report, estimated_cost_usd=None
    )
    assert process_once(queue, model_executor=lambda claim: deepcopy(payload))
    status = queue.get("tenant", job["id"])
    assert status["status"] == "succeeded"
    assert len(queue.store.list("tenant")) == 1


def test_model_timeout_never_retries_and_expired_crash_is_terminal(queue, body):
    job = queue.submit(
        "tenant",
        "analyst",
        "model-key",
        body,
        pipeline_version=MODEL_PIPELINE_VERSION,
        model_spec=spec(),
    )
    calls = []

    def fail(claim):
        calls.append(claim.id)
        raise TimeoutError("private")

    assert process_once(queue, model_executor=fail)
    assert queue.get("tenant", job["id"])["status"] == "failed"
    queue.clock.advance(1000)
    assert not process_once(queue, model_executor=fail)
    assert calls == [job["id"]]
    second = queue.submit(
        "tenant",
        "analyst",
        "crash-key",
        body,
        pipeline_version=MODEL_PIPELINE_VERSION,
        model_spec=spec(),
    )
    queue.claim(5)
    queue.clock.advance(6)
    assert queue.claim(5) is None
    assert queue.get("tenant", second["id"])["status"] == "failed"


def test_model_api_is_default_off_and_never_accepts_provider_config(tmp_path, body, monkeypatch):
    monkeypatch.delenv("ATLAS_ENABLE_BEDROCK_JOBS", raising=False)
    import json

    spec_path = tmp_path / "model-spec.json"
    spec_path.write_text(json.dumps(spec()))
    monkeypatch.setenv("ATLAS_MODEL_JOB_SPEC", str(spec_path))
    app = create_app("sqlite:///" + str(tmp_path / "jobs.db"), PRINCIPALS)
    with TestClient(app) as client:
        assert client.get("/api/execution-options").status_code == 401
        assert client.get("/api/execution-options", headers=auth()).json() == {
            "model": {"enabled": False}
        }
        request = {**body, "execution_mode": "bedrock"}
        assert client.post("/api/jobs", json=request, headers=auth()).status_code == 503
        monkeypatch.setenv("ATLAS_ENABLE_BEDROCK_JOBS", "1")
        options = client.get("/api/execution-options", headers=auth()).json()["model"]
        assert options["enabled"] is True
        assert "profile" not in options
        assert options["maximum_reserved_inference_usd"]
        assert client.post("/api/jobs", json=request, headers=auth()).status_code == 409
        assert (
            client.post(
                "/api/jobs",
                json={**request, "expected_model_config_sha256": "a" * 64},
                headers=auth(),
            ).status_code
            == 409
        )
        assert client.get("/api/jobs", headers=auth()).json() == []
        request["expected_model_config_sha256"] = options["model_config_sha256"]
        response = client.post("/api/jobs", json=request, headers=auth())
        assert response.status_code == 202
        assert response.json()["pipeline_version"] == MODEL_PIPELINE_VERSION
        assert response.json()["max_attempts"] == 1
        assert (
            client.post(
                "/api/jobs", json={**request, "profile": "admin"}, headers=auth()
            ).status_code
            == 422
        )


def test_paid_job_reserves_before_credentials_and_cannot_execute_twice(
    tmp_path, monkeypatch, publication
):
    from datetime import UTC, datetime
    from decimal import Decimal

    import boto3
    from botocore.stub import ANY, Stubber
    from test_model_gateway import response

    from atlas.domain import Document
    from atlas.models.bedrock import BedrockGateway
    from atlas.models.contracts import BedrockConfig
    from atlas.models.intelligence import source_chunks
    from atlas.models.job_task import execute_claim
    from atlas.models.session_budget import initialize

    # Synthetic model identity, prices and SDK stubs; no account or network access.
    monkeypatch.chdir(tmp_path)
    config = BedrockConfig.model_validate(
        {
            "model_id": "synthetic-model",
            "region": "ca-central-1",
            "limits": {
                "max_calls": 2,
                "max_input_tokens": 1000,
                "max_output_tokens": 100,
                "max_reserved_tokens": 2200,
                "max_estimated_cost_usd": "1",
            },
            "price_card": {
                "model_id": "synthetic-model",
                "region": "ca-central-1",
                "input_usd_per_million": "1",
                "output_usd_per_million": "2",
                "verified_on": datetime.now(UTC).date().isoformat(),
                "source": "https://aws.amazon.com/bedrock/pricing/",
            },
        }
    )
    budget = tmp_path / "var" / "budget.json"
    initialize(budget, authorized_usd=Decimal("1"))
    body, _ = publication
    body = {**body, "_model_spec": spec()}
    value = {"tenant": "tenant", "id": "model-job", "input": body}
    document = Document.model_validate(body["rfp"])
    client = boto3.client(
        "bedrock-runtime",
        region_name="ca-central-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
    )
    calls = []

    def factory(cfg, **kwargs):
        import json

        assert json.loads(budget.read_text())["reservations"]
        calls.append(1)
        return BedrockGateway(client, cfg, live=True)

    with Stubber(client) as stub:
        for payload in [
            {
                "requirements": [
                    {
                        "chunk_id": source_chunks(document)[0].id,
                        "quote": document.text,
                        "category": "technical",
                    }
                ]
            },
            {"choice": "supported:e1"},
        ]:
            stub.add_response(
                "count_tokens", {"inputTokens": 20}, {"modelId": "synthetic-model", "input": ANY}
            )
            stub.add_response("converse", response(payload))
        result = execute_claim(
            value, config, session_budget=budget, allow_paid=True, gateway_factory=factory
        )
        assert result["provider"] == "bedrock"
        assert result["assessments"][0]["review_state"] == "pending"
        assert result["model_cost_usd"] > 0
        with pytest.raises(FileExistsError):
            execute_claim(
                value, config, session_budget=budget, allow_paid=True, gateway_factory=factory
            )
        stub.assert_no_pending_responses()
    assert calls == [1]

    def unavailable(cfg, **kwargs):
        raise RuntimeError("private credential details")

    setup_value = {**value, "id": "setup-failed"}
    with pytest.raises(RuntimeError):
        execute_claim(
            setup_value, config, session_budget=budget, allow_paid=True, gateway_factory=unavailable
        )
    import json

    from atlas.execution import fingerprint

    setup_path = (
        tmp_path
        / "var/model-jobs"
        / (fingerprint({"tenant": "tenant", "job": "setup-failed"}) + ".json")
    )
    assert json.loads(setup_path.read_text()) == {
        "status": "failed",
        "phase": "setup",
        "error_code": "provider_setup_failed",
    }
    assert "private" not in setup_path.read_text()
    with pytest.raises(FileExistsError):
        execute_claim(
            setup_value, config, session_budget=budget, allow_paid=True, gateway_factory=factory
        )
    with pytest.raises(ValueError):
        execute_claim(
            {**value, "id": "other"}, config, session_budget=budget, gateway_factory=factory
        )
    assert calls == [1]


def test_model_publication_failure_rolls_back_and_does_not_retry(queue, publication):
    body, report = publication
    job = queue.submit(
        "tenant",
        "analyst",
        "forged-model",
        body,
        pipeline_version=MODEL_PIPELINE_VERSION,
        model_spec=spec(),
    )
    payload = prepare_model_publication(
        {**body, "_model_spec": spec()}, report, estimated_cost_usd=None
    )
    payload["assessments"][0]["review_state"] = "approved"
    assert process_once(queue, model_executor=lambda _: payload)
    assert queue.get("tenant", job["id"])["status"] == "failed"
    assert queue.store.list("tenant") == []
