import io
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from defusedxml.common import DefusedXmlException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from sqlalchemy import select

from atlas.api import create_app
from atlas.documents import DocumentStore, quotas
from atlas.domain import Citation, Document, ResourceBudgetExceeded
from atlas.execution import execute, validate_publication
from atlas.ingestion import (
    ExtractionFailed,
    UnsupportedDocument,
    extract_document,
    extract_isolated,
)
from atlas.store import Store

PRINCIPALS = {
    "owner": {"tenant": "a", "actor": "alice", "role": "analyst"},
    "other": {"tenant": "b", "actor": "bob", "role": "analyst"},
    "viewer": {"tenant": "a", "actor": "carol", "role": "viewer"},
}


def auth(token="owner"):
    return {"Authorization": "Bearer " + token}


@pytest.fixture
def raw_pdf():
    return Path("datasets/documents/municipal-rfp.pdf").read_bytes()


@pytest.fixture
def raw_docx():
    return Path("datasets/documents/capability-register.docx").read_bytes()


def mutated_docx(raw, entries):
    target = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(raw)) as original,
        zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as result,
    ):
        for name in original.namelist():
            result.writestr(name, entries.get(name, original.read(name)))
        for name, content in entries.items():
            if name not in original.namelist():
                result.writestr(name, content)
    return target.getvalue()


def test_real_pdf_pages_and_docx_unicode_locations(raw_pdf, raw_docx):
    rfp = extract_isolated(raw_pdf, "pdf", "RFP", "rfp")
    knowledge = extract_isolated(raw_docx, "docx", "Knowledge", "knowledge")
    assert rfp.source_map.raw_sha256 == sha256(raw_pdf).hexdigest()
    assert [s.number for s in rfp.source_map.segments] == [1, 2]
    assert "Café" in knowledge.text
    assert "only guaranteed within 8 hours" in knowledge.text
    payload = execute({"rfp": rfp.model_dump(), "knowledge": [knowledge.model_dump()]})
    assert len(payload["assessments"]) == 7
    second_page = next(
        a for a in payload["assessments"] if "Recovery time" in a["requirement"]["text"]
    )
    citation = Citation.model_validate(second_page["requirement"]["source"])
    assert citation.matches(rfp)
    assert (
        rfp.source_map.segments[1].start
        <= citation.start
        < citation.end
        <= rfp.source_map.segments[1].end
    )
    validate_publication({"rfp": rfp.model_dump(), "knowledge": [knowledge.model_dump()]}, payload)


def test_no_text_encrypted_and_malformed_pdfs_fail_safely(raw_pdf):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    target = io.BytesIO()
    writer.write(target)
    with pytest.raises(UnsupportedDocument, match="OCR"):
        extract_isolated(target.getvalue(), "pdf", "Scanned", "rfp")
    encrypted = PdfWriter(io.BytesIO(raw_pdf))
    encrypted.encrypt("private-password")
    target = io.BytesIO()
    encrypted.write(target)
    with pytest.raises(UnsupportedDocument, match="Encrypted"):
        extract_isolated(target.getvalue(), "pdf", "Encrypted", "rfp")
    with pytest.raises(ExtractionFailed) as error:
        extract_isolated(b"%PDF-private-document-content", "pdf", "Malformed", "rfp")
    assert "private-document" not in str(error.value)


def test_bounded_subprocess_and_file_bytes(raw_pdf):
    with pytest.raises(ExtractionFailed, match="deadline"):
        extract_isolated(raw_pdf, "pdf", "Timeout", "rfp", timeout_seconds=0.0001)
    with pytest.raises(ResourceBudgetExceeded):
        extract_isolated(b"x" * 1_000_001, "pdf", "Huge", "rfp")


def test_pdf_compression_bomb_hits_decoder_limit_before_text_extraction():
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    stream = DecodedStreamObject()
    stream.set_data(b"x" * 10_000_001)
    page[NameObject("/Contents")] = writer._add_object(stream.flate_encode())
    target = io.BytesIO()
    writer.write(target)
    assert len(target.getvalue()) < 100_000
    with pytest.raises(ResourceBudgetExceeded):
        extract_isolated(target.getvalue(), "pdf", "Compressed", "rfp")


def test_docx_dtd_entities_bombs_macros_and_paths(raw_docx):
    entity = b'<!DOCTYPE document [<!ENTITY payload "private">]><document>&payload;</document>'
    with pytest.raises(DefusedXmlException):
        extract_document(
            mutated_docx(raw_docx, {"word/document.xml": entity}), "docx", "Entity", "rfp"
        )
    with pytest.raises(ResourceBudgetExceeded):
        extract_document(
            mutated_docx(raw_docx, {"word/huge.xml": "x" * 1_000_000}), "docx", "Bomb", "rfp"
        )
    with pytest.raises(UnsupportedDocument, match="Unsafe"):
        extract_document(mutated_docx(raw_docx, {"../outside": "data"}), "docx", "Path", "rfp")
    macro = '<Types><Override PartName="/word/document.xml" ContentType="application/vnd.ms-word.document.macroEnabled.main+xml"/></Types>'
    with pytest.raises(UnsupportedDocument):
        extract_document(
            mutated_docx(raw_docx, {"[Content_Types].xml": macro}), "docx", "Macro", "rfp"
        )


def test_docx_tabs_breaks_and_revision_reading_policy(raw_docx):
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Café</w:t><w:tab/><w:t>team</w:t><w:br/><w:t>shall review.</w:t></w:r><w:del><w:r><w:delText>deleted secret</w:delText></w:r></w:del></w:p></w:body></w:document>'
    document = extract_document(
        mutated_docx(raw_docx, {"word/document.xml": xml}), "docx", "Unicode", "rfp"
    )
    assert document.text == "Café\tteam\nshall review."
    corrupted = document.model_dump()
    corrupted["source_map"]["segments"][0]["end"] = 1
    with pytest.raises(ValidationError):
        Document.model_validate(corrupted)


def test_upload_isolation_dedup_original_and_job_tamper_guard(tmp_path, raw_pdf, raw_docx):
    url = "sqlite:///" + str(tmp_path / "uploads.db")
    with TestClient(create_app(url, PRINCIPALS)) as client:
        params = {"format": "pdf", "kind": "rfp", "title": "RFP"}
        assert client.post("/api/documents", params=params, content=raw_pdf).status_code == 401
        assert (
            client.post(
                "/api/documents", params=params, content=raw_pdf, headers=auth("viewer")
            ).status_code
            == 403
        )
        rfp_response = client.post("/api/documents", params=params, content=raw_pdf, headers=auth())
        assert rfp_response.status_code == 201
        rfp = rfp_response.json()
        params["title"] = "Different filename, identical source"
        assert (
            client.post("/api/documents", params=params, content=raw_pdf, headers=auth()).json()
            == rfp
        )
        assert len(client.get("/api/documents", headers=auth()).json()) == 1
        assert client.get("/api/documents", headers=auth("other")).json() == []
        assert client.get("/api/documents/" + rfp["id"], headers=auth("other")).status_code == 404
        original_url = "/api/documents/" + rfp["id"] + "/original"
        assert client.get(original_url, headers=auth("other")).status_code == 404
        original = client.get(original_url, headers=auth())
        assert (
            original.content == raw_pdf and original.headers["x-content-type-options"] == "nosniff"
        )
        knowledge = client.post(
            "/api/documents",
            params={"format": "docx", "kind": "knowledge", "title": "Capabilities"},
            content=raw_docx,
            headers=auth(),
        ).json()
        body = {"rfp": rfp, "knowledge": [knowledge]}
        headers = {**auth(), "Idempotency-Key": "upload-job-0001"}
        assert client.post("/api/jobs", json=body, headers=headers).status_code == 202
        altered = deepcopy(body)
        altered["rfp"]["text"] = altered["rfp"]["text"].replace("Canada", "France")
        assert client.post("/api/jobs", json=altered, headers=headers).status_code == 409
        altered["rfp"].pop("source_map")
        assert client.post("/api/jobs", json=altered, headers=headers).status_code == 409
        assert (
            client.post(
                "/api/jobs",
                json=body,
                headers={**auth("other"), "Idempotency-Key": "other-upload-job"},
            ).status_code
            == 404
        )
    with TestClient(create_app(url, PRINCIPALS)) as reopened:
        assert reopened.get("/api/documents/" + rfp["id"], headers=auth()).json() == rfp


def test_atomic_storage_quota_and_duplicate_rollback(tmp_path, raw_pdf):
    store = Store("sqlite:///" + str(tmp_path / "quota.db"))
    documents = DocumentStore(store, maximum_bytes=len(raw_pdf), maximum_count=1)
    document = extract_document(raw_pdf, "pdf", "Fixture", "rfp")
    with ThreadPoolExecutor(max_workers=4) as pool:
        saved = list(pool.map(lambda _: documents.save("a", "alice", document, raw_pdf), range(4)))
    assert all(d == document for d in saved)
    with store.engine.connect() as connection:
        row = connection.execute(select(quotas)).mappings().one()
        assert row["bytes"] == len(raw_pdf) and row["count"] == 1
    other = document.model_copy(update={"id": "other"})
    with pytest.raises(ResourceBudgetExceeded):
        documents.save("a", "alice", other, raw_pdf)
    assert len(documents.list("a")) == 1


def test_busy_ingestion_rejects_before_parsing_and_releases_on_failure(tmp_path, raw_pdf):
    app = create_app("sqlite:///" + str(tmp_path / "admission.db"), PRINCIPALS)
    params = {"format": "pdf", "kind": "rfp", "title": "RFP"}
    with TestClient(app) as client:
        slots = app.state.ingestion_slots
        assert slots.acquire(False) and slots.acquire(False)
        response = client.post("/api/documents", params=params, content=raw_pdf, headers=auth())
        assert response.status_code == 429 and response.headers["retry-after"] == "2"
        slots.release()
        slots.release()
        assert (
            client.post("/api/documents", params=params, content=b"bad", headers=auth()).status_code
            == 422
        )
        assert slots.acquire(False) and slots.acquire(False)
        slots.release()
        slots.release()


def test_seed_documents_regenerate_byte_identically(tmp_path):
    target = tmp_path / "fixtures"
    command = [sys.executable, "scripts/seed_documents.py", "--output", str(target)]
    subprocess.run(command, check=True, capture_output=True, timeout=10)
    first = {p.name: p.read_bytes() for p in target.iterdir()}
    subprocess.run(command, check=True, capture_output=True, timeout=10)
    assert first == {p.name: p.read_bytes() for p in target.iterdir()}


def test_duplicate_upload_bypasses_parser_and_preserves_declared_format(
    tmp_path, raw_pdf, monkeypatch
):
    app = create_app("sqlite:///" + str(tmp_path / "dedup.db"), PRINCIPALS)
    params = {"format": "pdf", "kind": "rfp", "title": "RFP"}
    with TestClient(app) as client:
        first = client.post("/api/documents", params=params, content=raw_pdf, headers=auth()).json()
        monkeypatch.setattr(
            "atlas.api.extract_isolated", lambda *_: pytest.fail("Duplicate upload reached parser")
        )
        assert (
            client.post("/api/documents", params=params, content=raw_pdf, headers=auth()).json()
            == first
        )
        assert (
            client.post(
                "/api/documents",
                params={**params, "format": "docx"},
                content=raw_pdf,
                headers=auth(),
            ).status_code
            == 422
        )
