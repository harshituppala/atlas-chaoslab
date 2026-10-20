"""Immutable source references; offsets count Unicode characters, not bytes."""

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def valid_unicode(cls, value):
        # JSON permits escaped unpaired surrogates; UTF-8 storage and hashing do not.
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, (list, tuple)):
                pending.extend(item)
                continue
            if not isinstance(item, str):
                continue
            try:
                item.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("Text must contain valid Unicode scalar values") from None
        return value


class SourceSegment(StrictModel):
    unit: Literal["page", "paragraph"]
    number: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class SourceMap(StrictModel):
    format: Literal["pdf", "docx"]
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parser_version: str = Field(min_length=1, max_length=64)
    segments: list[SourceSegment] = Field(min_length=1, max_length=2000)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class Document(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100_000)
    kind: Literal["rfp", "knowledge"]
    source_map: SourceMap | None = None

    @model_validator(mode="after")
    def validate_source_map(self):
        if self.source_map is None:
            return self
        previous_end, previous_number = 0, 0
        expected_unit = "page" if self.source_map.format == "pdf" else "paragraph"
        for segment in self.source_map.segments:
            if (
                segment.unit != expected_unit
                or segment.number <= previous_number
                or not previous_end <= segment.start < segment.end <= len(self.text)
                or self.text[previous_end : segment.start].strip()
            ):
                raise ValueError("Source map does not match canonical text")
            previous_end, previous_number = segment.end, segment.number
        if self.text[previous_end:].strip():
            raise ValueError("Source map leaves unmapped text")
        return self

    @property
    def digest(self) -> str:
        return sha256(self.text.encode()).hexdigest()


class Citation(StrictModel):
    document_id: str
    digest: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)

    def matches(self, document: Document) -> bool:
        return (
            self.document_id == document.id
            and self.digest == document.digest
            and self.start < self.end <= len(document.text)
            and document.text[self.start : self.end] == self.quote
        )


class Requirement(StrictModel):
    id: str
    text: str
    category: str
    source: Citation


class Assessment(StrictModel):
    requirement: Requirement
    status: Literal["evidence_found", "conflicting_evidence", "missing_evidence"]
    evidence: list[Citation]
    draft: str
    review_state: Literal["pending", "approved", "rejected"] = "pending"
    version: int = 1

    @model_validator(mode="after")
    def consistent(self):
        if self.status != "missing_evidence" and not self.evidence:
            raise ValueError("Evidence is required for a supported assessment")
        if self.status == "missing_evidence" and self.evidence:
            raise ValueError("Missing evidence must not contain citations")
        return self


class ResourceBudgetExceeded(Exception):
    """The deterministic pipeline refused an input exceeding its work budget."""


def extractive_draft(evidence: list[Citation]) -> str:
    if evidence:
        return "Evidence excerpts for human assessment:\n" + "\n".join(c.quote for c in evidence)
    return "No supporting evidence located. A reviewer must obtain evidence before responding."
