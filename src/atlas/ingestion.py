"""Bounded text extraction. Source coordinates refer to canonical extracted text.

No OCR, rendering, network fetches, macros or field evaluation are performed.
Parsing runs in a separate trusted process with a hard wall-clock deadline.
"""

import base64
import io
import json
import subprocess
import sys
import zipfile
from hashlib import sha256

from defusedxml.ElementTree import fromstring

from .domain import Document, ResourceBudgetExceeded, SourceMap, SourceSegment

PARSER_VERSION = "document-text-v1"
MAX_FILE_BYTES = 1_000_000
MAX_UNPACKED_BYTES = 10_000_000
MAX_TEXT_CHARS = 100_000
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class UnsupportedDocument(Exception):
    pass


class ExtractionFailed(Exception):
    pass


def document_id(raw, kind):
    return "upload-" + sha256(PARSER_VERSION.encode() + kind.encode() + raw).hexdigest()


def assemble(parts, raw, format, title, kind, warnings=()):
    text, segments, offset = [], [], 0
    for number, part in parts:
        # Preserve extracted Unicode and in-paragraph whitespace; normalize only CRs.
        part = part.replace("\r\n", "\n").replace("\r", "\n")
        if not part.strip():
            continue
        if offset:
            text.append("\n")
            offset += 1
        if offset + len(part) > MAX_TEXT_CHARS:
            raise ResourceBudgetExceeded("Extracted text exceeds its character budget")
        segments.append(
            SourceSegment(
                unit="page" if format == "pdf" else "paragraph",
                number=number,
                start=offset,
                end=offset + len(part),
            )
        )
        text.append(part)
        offset += len(part)
    if not text:
        raise UnsupportedDocument("No extractable text; scanned PDFs require OCR")
    return Document(
        id=document_id(raw, kind),
        title=title,
        kind=kind,
        text="".join(text),
        source_map=SourceMap(
            format=format,
            raw_sha256=sha256(raw).hexdigest(),
            parser_version=PARSER_VERSION,
            segments=segments,
            warnings=list(warnings),
        ),
    )


def extract_pdf(raw, title, kind):
    from pypdf import PdfReader

    if not raw.startswith(b"%PDF-"):
        raise UnsupportedDocument("The upload is not a PDF")
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted:
        raise UnsupportedDocument("Encrypted PDFs are not supported")
    if len(reader.pages) > 100:
        raise ResourceBudgetExceeded("PDF page budget exceeded")
    parts, decoded_bytes, blank_pages = [], 0, 0
    for number, page in enumerate(reader.pages, 1):
        contents = page.get_contents()
        # Checking decoded length can itself allocate; process limits bound that operation.
        decoded_bytes += len(contents.get_data()) if contents is not None else 0
        if decoded_bytes > MAX_UNPACKED_BYTES:
            raise ResourceBudgetExceeded("PDF decoded-content budget exceeded")
        text = page.extract_text() or ""
        if not text.strip():
            blank_pages += 1
        parts.append((number, text))
        if sum(len(part) for _, part in parts) > MAX_TEXT_CHARS:
            raise ResourceBudgetExceeded("PDF text budget exceeded")
    warnings = ["PDF reading order and tables require source review; no OCR was performed."]
    if blank_pages:
        warnings.append(f"{blank_pages} pages had no extractable text and may require OCR.")
    return assemble(parts, raw, "pdf", title, kind, warnings)


def paragraph_text(paragraph):
    pieces = []

    def visit(node):
        # Deleted revisions and text boxes are excluded from the main-body reading order.
        if node.tag in {W + "del", W + "txbxContent"}:
            return
        if node.tag == W + "t":
            pieces.append(node.text or "")
        elif node.tag == W + "tab":
            pieces.append("\t")
        elif node.tag in {W + "br", W + "cr"}:
            pieces.append("\n")
        for child in node:
            visit(child)

    visit(paragraph)
    return "".join(pieces)


def extract_docx(raw, title, kind):
    if not raw.startswith(b"PK\x03\x04"):
        raise UnsupportedDocument("The upload is not a DOCX archive")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(infos) > 200 or len(names) != len(set(names)):
            raise ResourceBudgetExceeded("DOCX entry count or duplicate-name budget exceeded")
        if sum(item.file_size for item in infos) > MAX_UNPACKED_BYTES:
            raise ResourceBudgetExceeded("DOCX decompression budget exceeded")
        for item in infos:
            if (
                item.flag_bits & 1
                or item.file_size > 3_000_000
                or item.file_size > max(1, item.compress_size) * 100
            ):
                raise ResourceBudgetExceeded("DOCX archive entry budget exceeded")
            if item.filename.startswith("/") or ".." in item.filename.split("/"):
                raise UnsupportedDocument("Unsafe DOCX archive entry")
        if "[Content_Types].xml" not in names or "word/document.xml" not in names:
            raise UnsupportedDocument("Missing DOCX document parts")
        content_types = fromstring(archive.read("[Content_Types].xml"), forbid_dtd=True)
        main_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        )
        if not any(
            node.get("PartName") == "/word/document.xml" and node.get("ContentType") == main_type
            for node in content_types
        ):
            raise UnsupportedDocument("Only standard DOCX documents are supported")
        if any("macro" in str(node.get("ContentType", "")).lower() for node in content_types):
            raise UnsupportedDocument("Macro-enabled content is not supported")
        root = fromstring(archive.read("word/document.xml"), forbid_dtd=True)
    body = root.find(W + "body")
    if body is None:
        raise UnsupportedDocument("Missing DOCX document body")
    # Main-body paragraphs include table cells in XML order, not a rendered page layout.
    paragraphs = []

    def gather(node):
        if node.tag in {W + "del", W + "txbxContent"}:
            return
        if node.tag == W + "p":
            paragraphs.append(node)
            return
        for child in node:
            gather(child)

    gather(body)
    if len(paragraphs) > 2000:
        raise ResourceBudgetExceeded("DOCX paragraph budget exceeded")
    warnings = [
        "DOCX body paragraphs and table cells only; no page layout, headers, footnotes or field evaluation."
    ]
    return assemble(
        ((n, paragraph_text(p)) for n, p in enumerate(paragraphs, 1)),
        raw,
        "docx",
        title,
        kind,
        warnings,
    )


def extract_document(raw, format, title, kind):
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ResourceBudgetExceeded("File byte budget exceeded")
    if format == "pdf":
        from pypdf import apply_configuration
        from pypdf.errors import LimitReachedError

        try:
            with apply_configuration(
                maximum_declared_stream_length=MAX_FILE_BYTES,
                array_based_stream_maximum_output_length=MAX_UNPACKED_BYTES,
                zlib_maximum_output_length=MAX_UNPACKED_BYTES,
                lzw_maximum_output_length=MAX_UNPACKED_BYTES,
                run_length_maximum_output_length=MAX_UNPACKED_BYTES,
                brotli_maximum_output_length=MAX_UNPACKED_BYTES,
                stream_decoding_work_maximum_length=4 * MAX_UNPACKED_BYTES,
                stream_filters_maximum_length=4,
                page_tree_maximum_entries=200,
                page_tree_maximum_depth=20,
                xform_maximum_invocations_per_extraction=100,
                jbig2dec_binary=None,
                disable_legacy_handling=True,
            ):
                return extract_pdf(raw, title, kind)
        except LimitReachedError:
            raise ResourceBudgetExceeded("PDF decoder budget exceeded") from None
    if format == "docx":
        return extract_docx(raw, title, kind)
    raise UnsupportedDocument("Supported formats are PDF and DOCX")


def extract_isolated(raw, format, title, kind, timeout_seconds=15):
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ResourceBudgetExceeded("File byte budget exceeded")
    payload = {
        "data": base64.b64encode(raw).decode(),
        "format": format,
        "title": title,
        "kind": kind,
    }
    try:
        child = subprocess.run(
            [sys.executable, "-m", "atlas.ingestion_task"],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        raise ExtractionFailed("Document extraction deadline exceeded") from None
    if len(child.stdout) > 1_000_000:
        raise ExtractionFailed("Invalid extraction response")
    try:
        response = json.loads(child.stdout)
        if child.returncode:
            if response.get("error") == "resource_budget_exceeded":
                raise ResourceBudgetExceeded("Document extraction budget exceeded")
            if response.get("error") == "unsupported_document":
                raise UnsupportedDocument(response["detail"])
            raise ExtractionFailed("Document could not be extracted safely")
        document = Document.model_validate(response)
        if (
            document.id != document_id(raw, kind)
            or document.kind != kind
            or document.title != title
            or document.source_map is None
            or document.source_map.raw_sha256 != sha256(raw).hexdigest()
            or document.source_map.format != format
            or document.source_map.parser_version != PARSER_VERSION
        ):
            raise ExtractionFailed("Extraction identity mismatch")
        return document
    except (ValueError, KeyError, TypeError):
        raise ExtractionFailed("Invalid extraction response") from None
