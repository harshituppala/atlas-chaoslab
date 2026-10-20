from copy import deepcopy

import pytest
from test_jobs import body as body
from test_jobs import queue as queue
from test_model_jobs import spec
from test_model_publication import publication as publication

from atlas.execution import prepare_model_publication, validate_model_snapshot
from atlas.models.contracts import BedrockConfig
from atlas.models.intelligence import MODEL_PIPELINE_VERSION
from atlas.models.job_spec import ModelJobSpec, job_spec
from atlas.models.job_task import execute_claim
from atlas.store import Conflict


def test_profile_identity_is_excluded_but_execution_settings_are_bound():
    config = BedrockConfig.model_validate({**spec(), "profile": "private-profile"})
    original = job_spec(config)
    assert "profile" not in original.model_dump()
    assert "private" not in original.model_dump_json()
    assert job_spec(config.model_copy(update={"profile": "other"})).digest() == original.digest()
    changed = original.model_dump(mode="json")
    changed["limits"]["max_calls"] += 1
    assert ModelJobSpec.model_validate(changed).digest() != original.digest()
    with pytest.raises(ValueError):
        ModelJobSpec.model_validate({**spec(), "profile": "admin"})


@pytest.mark.parametrize("field", ["model", "region", "limits", "price"])
def test_worker_drift_is_rejected_before_ownership_funding_or_credentials(
    tmp_path, monkeypatch, publication, field
):
    monkeypatch.chdir(tmp_path)
    pinned = spec()
    changed = deepcopy(pinned)
    if field == "model":
        changed["model_id"] = changed["price_card"]["model_id"] = "other-model"
    elif field == "region":
        changed["region"] = changed["price_card"]["region"] = "us-east-1"
    elif field == "limits":
        changed["limits"]["max_calls"] = 3
    else:
        changed["price_card"]["output_usd_per_million"] = "3"
    body, _ = publication
    value = {"tenant": "tenant", "id": "job", "input": {**body, "_model_spec": pinned}}
    with pytest.raises(ValueError, match="pinned job"):
        execute_claim(
            value,
            BedrockConfig.model_validate(changed),
            session_budget=tmp_path / "missing-budget.json",
            allow_paid=True,
            gateway_factory=lambda *a, **k: pytest.fail("Credentials must not be touched"),
        )
    assert not (tmp_path / "var").exists()


def test_changed_spec_conflicts_with_existing_idempotency_key(queue, body):
    queue.submit(
        "tenant",
        "analyst",
        "pinned-job",
        body,
        pipeline_version=MODEL_PIPELINE_VERSION,
        model_spec=spec(),
    )
    changed = spec()
    changed["limits"]["max_calls"] = 3
    with pytest.raises(Conflict):
        queue.submit(
            "tenant",
            "analyst",
            "pinned-job",
            body,
            pipeline_version=MODEL_PIPELINE_VERSION,
            model_spec=changed,
        )


def test_model_persistence_rejects_wrong_configuration_fingerprint(publication):
    body, report = publication
    body = {**body, "_model_spec": spec()}
    payload = prepare_model_publication(body, report, estimated_cost_usd=None)
    assert (
        validate_model_snapshot(body, payload)["model_config_sha256"]
        == ModelJobSpec.model_validate(spec()).digest()
    )
    payload["model_config_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="configuration"):
        validate_model_snapshot(body, payload)


def test_legacy_unpinned_job_status_remains_readable_but_cannot_publish(queue, publication):
    from sqlalchemy import update

    from atlas.jobs import jobs

    body, report = publication
    job = queue.submit(
        "tenant",
        "analyst",
        "legacy-job",
        body,
        pipeline_version=MODEL_PIPELINE_VERSION,
        model_spec=spec(),
    )
    # Recreate a stored pre-pinning job without upgrading its historical evidence.
    with queue.store.engine.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.id == job["id"]).values(input=body))
    assert queue.get("tenant", job["id"])["model_config_sha256"] is None
    claim = queue.claim()
    payload = prepare_model_publication(body, report, estimated_cost_usd=None)
    with pytest.raises(ValueError, match="configuration"):
        queue.complete(claim, payload)
    assert queue.store.list("tenant") == []
