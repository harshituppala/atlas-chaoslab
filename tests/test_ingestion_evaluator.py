import copy
import hashlib

from chaoslab.ingestion import evaluate


def test_independent_scorer_detects_forged_identity_and_page_location():
    raw = b"authored raw source"
    expected = {
        "status": "extracted",
        "format": "pdf",
        "segment_count": 1,
        "locations": [{"quote": "Vendor shall encrypt.", "unit": "page", "number": 2}],
    }
    observed = {
        "status": "extracted",
        "document": {
            "text": "Vendor shall encrypt.",
            "source_map": {
                "format": "pdf",
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "segments": [{"unit": "page", "number": 2, "start": 0, "end": 21}],
            },
        },
    }
    assert all(evaluate(raw, expected, observed).values())
    forged = copy.deepcopy(observed)
    forged["document"]["source_map"]["raw_sha256"] = "0" * 64
    forged["document"]["source_map"]["segments"][0]["number"] = 1
    checks = evaluate(raw, expected, forged)
    assert not checks["raw_identity"] and not checks["authored_location_1"]


def test_rejected_parser_response_cannot_include_partial_document():
    expected = {"status": "rejected", "reason": "extraction_failed"}
    assert not evaluate(b"data", expected, {**expected, "document": {"text": "partial"}})[
        "no_partial_document"
    ]
