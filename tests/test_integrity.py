from atlas.domain import Document
from atlas.workflow import analyze, extract
from chaoslab.__main__ import citation_valid, wilson


def test_unicode_offsets_and_digest():
    doc = Document(
        id="a", title="a", kind="rfp", text="Équipe 🧭\nThe vendor must store data in Canada."
    )
    req = extract(doc)[0]
    assert req.source.matches(doc)
    assert citation_valid(req.source.model_dump(), {"a": doc.model_dump()})
    changed = doc.model_copy(update={"text": doc.text.replace("Canada", "Europe")})
    assert not req.source.matches(changed)


def test_empty_retrieval_abstains():
    rfp = Document(id="r", title="r", kind="rfp", text="Vendor must implement SAML federation.")
    doc = Document(id="p", title="p", kind="knowledge", text="Lunch is served at noon.")
    item = analyze(rfp, [doc])["assessments"][0]
    assert item.status == "missing_evidence"
    assert not item.evidence
    assert item.review_state == "pending"


def test_timeout_retries_are_bounded():
    calls = []

    def timeout(query):
        calls.append(query)
        raise TimeoutError()

    rfp = Document(id="r", title="r", kind="rfp", text="Vendor must implement SAML federation.")
    doc = Document(id="p", title="p", kind="knowledge", text="SAML federation enabled.")
    output = analyze(rfp, [doc], timeout)
    assert len(calls) == 2
    assert output["assessments"][0].status == "missing_evidence"


def test_integrity_scorer_rejects_forged_citation():
    assert not citation_valid({"document_id": "missing"}, {})
    assert wilson(0, 0) is None
    assert wilson(1, 1)[0] < 1
