"""Versioned execution contract shared by the API and durable worker."""

import hashlib
import json

from pydantic import Field

from .domain import Assessment, Document, StrictModel, extractive_draft
from .workflow import analyze

PIPELINE_VERSION = "extractive-v3"


def fingerprint(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def execute(body: dict) -> dict:
    rfp = Document.model_validate(body["rfp"])
    knowledge = [Document.model_validate(d) for d in body["knowledge"]]
    state = analyze(rfp, knowledge)
    return {
        "documents": [d.model_dump() for d in [rfp, *knowledge]],
        "assessments": [a.model_dump() for a in state["assessments"]],
        "trace": state["trace"],
        "provider": "extractive-baseline",
        "pipeline_version": PIPELINE_VERSION,
        "model_cost_usd": 0,
        "limitations": "Lexical retrieval and mandatory-line extraction. Evidence found is not verified compliance. Human review required.",
    }


class AnalysisPayload(StrictModel):
    documents: list[Document]
    assessments: list[Assessment]
    trace: list[dict]
    provider: str
    pipeline_version: str
    model_cost_usd: float = Field(ge=0, allow_inf_nan=False)
    limitations: str


def validate_publication(body, payload):
    """Validate even trusted worker outputs at the persistence trust boundary."""
    checked = AnalysisPayload.model_validate(payload)
    expected = [Document.model_validate(d).model_dump() for d in [body["rfp"], *body["knowledge"]]]
    if [d.model_dump() for d in checked.documents] != expected:
        raise ValueError("Result source snapshot differs from submitted input")
    if checked.pipeline_version != PIPELINE_VERSION:
        raise ValueError("Result pipeline version differs from worker version")
    if checked.provider != "extractive-baseline" or checked.model_cost_usd != 0:
        raise ValueError("Provider metadata differs from the configured baseline")
    validate_sources(body, checked)
    return checked.model_dump()


def validate_sources(body, checked):
    """Shared citation and review invariants for every execution backend."""
    documents = {d.id: d for d in checked.documents}
    identifiers = set()
    for item in checked.assessments:
        if item.requirement.id in identifiers:
            raise ValueError("Duplicate requirement ID")
        identifiers.add(item.requirement.id)
        source = item.requirement.source
        if item.requirement.text != source.quote or item.draft != extractive_draft(item.evidence):
            raise ValueError("Baseline output includes unsupported generated text")
        if source.document_id != body["rfp"]["id"] or not source.matches(
            documents[source.document_id]
        ):
            raise ValueError("Invalid requirement provenance")
        for citation in item.evidence:
            document = documents.get(citation.document_id)
            if document is None or document.kind != "knowledge" or not citation.matches(document):
                raise ValueError("Invalid evidence provenance")
        if item.review_state != "pending" or item.version != 1:
            raise ValueError("Worker cannot approve its own result")


class ModelAnalysisPayload(AnalysisPayload):
    model_config_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    model_cost_usd: float | None = Field(ge=0, allow_inf_nan=False)


def prepare_model_publication(body, report, *, estimated_cost_usd):
    """Prepare a source-checked provisional result; does not enable API inference.

    Cost is supplied by the worker's usage ledger, never by generated model text.
    Unknown cost stays null. Baseline publication remains a separate strict gate.
    """
    from .models.intelligence import MODEL_PIPELINE_VERSION

    if (
        report.get("pipeline_version") != MODEL_PIPELINE_VERSION
        or report.get("live_model") is not True
    ):
        raise ValueError("Unexpected model execution identity")
    checked = ModelAnalysisPayload.model_validate(
        {
            "documents": report["documents"],
            "assessments": report["assessments"],
            "trace": [{"stage": "model_publication", "citations_valid": True}],
            "provider": "bedrock",
            "pipeline_version": MODEL_PIPELINE_VERSION,
            "model_cost_usd": estimated_cost_usd,
            "model_config_sha256": model_spec_digest(body),
            "limitations": "Provisional model assessment requiring human review. Exact citations do not establish factual correctness. Model cost is an estimate, not an invoice; null means unknown.",
        }
    )
    expected = [Document.model_validate(d).model_dump() for d in [body["rfp"], *body["knowledge"]]]
    if [d.model_dump() for d in checked.documents] != expected:
        raise ValueError("Result source snapshot differs from submitted input")
    validate_sources(body, checked)
    relations = report.get("provisional_relations")
    if not isinstance(relations, dict) or set(relations) != {
        a.requirement.id for a in checked.assessments
    }:
        raise ValueError("Model relation coverage differs from assessments")
    expected_status = {
        "supported": "evidence_found",
        "contradicted": "conflicting_evidence",
        "insufficient": "missing_evidence",
    }
    for item in checked.assessments:
        relation = relations[item.requirement.id]
        if not isinstance(relation, str) or expected_status.get(relation) != item.status:
            raise ValueError("Model relation and assessment disagree")
        if (relation == "insufficient") != (not item.evidence):
            raise ValueError("Model relation violates the evidence contract")
    return checked.model_dump()


def model_spec_digest(body):
    if "_model_spec" not in body:
        return None
    from .models.job_spec import ModelJobSpec

    return ModelJobSpec.model_validate(body["_model_spec"]).digest()


def validate_model_snapshot(body, payload):
    """Persistence gate selected by the stored job identity, never its output."""
    from .models.intelligence import MODEL_PIPELINE_VERSION

    checked = ModelAnalysisPayload.model_validate(payload)
    expected_spec = model_spec_digest(body)
    if expected_spec is None or checked.model_config_sha256 != expected_spec:
        raise ValueError("Model result configuration differs from the stored job")
    if checked.provider != "bedrock" or checked.pipeline_version != MODEL_PIPELINE_VERSION:
        raise ValueError("Model publication identity differs from the stored job")
    expected = [Document.model_validate(d).model_dump() for d in [body["rfp"], *body["knowledge"]]]
    if [d.model_dump() for d in checked.documents] != expected:
        raise ValueError("Result source snapshot differs from submitted input")
    validate_sources(body, checked)
    for item in checked.assessments:
        if item.status not in {"evidence_found", "conflicting_evidence", "missing_evidence"}:
            raise ValueError("Unknown model assessment status")
        if (item.status == "missing_evidence") != (not item.evidence):
            raise ValueError("Model evidence status is inconsistent")
    if checked.trace != [{"stage": "model_publication", "citations_valid": True}]:
        raise ValueError("Unexpected model publication trace")
    return checked.model_dump()
