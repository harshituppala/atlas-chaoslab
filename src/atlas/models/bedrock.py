"""Bedrock Converse gateway. No network or credentials are touched on import.

No hidden SDK retries. A failed invocation may still have incurred charges, so its
reserved budget is retained and usage/cost are marked unknown instead of zero.
"""

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Protocol, TypeVar

from pydantic import BaseModel

from atlas.domain import ResourceBudgetExceeded

from .contracts import BedrockConfig, Usage

T = TypeVar("T", bound=BaseModel)


class PaidCallNotAuthorized(Exception):
    pass


class ProviderFailure(Exception):
    pass


class InvalidModelOutput(Exception):
    pass


class StructuredGateway(Protocol):
    def structured(self, *, task: str, system: str, data: dict, output: type[T]) -> T: ...


def provider_schema(schema: dict) -> dict:
    """Remove unsupported generation constraints; retain them in local validation."""
    forbidden = {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "maxItems",
        "pattern",
    }

    def clean(node):
        if isinstance(node, list):
            return [clean(item) for item in node]
        if not isinstance(node, dict):
            return node
        result = {}
        for key, value in node.items():
            if key in forbidden or (key == "minItems" and value not in (0, 1)):
                continue
            if key in {"properties", "$defs", "definitions"}:
                result[key] = {name: clean(child) for name, child in value.items()}
            else:
                result[key] = clean(value)
        return result

    return clean(deepcopy(schema))


@dataclass
class Receipt:
    task: str
    prompt_sha256: str
    schema_sha256: str
    preflight_input_tokens: int
    reserved_input_tokens: int
    reserved_output_tokens: int
    status: str = "reserved"
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: str | None = None
    provider_error_code: str | None = None
    validation_error_code: str | None = None
    invocation_failure_kind: str | None = None


class Ledger:
    def __init__(self, config: BedrockConfig):
        config.validate_price_identity()
        self.config = config
        self.receipts: list[Receipt] = []
        self.on_change = None

    def changed(self):
        if self.on_change is not None:
            self.on_change(self.report())

    def reserve(self, task, prompt, schema, count):
        if type(count) is not int or count < 0:
            raise ProviderFailure("Invalid token preflight response")
        limits = self.config.limits
        tokens = limits.max_input_tokens + limits.max_output_tokens
        price = self.config.price_card
        per_call = (
            Decimal(limits.max_input_tokens) * price.input_usd_per_million
            + Decimal(limits.max_output_tokens) * price.output_usd_per_million
        ) / 1_000_000
        if (
            count > limits.max_input_tokens
            or len(self.receipts) >= limits.max_calls
            or tokens * (len(self.receipts) + 1) > limits.max_reserved_tokens
            or per_call * (len(self.receipts) + 1) > limits.max_estimated_cost_usd
        ):
            raise ResourceBudgetExceeded("Model reservation budget exceeded")
        receipt = Receipt(
            task,
            sha256(prompt.encode()).hexdigest(),
            sha256(schema.encode()).hexdigest(),
            count,
            limits.max_input_tokens,
            limits.max_output_tokens,
        )
        self.receipts.append(receipt)
        self.changed()  # Persist before a possibly billable invocation.
        return receipt

    def observe(self, receipt, raw):
        try:
            usage = Usage(input_tokens=raw["inputTokens"], output_tokens=raw["outputTokens"])
            if raw.get("cacheReadInputTokens", 0) or raw.get("cacheWriteInputTokens", 0):
                raise ValueError("Cache billing is outside this price contract")
        except Exception:
            receipt.status = "usage_unknown"
            self.changed()
            raise ProviderFailure("Model usage could not be verified") from None
        receipt.input_tokens, receipt.output_tokens = usage.input_tokens, usage.output_tokens
        price = self.config.price_card
        receipt.estimated_cost_usd = str(
            (
                Decimal(usage.input_tokens) * price.input_usd_per_million
                + Decimal(usage.output_tokens) * price.output_usd_per_million
            )
            / 1_000_000
        )
        if (
            usage.input_tokens > receipt.reserved_input_tokens
            or usage.output_tokens > receipt.reserved_output_tokens
        ):
            receipt.status = "usage_overrun"
            self.changed()
            raise ResourceBudgetExceeded("Observed model usage exceeded its reservation")
        receipt.status = "received"
        self.changed()

    def report(self):
        known = all(r.estimated_cost_usd is not None for r in self.receipts)
        return {
            "provider": "bedrock",
            "model_id": self.config.model_id,
            "region": self.config.region,
            "price_card": self.config.price_card.model_dump(mode="json"),
            "estimated_model_cost_usd": str(
                sum((Decimal(r.estimated_cost_usd) for r in self.receipts), Decimal(0))
            )
            if known
            else None,
            "cost_is_invoice": False,
            "receipts": [asdict(r) for r in self.receipts],
        }


class BedrockGateway:
    def __init__(self, client, config: BedrockConfig, *, live=False):
        self.client, self.config, self.live = client, config, live
        self.ledger = Ledger(config)

    @classmethod
    def open(cls, config: BedrockConfig, *, allow_paid=False):
        if not allow_paid:
            raise PaidCallNotAuthorized("Live inference requires explicit spending authorization")
        config.validate_live_price()
        import boto3
        from botocore.config import Config

        session = boto3.Session(profile_name=config.profile, region_name=config.region)
        client = session.client(
            "bedrock-runtime",
            config=Config(
                connect_timeout=5,
                read_timeout=90,
                retries={"total_max_attempts": 1},
                max_pool_connections=2,
            ),
        )
        return cls(client, config, live=True)

    def structured(self, *, task, system, data, output):
        prompt = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if len(prompt.encode()) > 400_000:
            raise ResourceBudgetExceeded("Model prompt byte budget exceeded")
        schema = json.dumps(provider_schema(output.model_json_schema()), sort_keys=True)
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        system_blocks = [{"text": system}]
        try:
            count = self.client.count_tokens(
                modelId=self.config.count_tokens_model_id or self.config.model_id,
                input={"converse": {"messages": messages, "system": system_blocks}},
            )["inputTokens"]
        except Exception:
            raise ProviderFailure("Token preflight failed; inference was not sent") from None
        receipt = self.ledger.reserve(
            task,
            json.dumps({"system": system, "data": data}, ensure_ascii=False, sort_keys=True),
            schema,
            count,
        )
        try:
            response = self.client.converse(
                modelId=self.config.model_id,
                messages=messages,
                system=system_blocks,
                inferenceConfig={"maxTokens": self.config.limits.max_output_tokens},
                outputConfig={
                    "textFormat": {
                        "type": "json_schema",
                        "structure": {
                            "jsonSchema": {
                                "schema": schema,
                                "name": task,
                                "description": "Source-constrained document analysis",
                            }
                        },
                    }
                },
            )
        except Exception as exc:
            receipt.status = "invocation_unknown"
            # Never persist arbitrary upstream messages, headers or response bodies.
            from botocore.exceptions import (
                ClientError,
                ConnectionClosedError,
                ConnectTimeoutError,
                EndpointConnectionError,
                ReadTimeoutError,
                SSLError,
            )

            receipt.invocation_failure_kind = "unclassified"
            for error_type, kind in (
                (ClientError, "service_error"),
                (ReadTimeoutError, "read_timeout"),
                (ConnectTimeoutError, "connect_timeout"),
                (ConnectionClosedError, "connection_closed"),
                (SSLError, "tls_error"),
                (EndpointConnectionError, "endpoint_connection"),
            ):
                if isinstance(exc, error_type):
                    receipt.invocation_failure_kind = kind
                    break

            if isinstance(exc, ClientError):
                code = exc.response.get("Error", {}).get("Code")
                if code in {
                    "AccessDeniedException",
                    "ValidationException",
                    "ThrottlingException",
                    "ModelTimeoutException",
                    "ModelNotReadyException",
                    "ServiceUnavailableException",
                    "InternalServerException",
                    "ResourceNotFoundException",
                    "ServiceQuotaExceededException",
                }:
                    receipt.provider_error_code = code
            self.ledger.changed()
            raise ProviderFailure("Invocation failed; usage and cost may be unknown") from None
        self.ledger.observe(receipt, response.get("usage", {}))
        if response.get("stopReason") != "end_turn":
            receipt.status = "incomplete_output"
            self.ledger.changed()
            raise InvalidModelOutput("Model did not finish a complete response")
        try:
            blocks = response["output"]["message"]["content"]
            if not blocks or any(set(block) != {"text"} for block in blocks):
                raise ValueError()
            content = "".join(block["text"] for block in blocks)
            if len(content) > 200_000:
                raise ValueError()
            result = output.model_validate_json(content)
        except Exception as exc:
            receipt.status = "invalid_schema"
            from pydantic import ValidationError

            receipt.validation_error_code = "schema_or_response_shape"
            if isinstance(exc, ValidationError):
                messages = {e["msg"] for e in exc.errors(include_input=False, include_url=False)}
                for message, code in {
                    "Value error, Insufficient evidence must abstain": "abstention_has_evidence",
                    "Value error, Positive or contradictory decisions require evidence": "relation_missing_evidence",
                    "Value error, Duplicate evidence IDs": "duplicate_evidence_ids",
                }.items():
                    if message in messages:
                        receipt.validation_error_code = code
            self.ledger.changed()
            raise InvalidModelOutput("Model output failed local validation") from None
        receipt.status = "validated"
        self.ledger.changed()
        return result
