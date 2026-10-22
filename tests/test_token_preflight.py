"""Retain bounded preflight diagnostics without inference, retries or upstream data."""

import json

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from test_model_gateway import config as config
from test_model_gateway import invoke

from atlas.models.bedrock import BedrockGateway, ProviderFailure, failure_diagnostic


@pytest.mark.parametrize(
    "error,kind,code",
    [
        (
            ClientError(
                {"Error": {"Code": "ThrottlingException", "Message": "secret-contract"}},
                "CountTokens",
            ),
            "service_error",
            "ThrottlingException",
        ),
        (
            ClientError(
                {"Error": {"Code": "secret-contract", "Message": "secret-contract"}}, "CountTokens"
            ),
            "service_error",
            None,
        ),
        (ReadTimeoutError(endpoint_url="https://secret-contract.invalid"), "read_timeout", None),
        (RuntimeError("secret-contract"), "unclassified", None),
    ],
)
def test_failed_preflight_is_recorded_once_without_inference(config, error, kind, code):
    class Client:
        attempts = 0

        def count_tokens(self, **kwargs):
            self.attempts += 1
            raise error

        def converse(self, **kwargs):
            pytest.fail("Inference must not follow a failed preflight")

    client = Client()
    gateway = BedrockGateway(client, config)
    snapshots = []
    gateway.ledger.on_change = snapshots.append
    with pytest.raises(ProviderFailure, match="inference was not sent"):
        invoke(gateway)
    assert client.attempts == 1
    assert len(snapshots) == 1
    diagnostic = snapshots[0]["preflight_failure"]
    assert diagnostic == {
        "failure_kind": kind,
        "provider_error_code": code,
        "inference_sent": False,
    }
    assert snapshots[0]["receipts"] == []
    assert "secret-contract" not in json.dumps(snapshots)
    diagnostic["failure_kind"] = "mutated-copy"
    assert gateway.ledger.report()["preflight_failure"]["failure_kind"] == kind


@pytest.mark.parametrize(
    "response", [{}, {"inputTokens": True}, {"inputTokens": -1}, {"inputTokens": "secret-contract"}]
)
def test_malformed_preflight_has_no_paid_receipt(config, response):
    class Client:
        def count_tokens(self, **kwargs):
            return response

        def converse(self, **kwargs):
            pytest.fail("Malformed preflight must stop before inference")

    gateway = BedrockGateway(Client(), config)
    with pytest.raises(ProviderFailure):
        invoke(gateway)
    report = gateway.ledger.report()
    assert report["receipts"] == []
    assert report["preflight_failure"]["failure_kind"] == "unclassified"
    assert "secret-contract" not in json.dumps(report)


@pytest.mark.parametrize("detail", [{"Code": ["secret-contract"]}, ["secret-contract"]])
def test_malformed_service_code_cannot_escape_the_diagnostic_allowlist(detail):
    error = ClientError({"Error": {}}, "CountTokens")
    error.response = {"Error": detail}
    assert failure_diagnostic(error) == {
        "failure_kind": "service_error",
        "provider_error_code": None,
    }
