"""Local validation remains authoritative even with provider JSON enforcement."""

from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import combinations
from typing import Literal

from pydantic import AnyHttpUrl, Field, StrictInt, create_model, model_validator

from atlas.domain import StrictModel


class SelectedRequirement(StrictModel):
    chunk_id: str = Field(min_length=1, max_length=64)
    quote: str = Field(min_length=8, max_length=4096)
    category: Literal[
        "security", "technical", "operations", "legal", "commercial", "deadline", "other"
    ]


class Extraction(StrictModel):
    requirements: list[SelectedRequirement] = Field(max_length=500)


class EvidenceDecision(StrictModel):
    relation: Literal["supported", "contradicted", "insufficient"]
    evidence_ids: list[str] = Field(max_length=3)

    @model_validator(mode="after")
    def evidence_relation(self):
        if self.relation == "insufficient" and self.evidence_ids:
            raise ValueError("Insufficient evidence must abstain")
        if self.relation != "insufficient" and not self.evidence_ids:
            raise ValueError("Positive or contradictory decisions require evidence")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Duplicate evidence IDs")
        return self


def evidence_choices(candidate_count: int):
    """Encode only valid relation/citation combinations in the generation schema.

    IDs are allocated by the application, never copied from untrusted source text.
    With at most three candidates this produces at most fifteen choices.
    """
    if type(candidate_count) is not int or not 1 <= candidate_count <= 3:
        raise ValueError("Expected one to three evidence candidates")
    identifiers = [f"e{n + 1}" for n in range(candidate_count)]
    choices = {"insufficient": EvidenceDecision(relation="insufficient", evidence_ids=[])}
    for count in range(1, candidate_count + 1):
        for selected in combinations(identifiers, count):
            for relation in ("supported", "contradicted"):
                choices[f"{relation}:{','.join(selected)}"] = EvidenceDecision(
                    relation=relation, evidence_ids=list(selected)
                )
    schema = create_model(
        "EvidenceChoice",
        __base__=StrictModel,
        choice=(Literal[tuple(choices)], ...),
    )
    return schema, choices


class Usage(StrictModel):
    input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)


class Limits(StrictModel):
    max_calls: int = Field(default=12, ge=1, le=200)
    max_input_tokens: int = Field(default=12000, ge=100, le=100000)
    max_output_tokens: int = Field(default=2048, ge=16, le=8192)
    max_reserved_tokens: int = Field(default=200000, ge=1)
    max_estimated_cost_usd: Decimal = Field(gt=0, le=100)


class PriceCard(StrictModel):
    model_id: str
    region: str
    input_usd_per_million: Decimal = Field(ge=0)
    output_usd_per_million: Decimal = Field(ge=0)
    verified_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source: AnyHttpUrl


class BedrockConfig(StrictModel):
    model_id: str = Field(min_length=1, max_length=256)
    count_tokens_model_id: str | None = Field(default=None, min_length=1, max_length=256)
    region: str = Field(min_length=1, max_length=64)
    profile: str | None = None
    limits: Limits
    price_card: PriceCard

    @model_validator(mode="after")
    def matching_tokenizer(self):
        if self.count_tokens_model_id is not None:
            prefix, _, base = self.model_id.partition(".")
            if prefix not in {"us", "eu", "apac", "au", "jp", "in", "global"} or (
                self.count_tokens_model_id != base
            ):
                raise ValueError(
                    "Token counter must match the inference profile's exact base model"
                )
        return self

    def validate_price_identity(self):
        if self.price_card.model_id != self.model_id or self.price_card.region != self.region:
            raise ValueError("Price card identity does not match the configured model and region")

    def validate_live_price(self):
        self.validate_price_identity()
        card = self.price_card
        age = (datetime.now(UTC).date() - date.fromisoformat(card.verified_on)).days
        if (
            not 0 <= age <= 7
            or card.source.scheme != "https"
            or card.source.host != "aws.amazon.com"
            or card.source.path != "/bedrock/pricing/"
        ):
            raise ValueError(
                "Live execution requires a recently verified official Bedrock price card"
            )
        if card.input_usd_per_million <= 0 or card.output_usd_per_million <= 0:
            raise ValueError(
                "Live execution requires positive base token prices; discounts are not assumed"
            )
