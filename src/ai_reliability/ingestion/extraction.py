"""Conservative text extraction; no network, OCR, citation resolution or repair."""
import hashlib
import io
import logging
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from ai_reliability.schemas.record import DocumentExtraction, ExtractedSegment

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 100000
MAX_PAGES = 40
MAX_ZIP_BYTES = 20 * 1024 * 1024
EXTRACTION_TIMEOUT = 20


class ExtractionError(ValueError):
    """Safe, actionable message suitable for display in the UI."""


def _document(data, filename, role, kind, parts, limitations):
    digest = hashlib.sha256(data).hexdigest()
    if not parts or sum(len(text) for _, text in parts) > MAX_TEXT_CHARS or len(parts) > 1000:
        raise ExtractionError("Document is empty or exceeds the 100000-character / 1000-segment extraction limit. Split it into smaller documents.")
    segments = [ExtractedSegment(id=f"src-{digest}-{i}", reference=ref, original_text=text,
                                citation_markers=re.findall(r"\[\d+(?:\s*[,;\-]\s*\d+)*\]", text))
                for i, (ref, text) in enumerate(parts, 1)]
    # Filename participates in the document identity so identical uploads with
    # different names retain both original names; source IDs depend on bytes.
    name_digest = hashlib.sha256((filename or "").encode()).hexdigest()[:16]
    return DocumentExtraction(id=f"doc-{role}-{digest}-{name_digest}", role=role, kind=kind,
                              filename=filename, content_sha256=digest, segments=segments,
                              limitations=limitations + ["Citation markers are untrusted text, not structured citations or resolved sources."])


def pasted_document(text, role):
    if not text.strip() or len(text) > MAX_TEXT_CHARS:
        raise ExtractionError("Pasted text must contain 1-100000 characters.")
    return _document(text.encode("utf-8"), None, role, "text", [("Pasted text", text)],
                     ["Text was supplied by the user; its truth and completeness are not verified."])


def validate_file(data, filename):
    if not data:
        raise ExtractionError("The uploaded file is empty. Choose a PDF or DOCX containing text.")
    if len(data) > MAX_FILE_BYTES:
        raise ExtractionError("File exceeds the 5 MiB limit. Split or reduce the document before uploading.")
    if not filename or len(filename) > 255 or any(c in filename for c in ("/", "\\", "\x00")):
        raise ExtractionError("Use a filename without directory paths, at most 255 characters.")
    extension = Path(filename).suffix.lower()
    if extension == ".doc":
        raise ExtractionError("Legacy .doc files are unsupported. Convert the file to .docx first.")
    if data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        raise ExtractionError("Encrypted Office or legacy binary document detected. Save an unencrypted .docx copy.")
    if extension == ".pdf" and data.startswith(b"%PDF-"):
        return "pdf"
    if extension == ".docx" and data.startswith(b"PK\x03\x04"):
        return "docx"
    raise ExtractionError("File content does not match a supported PDF/DOCX format. Renaming the extension does not convert a file.")


def _pdf(data):
    from pypdf import PdfReader
    if not data.rstrip().endswith(b"%%EOF"):
        raise ExtractionError("PDF is truncated or malformed. Re-export a complete PDF.")
    warnings = []
    class Capture(logging.Handler):
        def emit(self, record):
            warnings.append(record.levelno)
    logger = logging.getLogger("pypdf")
    handler = Capture()
    logger.addHandler(handler)
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ExtractionError("Encrypted PDFs are unsupported. Upload an unencrypted copy; passwords are not collected.")
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ExtractionError("PDF must contain 1-40 pages. Split the document before uploading.")
        if reader.get_fields():
            raise ExtractionError("PDF form fields cannot be extracted completely. Export a text-only document first.")
        parts = []
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            if not text or not text.strip():
                raise ExtractionError(f"PDF page {number} has no extractable text. OCR is required for scanned pages; remove intentional blank pages before uploading. No partial extraction was retained.")
            # Image text cannot be verified by a text-only extractor. Reject
            # rather than silently lose it, including images nested in forms.
            if len(page.images):
                raise ExtractionError(f"PDF page {number} contains images. OCR/image-text review or a text-only export is required; partial text will not be evaluated.")
            if page.get("/Annots"):
                for annotation in page["/Annots"]:
                    if annotation.get_object().get("/Contents"):
                        raise ExtractionError("PDF annotation text is unsupported. Flatten/export it as ordinary text before uploading.")
            parts.append((f"Page {number}", text))
            if sum(len(t) for _, t in parts) > MAX_TEXT_CHARS:
                raise ExtractionError("PDF exceeds the 100000-character extraction limit. Split the document.")
        if warnings:
            raise ExtractionError("PDF parser reported malformed content. Re-export the document; partial extraction is not accepted.")
        return parts
    finally:
        logger.removeHandler(handler)


def _docx(data):
    from defusedxml import ElementTree as ET
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [info.filename for info in entries]
        if len(entries) > 500 or len(names) != len(set(names)) or sum(i.file_size for i in entries) > MAX_ZIP_BYTES:
            raise ExtractionError("DOCX archive exceeds extraction limits or has duplicate parts. Re-export a smaller document.")
        for info in entries:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename or info.flag_bits & 1:
                raise ExtractionError("DOCX has unsafe or encrypted archive entries. Re-export an unencrypted document.")
            if info.file_size > MAX_FILE_BYTES or info.file_size > max(1, info.compress_size) * 100:
                raise ExtractionError("DOCX compressed content exceeds safe extraction limits.")
        if not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= set(names):
            raise ExtractionError("This ZIP file is not a valid DOCX document.")
        types = ET.fromstring(archive.read("[Content_Types].xml"))
        if not any(n.get("PartName") == "/word/document.xml" and n.get("ContentType") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" for n in types):
            raise ExtractionError("DOCX main document type is invalid or macro-enabled. Export a standard .docx.")
        relationships = ET.fromstring(archive.read("_rels/.rels"))
        if not any(n.get("Type", "").endswith("/officeDocument") and n.get("Target") in ("word/document.xml", "/word/document.xml") and n.get("TargetMode") != "External" for n in relationships):
            raise ExtractionError("DOCX package has no valid main document relationship.")
        if any("vbaproject" in name.lower() or name.startswith(("word/embeddings/", "word/media/")) for name in names):
            raise ExtractionError("DOCX contains images, macros or embedded objects. Supply a text-only export; OCR may be required.")
        relevant = ["word/document.xml"] + sorted(n for n in names if re.fullmatch(r"word/(header\d+|footer\d+|footnotes|endnotes)\.xml", n))
        parts = []
        for name in relevant:
            root = ET.fromstring(archive.read(name))
            if name == "word/document.xml" and root.find(w + "body") is None:
                raise ExtractionError("DOCX document body is missing.")
            unsupported = {"drawing", "pict", "object", "altChunk", "txbxContent", "ins", "del", "moveFrom", "moveTo", "instrText", "fldSimple", "sym", "commentReference", "numPr"}
            if any(node.tag in {w + t for t in unsupported} or "officeDocument/2006/math" in node.tag for node in root.iter()):
                raise ExtractionError("DOCX has unsupported content (images, fields, tracked changes, comments, automatic numbering, equations or text boxes). Accept revisions and export ordinary text before uploading.")
            section = "Body" if name == "word/document.xml" else Path(name).stem
            for index, paragraph in enumerate(root.iter(w + "p"), 1):
                text = "".join(node.text or "" if node.tag == w + "t" else "\t" if node.tag == w + "tab" else "\n"
                               for node in paragraph.iter() if node.tag in {w + "t", w + "tab", w + "br", w + "cr"})
                if not text.strip():
                    continue
                style = paragraph.find(w + "pPr/" + w + "pStyle")
                if style is not None and style.get(w + "val", "").lower().startswith("heading"):
                    section = text[:120]
                parts.append((f"{Path(name).name} / {section} / paragraph {index}", text))
                if len(parts) > 1000 or sum(len(t) for _, t in parts) > MAX_TEXT_CHARS:
                    raise ExtractionError("DOCX exceeds the text/segment extraction limit. Split the document.")
        return parts


def extract_in_worker(data, filename, role):
    """Called only inside the bounded worker; tests may call for edge cases."""
    kind = validate_file(data, filename)
    try:
        parts = _pdf(data) if kind == "pdf" else _docx(data)
        return _document(data, filename, role, kind, parts, [
            "Text extraction does not verify truth, reading order or layout. Review every segment against the original.",
            "PDF references are physical pages; DOCX references are XML parts/paragraphs and headings, not rendered page numbers.",
            "No OCR, external links, structured citation resolution or embedded objects are processed."])
    except ExtractionError:
        raise
    except Exception:
        raise ExtractionError("Document is malformed or uses unsupported content. Re-export as a standard text-only PDF or DOCX.") from None


def _extract_document(data, filename, role):
    validate_file(data, filename)
    if role not in ("answer", "evidence"):
        raise ExtractionError("Choose an explicit answer or evidence role.")
    with tempfile.TemporaryDirectory(prefix="reliability-extract-") as directory:
        source = Path(directory) / "input.bin"
        source.write_bytes(data)
        try:
            result = subprocess.run([sys.executable, "-m", "ai_reliability.ingestion.worker", str(source), filename, role],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=EXTRACTION_TIMEOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        except subprocess.TimeoutExpired:
            raise ExtractionError("Extraction exceeded 20 seconds. Split or simplify the document; no partial text was retained.") from None
        if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
            raise ExtractionError("Extraction failed or exceeded its resource budget. Split or re-export the document; no partial text was retained.")
        import json
        output = json.loads(result.stdout)
        if "error" in output:
            raise ExtractionError(output["error"])
        return DocumentExtraction.model_validate(output)


def extract_document(data, filename, role):
    try:
        return _extract_document(data, filename, role)
    except ExtractionError:
        raise
    except Exception:
        raise ExtractionError("Extraction could not complete. Check the server temporary-directory permissions and parser installation, or re-export the document. No partial text was retained.") from None
