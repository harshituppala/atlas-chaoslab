"""Validate authored scenario contracts without importing application models.

A malformed label set is an invalid experiment, not an agent success or failure.
Messages describe the contract field without copying source documents into errors.
"""

RELATIONS = frozenset({"supported", "contradicted", "insufficient"})


def bounded_text(value, maximum, *, empty=False):
    return isinstance(value, str) and (0 if empty else 1) <= len(value) <= maximum


def validate_case(case):
    if not isinstance(case, dict) or not bounded_text(case.get("id"), 128):
        raise ValueError("Invalid scenario identity")
    inputs = case.get("input")
    if not isinstance(inputs, dict) or not isinstance(inputs.get("rfp"), dict):
        raise ValueError("Scenario requires an RFP document")
    knowledge = inputs.get("knowledge")
    if not isinstance(knowledge, list) or len(knowledge) > 100:
        raise ValueError("Scenario knowledge must contain at most 100 documents")
    documents = [inputs["rfp"], *knowledge]
    identifiers = []
    for index, document in enumerate(documents):
        if (
            not isinstance(document, dict)
            or not bounded_text(document.get("id"), 128)
            or not bounded_text(document.get("text"), 100_000)
            or ("kind" in document and document["kind"] != ("rfp" if index == 0 else "knowledge"))
        ):
            raise ValueError("Invalid scenario document identity, text or kind")
        identifiers.append(document["id"])
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Scenario document identities must be unique")
    expectations = case.get("expected")
    if not isinstance(expectations, list) or not 1 <= len(expectations) <= 200:
        raise ValueError("Expected obligations must be nonempty and unique per scenario")
    texts, known = [], set(identifiers[1:])
    for expected in expectations:
        if not isinstance(expected, dict):
            raise ValueError("Invalid expected obligation")
        text, relation, evidence = (
            expected.get(key) for key in ("text", "relation", "evidence_ids")
        )
        if not bounded_text(text, 100_000) or text not in inputs["rfp"]["text"]:
            raise ValueError("Expected obligation must quote the RFP text")
        if not isinstance(relation, str) or relation not in RELATIONS:
            raise ValueError("Invalid expected relation")
        if (
            not isinstance(evidence, list)
            or len(evidence) > len(knowledge)
            or any(
                not isinstance(identifier, str) or identifier not in known
                for identifier in evidence
            )
            or len(set(evidence)) != len(evidence)
        ):
            raise ValueError("Expected evidence must identify unique knowledge documents")
        if (relation == "insufficient") != (len(evidence) == 0):
            raise ValueError("Expected relation and evidence coverage disagree")
        texts.append(text)
    if len(set(texts)) != len(texts):
        raise ValueError("Expected obligations must be nonempty and unique per scenario")


def validate_dataset(dataset):
    if not isinstance(dataset, dict) or not bounded_text(dataset.get("scope"), 4000):
        raise ValueError("Scenario dataset requires a bounded scope")
    if "schema_version" in dataset and (
        type(dataset["schema_version"]) is not int or dataset["schema_version"] != 1
    ):
        raise ValueError("Unsupported scenario schema version")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
        raise ValueError("Comparison requires 1..200 scenarios")
    for case in cases:
        validate_case(case)
    identifiers = [case["id"] for case in cases]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate authored scenario")
