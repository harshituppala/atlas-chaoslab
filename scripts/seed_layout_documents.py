"""Generate fictional layout fixtures; expected text is authored separately."""

import io
import zipfile
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1] / "datasets/documents/layout"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES = """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>"""


def docx(name, body):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, text in (
            ("[Content_Types].xml", CONTENT_TYPES),
            (
                "word/document.xml",
                f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>',
            ),
        ):
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            archive.writestr(info, text.encode())
    (ROOT / name).write_bytes(target.getvalue())


def paragraph(text):
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for lines in (
        ("Recovery must complete within four hours.", "Fictional procurement - review copy"),
        (),
        ("Evidence must identify the recovery test.", "Fictional procurement - review copy"),
    ):
        page = writer.add_blank_page(width=612, height=792)
        if lines:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): writer._add_object(font)}
                    )
                }
            )
            commands = (
                "BT /F1 12 Tf 72 720 Td "
                + " 0 -24 Td ".join(f"({line}) Tj" for line in lines)
                + " ET"
            )
            stream = DecodedStreamObject()
            stream.set_data(commands.encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    with (ROOT / "repeated-footer.pdf").open("wb") as handle:
        writer.write(handle)
    docx(
        "split-runs.docx",
        """<w:p><w:r><w:t>Café team </w:t></w:r><w:r><w:t>shall review </w:t></w:r><w:r><w:t>the recovery evidence.</w:t></w:r></w:p>
<w:p><w:r><w:t>Current recovery target: four hours.</w:t></w:r><w:del><w:r><w:delText>Deleted target: one hour.</w:delText></w:r></w:del></w:p>
<w:p><w:r><w:t>Owner</w:t><w:tab/><w:t>Review team</w:t><w:br/><w:t>Canada</w:t></w:r></w:p>""",
    )
    rows = (
        '<w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>'
        + paragraph("Recovery evidence")
        + "</w:tc></w:tr>"
    )
    for left, right in (("Criterion", "Capability"), ("Recovery target", "Eight hours")):
        rows += (
            "<w:tr><w:tc>" + paragraph(left) + "</w:tc><w:tc>" + paragraph(right) + "</w:tc></w:tr>"
        )
    docx("merged-table.docx", "<w:tbl>" + rows + "</w:tbl>")
    print("Generated three fictional layout fixtures.")


if __name__ == "__main__":
    main()
