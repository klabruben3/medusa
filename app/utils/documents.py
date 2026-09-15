"""Read complete sources without language filtering or retrieval truncation."""
import io
import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pdfplumber
from PIL import Image

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILES = 10
MAX_PAGES = 100
MAX_TEXT = 180_000


class DocumentError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def ocr(image):
    import pytesseract
    if os.getenv("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
    try:
        return pytesseract.image_to_string(image, lang=os.getenv("OCR_LANGUAGES", "eng"), timeout=45)
    except pytesseract.TesseractNotFoundError as exc:
        raise DocumentError("This document needs OCR. Install Tesseract on the server or upload a searchable PDF/DOCX.", 503) from exc
    except RuntimeError as exc:
        raise DocumentError("OCR could not finish. Upload a clearer or smaller document.") from exc


def extract_source(name, data):
    suffix = Path(name).suffix.lower()
    warnings = []
    sections = []
    readable = False
    try:
        if suffix == ".pdf":
            if not data.startswith(b"%PDF-"):
                raise DocumentError("The file is not a valid PDF.")
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                if len(pdf.pages) > MAX_PAGES:
                    raise DocumentError(f"PDFs may contain at most {MAX_PAGES} pages.", 413)
                for i, page in enumerate(pdf.pages, 1):
                    scanned = ""
                    text = page.extract_text(layout=True) or ""
                    if not text.strip() or page.images:
                        # OCR the whole page: mixed text/image pages can contain scanned tables.
                        scanned = ocr(page.to_image(resolution=150).original)
                        text += "\n[OCR transcription; may duplicate page text]\n" + scanned
                        warnings.append(f"{name}, page {i}: OCR was used; verify dates and marks.")
                    tables = page.extract_tables()
                    for table in tables:
                        text += "\n[TABLE]\n" + "\n".join(" | ".join((cell or "").replace("\n", " ") for cell in row) for row in table)
                    readable = readable or bool((page.extract_text() or "").strip()) or bool(scanned.strip())
                    sections.append(f"[Page {i}]\n{text}")
        elif suffix == ".docx":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(item.file_size for item in archive.infolist()) > MAX_TOTAL_BYTES:
                    raise DocumentError("Expanded DOCX exceeds the document limit.", 413)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                root = ElementTree.fromstring(archive.read("word/document.xml"))
                body = root.find("w:body", ns)
                for element in body:
                    if element.tag.endswith("}tbl"):
                        sections.append("\n".join(" | ".join(" ".join(n.text or "" for n in cell.findall(".//w:t", ns)) for cell in row.findall("w:tc", ns)) for row in element.findall("w:tr", ns)))
                    else:
                        sections.append("".join(node.text or "" for node in element.findall(".//w:t", ns)))
                for item in archive.namelist():
                    if item.startswith("word/media/"):
                        with Image.open(io.BytesIO(archive.read(item))) as img:
                            sections.append("[Embedded image OCR]\n" + ocr(img))
                        warnings.append(f"{name}: embedded images were transcribed using OCR.")
                readable = bool("".join(sections).strip())
        elif suffix in {".png", ".jpg", ".jpeg"}:
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in {"PNG", "JPEG"}:
                    raise DocumentError("Only PNG and JPEG images are supported.", 415)
                sections.append(ocr(img))
            readable = bool("".join(sections).strip())
            warnings.append(f"{name}: OCR was used; verify dates and marks.")
        else:
            raise DocumentError("Supported files: PDF, DOCX, PNG and JPEG.", 415)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(f"Could not read {name}. Upload an unencrypted, readable document.") from exc
    text = "\n".join(sections).strip()
    if not readable or not text or not any(c.isalnum() for c in text):
        raise DocumentError(f"No readable text found in {name}.")
    if len(text) > MAX_TEXT:
        raise DocumentError("Document text exceeds the extraction limit. Split the upload.", 413)
    return {"filename": name, "text": text}, warnings
