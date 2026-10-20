"""Reproducible authored synthetic PDF/DOCX fixtures; no customer data."""

import argparse
import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def pdf_bytes(pages):
    writer = PdfWriter()
    for lines in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        commands = ["BT /F1 11 Tf 50 730 Td 16 TL"]
        for line in lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({safe}) Tj T*")
        commands.append("ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(commands).encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    target = io.BytesIO()
    writer.write(target)
    return target.getvalue()


def docx_bytes(paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>" for text in paragraphs)
    body += "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Recovery time is only guaranteed within 8 hours.</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Audit records are retained for only 90 days.</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:

        def write_part(name, content):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)

        write_part(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        write_part(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        write_part(
            "word/document.xml",
            f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}<w:sectPr/></w:body></w:document>',
        )
    return target.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="datasets/documents")
    root = Path(parser.parse_args().output)
    root.mkdir(parents=True, exist_ok=True)
    (root / "municipal-rfp.pdf").write_bytes(
        pdf_bytes(
            [
                [
                    "NORTHSTAR MUNICIPAL PROCUREMENT - SYNTHETIC FIXTURE",
                    "No real customer information.",
                    "4.1 Data must remain in Canada.",
                    "4.2 The platform shall support SSO using SAML.",
                    "4.3 AES-256 encryption at rest is required.",
                ],
                [
                    "NORTHSTAR MUNICIPAL PROCUREMENT - PAGE TWO",
                    "5.1 The vendor must provide 24/7 incident response.",
                    "5.2 Recovery time must be at most 4 hours.",
                    "5.3 Audit records must be retained for 365 days.",
                    "6.1 WCAG 2.2 AA accessibility conformance is required.",
                ],
            ]
        )
    )
    (root / "capability-register.docx").write_bytes(
        docx_bytes(
            [
                "NORTHSTAR CAPABILITY REGISTER — SYNTHETIC FIXTURE",
                "No real customer information. Café team review.",
                "Customer data is stored in Canada in the Montreal region.",
                "SSO using SAML is enabled for enterprise tenants.",
                "AES-256 encryption at rest protects customer volumes.",
                "The incident response team operates 24/7.",
            ]
        )
    )
    print("Generated two synthetic upload fixtures")


if __name__ == "__main__":
    main()
