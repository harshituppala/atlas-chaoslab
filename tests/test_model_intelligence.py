import pytest

from atlas.domain import Document
from atlas.models.bedrock import InvalidModelOutput
from atlas.models.contracts import EvidenceDecision, Extraction
from atlas.models.intelligence import analyze_model, selected_requirements, source_chunks


def rfp(text):
    return Document(id="rfp", title="Synthetic", kind="rfp", text=text)


def selection(chunk, quote):
    return Extraction.model_validate(
        {"requirements": [{"chunk_id": chunk, "quote": quote, "category": "security"}]}
    )


def test_exact_unicode_quote_is_reconstructed_without_model_offsets():
    document = rfp("Équipe 🧭: The vendor is obligated to support SAML federation.")
    chunks = source_chunks(document)
    selected = selected_requirements(
        document,
        chunks,
        selection(chunks[0].id, "The vendor is obligated to support SAML federation."),
    )
    assert selected[0].source.matches(document)
    assert selected[0].source.start == len("Équipe 🧭: ")


def test_forged_unknown_and_ambiguous_sources_are_rejected():
    document = rfp("The vendor must comply. The vendor must comply.")
    chunks = source_chunks(document)
    with pytest.raises(InvalidModelOutput):
        selected_requirements(document, chunks, selection("invented", "The vendor must comply."))
    with pytest.raises(InvalidModelOutput):
        selected_requirements(document, chunks, selection(chunks[0].id, "The vendor must comply."))
    with pytest.raises(InvalidModelOutput):
        selected_requirements(
            document, chunks, selection(chunks[0].id, "Invented service guarantee.")
        )


def test_model_decisions_are_provisional_and_drafts_stay_extractive():
    document = rfp("The vendor is obligated to support SAML federation.")
    knowledge = [
        Document(
            id="policy", title="Policy", kind="knowledge", text="SAML federation is available."
        )
    ]

    class ScriptedGateway:
        live = False

        def structured(self, *, task, system, data, output):
            if task == "extract_obligations":
                chunk = data["untrusted_document"]["chunks"][0]
                return selection(chunk["chunk_id"], chunk["text"])
            assert "no tools" in system.lower()
            return output(choice="supported:e1")

    report = analyze_model(document, knowledge, ScriptedGateway())
    assert report["live_model"] is False
    assert report["retrieval_method"] == "lexical"
    item = report["assessments"][0]
    assert item["review_state"] == "pending"
    assert item["evidence"][0]["quote"] == knowledge[0].text
    assert item["draft"] == "Evidence excerpts for human assessment:\n" + knowledge[0].text


def test_model_cannot_reference_evidence_outside_retrieval_set():
    document = rfp("The vendor shall implement SAML federation.")
    knowledge = [
        Document(
            id="policy", title="Policy", kind="knowledge", text="SAML federation is available."
        )
    ]

    class ScriptedGateway:
        def structured(self, *, task, system, data, output):
            if task == "extract_obligations":
                chunk = data["untrusted_document"]["chunks"][0]
                return selection(chunk["chunk_id"], chunk["text"])
            from types import SimpleNamespace

            return SimpleNamespace(choice="supported:invented")

    with pytest.raises(InvalidModelOutput):
        analyze_model(document, knowledge, ScriptedGateway())


def test_provisional_support_requires_evidence_and_abstention_does_not_cite():
    with pytest.raises(ValueError):
        EvidenceDecision(relation="supported", evidence_ids=[])
    with pytest.raises(ValueError):
        EvidenceDecision(relation="insufficient", evidence_ids=["e1"])
    with pytest.raises(ValueError):
        EvidenceDecision(relation="supported", evidence_ids=["e1", "e1"])


def test_out_of_scope_retriever_data_is_rejected_before_model_disclosure():
    from types import SimpleNamespace

    from atlas.domain import Citation

    document = rfp("The vendor must provide secure storage.")
    knowledge = [
        Document(id="policy", title="Policy", kind="knowledge", text="Secure storage is available.")
    ]
    other = Document(
        id="foreign", title="Other tenant", kind="knowledge", text="Private foreign data"
    )

    class ForeignRetriever:
        def search(self, *args, **kwargs):
            return [
                SimpleNamespace(
                    source=Citation(
                        document_id=other.id,
                        digest=other.digest,
                        start=0,
                        end=len(other.text),
                        quote=other.text,
                    )
                )
            ]

    calls = []

    class Gateway:
        def structured(self, *, task, system, data, output):
            calls.append(task)
            assert task == "extract_obligations"
            chunk = data["untrusted_document"]["chunks"][0]
            return selection(chunk["chunk_id"], chunk["text"])

    with pytest.raises(InvalidModelOutput):
        analyze_model(document, knowledge, Gateway(), retriever=ForeignRetriever())
    assert calls == ["extract_obligations"]


def test_overlapping_quote_occurrences_are_ambiguous():
    document = rfp("aaaaaaaaa")
    chunks = source_chunks(document)
    with pytest.raises(InvalidModelOutput):
        selected_requirements(document, chunks, selection(chunks[0].id, "aaaaaaaa"))


@pytest.mark.parametrize("candidate_count", [1, 2, 3])
def test_generation_choices_only_encode_valid_scoped_decisions(candidate_count):
    from atlas.models.bedrock import provider_schema
    from atlas.models.contracts import evidence_choices

    schema, choices = evidence_choices(candidate_count)
    published = provider_schema(schema.model_json_schema())
    assert set(published["properties"]["choice"]["enum"]) == set(choices)
    assert len(choices) == 1 + 2 * (2**candidate_count - 1)
    for name, decision in choices.items():
        assert schema.model_validate({"choice": name}).choice == name
        assert EvidenceDecision.model_validate(decision.model_dump()) == decision
        assert set(decision.evidence_ids) <= {f"e{n + 1}" for n in range(candidate_count)}
    for name in ["supported", "supported:e99", "insufficient:e1", "supported:e1,e1"]:
        with pytest.raises(ValueError):
            schema.model_validate({"choice": name})
    with pytest.raises(ValueError):
        schema.model_validate({"choice": "insufficient", "approval": "approved"})


@pytest.mark.parametrize("candidate_count", [0, 4, True, -1])
def test_choice_schema_rejects_invalid_candidate_budgets(candidate_count):
    from atlas.models.contracts import evidence_choices

    with pytest.raises(ValueError):
        evidence_choices(candidate_count)
