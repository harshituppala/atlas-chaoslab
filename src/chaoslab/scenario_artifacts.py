"""Structural admission for saved scenario observations, separate from quality scoring.

Wrong claims, citations and review decisions remain scoreable failures. Missing
containers and unusable field types are invalid experiments, with opaque errors.
"""

from .datasets import bounded_text


def citation_shape(value):
    if (
        not isinstance(value, dict)
        or not bounded_text(value.get("document_id"), 128)
        or not bounded_text(value.get("digest"), 128)
        or not bounded_text(value.get("quote"), 100_000, empty=True)
        or type(value.get("start")) is not int
        or type(value.get("end")) is not int
    ):
        raise ValueError("Invalid scenario citation structure")


def validate_output(output):
    if not isinstance(output, dict):
        raise ValueError("Scenario output must be an object")
    documents = output.get("documents")
    items = output.get("assessments")
    if (
        not isinstance(documents, list)
        or len(documents) > 101
        or any(
            not isinstance(document, dict)
            or not bounded_text(document.get("id"), 128)
            or not bounded_text(document.get("text"), 100_000)
            for document in documents
        )
    ):
        raise ValueError("Invalid scenario source snapshot structure")
    if not isinstance(items, list) or len(items) > 1000:
        raise ValueError("Scenario assessments must be a list of at most 1000 entries")
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("requirement"), dict):
            raise ValueError("Invalid scenario assessment structure")
        requirement = item["requirement"]
        if (
            not bounded_text(requirement.get("id"), 128)
            or not bounded_text(requirement.get("text"), 100_000)
            or not bounded_text(item.get("status"), 128)
            or not bounded_text(item.get("draft"), 1_000_000, empty=True)
        ):
            raise ValueError("Invalid scenario assessment fields")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or len(evidence) > 1000:
            raise ValueError("Scenario evidence must be a list of at most 1000 citations")
        citation_shape(requirement.get("source"))
        for citation in evidence:
            citation_shape(citation)


def validate_bundle(bundle, maximum_rows):
    if not isinstance(bundle, dict):
        raise ValueError("Scenario artifact must be an object")
    rows = bundle.get("results")
    if not isinstance(rows, list) or len(rows) > maximum_rows:
        raise ValueError("Invalid scenario result coverage")
    if not bounded_text(bundle.get("dataset_sha256"), 128):
        raise ValueError("Invalid scenario dataset identity")
    for row in rows:
        if (
            not isinstance(row, dict)
            or not bounded_text(row.get("id"), 128)
            or not bounded_text(row.get("input_sha256"), 128)
            or row.get("status") not in ("succeeded", "failed")
        ):
            raise ValueError("Invalid scenario result structure")
        if row["status"] == "succeeded":
            validate_output(row.get("output"))
