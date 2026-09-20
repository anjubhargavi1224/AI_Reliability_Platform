"""Regenerate hand-authored parser fixtures (requires reportlab==5.0.1).

These are software test documents, not model-generated experimental results.
"""
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).parent
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx(name, text, extra=""):
    with ZipFile(ROOT / name, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>{extra}<w:sectPr/></w:body></w:document>')


def main():
    pdf = canvas.Canvas(str(ROOT / "answer.pdf"), pageCompression=0)
    pdf.drawString(72, 720, "Synthetic answer fixture: growth was 17% [1].")
    pdf.save()
    pdf = canvas.Canvas(str(ROOT / "evidence.pdf"), pageCompression=0)
    pdf.drawString(72, 720, "Synthetic evidence fixture: growth was 4%.")
    pdf.showPage()
    pdf.drawString(72, 720, "Second evidence page: no additional growth claim.")
    pdf.save()
    pdf = canvas.Canvas(str(ROOT / "scanned.pdf"))
    pdf.drawImage(ImageReader(Image.new("RGB", (30, 30), "white")), 72, 500, 100, 100)
    pdf.save()
    for name, include_answer in (("blank.pdf", False), ("partial.pdf", True)):
        writer = PdfWriter()
        if include_answer:
            writer.append(PdfReader(ROOT / "answer.pdf"))
        writer.add_blank_page(width=612, height=792)
        writer.write(ROOT / name)
    writer = PdfWriter()
    writer.append(PdfReader(ROOT / "answer.pdf"))
    writer.encrypt("fixture-password-not-a-credential")
    writer.write(ROOT / "encrypted.pdf")
    docx("answer.docx", "Synthetic answer fixture: growth was 17% [1].")
    docx("evidence.docx", "Synthetic evidence: growth was 4%. Unicode: café 日本語.",
         '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table evidence cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
    docx("tracked.docx", "Synthetic evidence", '<w:ins><w:r><w:t>unaccepted edit</w:t></w:r></w:ins>')


if __name__ == "__main__":
    main()
