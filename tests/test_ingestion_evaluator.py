import copy
import hashlib

import pytest

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


def repeated_source():
    text = "Repeated footer\nRepeated footer"
    return {
        "status": "extracted",
        "document": {
            "text": text,
            "source_map": {
                "format": "pdf",
                "raw_sha256": hashlib.sha256(b"raw").hexdigest(),
                "segments": [
                    {"unit": "page", "number": 1, "start": 0, "end": 15},
                    {"unit": "page", "number": 3, "start": 16, "end": 31},
                ],
            },
        },
    }


def repeated_expected():
    return {
        "status": "extracted",
        "format": "pdf",
        "segment_count": 2,
        "locations": [{"quote": "Repeated footer", "unit": "page", "number": 3}],
    }


def test_repeated_text_is_found_on_the_authored_page_after_a_blank_page():
    assert all(evaluate(b"raw", repeated_expected(), repeated_source()).values())


def test_repeated_quote_on_another_page_does_not_satisfy_the_authored_location():
    observed = repeated_source()
    observed["document"]["source_map"]["segments"][1]["number"] = 2
    assert not evaluate(b"raw", repeated_expected(), observed)["authored_location_1"]


def test_quote_cannot_cross_a_segment_boundary():
    expected = repeated_expected()
    expected["locations"][0]["quote"] = "footer\nRepeated"
    assert not evaluate(b"raw", expected, repeated_source())["authored_location_1"]


def test_exact_authored_text_detects_an_extra_deleted_revision():
    expected = repeated_expected()
    expected["text"] = "Repeated footer\nRepeated footer"
    observed = repeated_source()
    assert evaluate(b"raw", expected, observed)["authored_text"]
    observed["document"]["text"] += "\nDeleted target: one hour."
    assert not evaluate(b"raw", expected, observed)["authored_text"]


def test_malformed_segment_bounds_fail_location_without_slicing_errors():
    observed = repeated_source()
    observed["document"]["source_map"]["segments"][1]["start"] = "not an offset"
    checks = evaluate(b"raw", repeated_expected(), observed)
    assert not checks["source_map_coverage"] and not checks["authored_location_1"]


@pytest.mark.parametrize("changed", ["dataset", "fixture", "source"])
def test_changed_inputs_refuse_report_publication(tmp_path, monkeypatch, changed):
    import json
    from types import SimpleNamespace

    from chaoslab import ingestion

    fixture = tmp_path / "fixture.pdf"
    fixture.write_bytes(b"original fixture")
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "scope": "Mutation check",
                "cases": [
                    {
                        "id": "rejected",
                        "input": {"file": "fixture.pdf", "format": "pdf", "kind": "rfp"},
                        "expected": {"status": "rejected", "reason": "extraction_failed"},
                    }
                ],
            }
        )
    )
    output = tmp_path / "result.json"
    output.write_text("previous report")

    def adapter(_):
        if changed == "dataset":
            dataset.write_text("changed dataset")
        elif changed == "fixture":
            fixture.write_bytes(b"changed fixture")
        return {"status": "rejected", "reason": "extraction_failed"}

    digests = iter(["before", "after" if changed == "source" else "before"])
    monkeypatch.setattr(ingestion, "source_digest", lambda: next(digests))
    monkeypatch.setattr(
        ingestion,
        "importlib",
        SimpleNamespace(import_module=lambda _: SimpleNamespace(run=adapter)),
    )
    monkeypatch.setattr(
        "sys.argv", ["ingestion", "--dataset", str(dataset), "--output", str(output)]
    )
    with pytest.raises(SystemExit, match="publication refused"):
        ingestion.main()
    assert output.read_text() == "previous report"


def test_report_cannot_overwrite_an_ingestion_fixture(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from chaoslab import ingestion

    fixture = tmp_path / "fixture.pdf"
    fixture.write_bytes(b"original fixture")
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "scope": "Output boundary",
                "cases": [
                    {
                        "id": "one",
                        "input": {"file": "fixture.pdf", "format": "pdf", "kind": "rfp"},
                        "expected": {"status": "rejected", "reason": "extraction_failed"},
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(
        ingestion,
        "importlib",
        SimpleNamespace(
            import_module=lambda _: SimpleNamespace(
                run=lambda _: pytest.fail("Adapter should not run")
            )
        ),
    )
    monkeypatch.setattr(
        "sys.argv", ["ingestion", "--dataset", str(dataset), "--output", str(fixture)]
    )
    with pytest.raises(SystemExit) as caught:
        ingestion.main()
    assert caught.value.code == 2
    assert fixture.read_bytes() == b"original fixture"
