"""Normalize native text, tables and selective OCR without retaining source files."""
import io
import json
import logging
import os
import re
import statistics
import warnings as python_warnings
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pdfplumber
from PIL import Image
from pdfminer.pdfdocument import PDFPasswordIncorrect

# These parsers can include malformed document tokens/metadata in their warnings.
for parser_logger in ("pdfminer", "pdfplumber"):
    logging.getLogger(parser_logger).setLevel(logging.CRITICAL)

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILES = 10
MAX_PAGES = 100
MAX_TEXT = 180_000
MAX_BLOCK_TEXT = 12_000
MAX_IMAGE_PIXELS = 25_000_000


class DocumentError(ValueError):
    def __init__(self, message, status=422, code="invalid_document"):
        super().__init__(message)
        self.status, self.code = status, code


def ocr(image):
    import pytesseract
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise DocumentError("Image is too large to process safely.", 413, "image_too_large")
    if os.getenv("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
    try:
        return pytesseract.image_to_string(image, lang=os.getenv("OCR_LANGUAGES", "eng"),
                                          config="-c preserve_interword_spaces=1", timeout=45)
    except pytesseract.TesseractNotFoundError as exc:
        raise DocumentError("OCR is temporarily unavailable. Try a searchable PDF.", 503, "ocr_unavailable") from exc
    except (RuntimeError, pytesseract.TesseractError) as exc:
        raise DocumentError("OCR could not finish. Try a clearer or smaller document.", 422, "ocr_failed") from exc


def sentences(text):
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ü])", text)
    result = []
    for piece in pieces:
        if result and re.search(r"\b(?:Dr|Mr|Mrs|Ms|Prof|Sr|Jr|No|Fig|e\.g|i\.e|[A-Z])\.$", result[-1], re.I):
            result[-1] += " " + piece
        else:
            result.append(piece)
    return result


def text_kind(text):
    if re.search(r"(?m)^\s*(?:[-•●▪]|\d+[.)])\s", text):
        return "list"
    if re.search(r"[=∑∫√≤≥]|\b\S+@\S+|^\w[\w ]{0,35}:|\S+\s{3,}\S+", text):
        return "structured"
    if len(text) < 100 and not re.search(r"[.!?]$", text):
        return "heading"
    return "text"


class Blocks:
    def __init__(self, source):
        self.source, self.items, self.characters = source, [], 0

    def add(self, content, page, kind=None, origin="native", bbox=None):
        content = content.strip()
        if not content or not any(c.isalnum() for c in content):
            return
        kind = kind or text_kind(content)
        for piece in sentences(content) if kind == "text" else [content]:
            if len(piece) > MAX_BLOCK_TEXT:
                raise DocumentError("A document section is too large. Split the source document.", 413, "block_too_large")
            self.characters += len(piece)
            if self.characters > MAX_TEXT:
                raise DocumentError("Document text exceeds the extraction limit. Split the upload.", 413, "text_too_large")
            order = len(self.items)
            self.items.append(dict(id=f"b{order}", type="sentence" if kind == "text" else kind,
                                   content=piece, page=page, order=order, source_file=self.source,
                                   metadata={"origin": origin, **({"bbox": list(bbox)} if bbox else {})}))

    def ocr_text(self, text, page, bbox=None):
        for paragraph in re.split(r"\n\s*\n", text):
            # Preserve aligned OCR columns verbatim; do not invent cell relationships.
            kind = "table" if len(re.findall(r"\S {3,}\S", paragraph)) >= 2 else None
            self.add(paragraph, page, kind, "ocr", bbox)


def table_text(rows):
    if not rows or any(not isinstance(row, (list, tuple)) for row in rows):
        raise DocumentError("A table could not be read. Try exporting the document again.", 422, "malformed_table")
    if not any(cell and str(cell).strip() for row in rows for cell in row):
        return ""
    return json.dumps({"rows": [[cell or "" for cell in row] for row in rows]}, ensure_ascii=False)


def render(page, crop=None):
    if page.width * page.height * (150 / 72) ** 2 > MAX_IMAGE_PIXELS:
        raise DocumentError("PDF page is too large for OCR. Try a smaller page size.", 413, "image_too_large")
    return (page.crop(crop) if crop else page).to_image(resolution=150).original


def inside(char, bbox):
    x, y = (char["x0"] + char["x1"]) / 2, (char["top"] + char["bottom"]) / 2
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def extract_pdf(data, blocks, notes):
    if not data.startswith(b"%PDF-"):
        raise DocumentError("The file is not a valid PDF.")
    with pdfplumber.open(io.BytesIO(data), strict_metadata=True) as pdf:
        if getattr(pdf.doc, "encryption", None):
            raise DocumentError("Password-protected PDFs are not supported.", 422, "encrypted_pdf")
        if not pdf.pages:
            raise DocumentError("The PDF contains no pages.", 422, "empty_document")
        if len(pdf.pages) > MAX_PAGES:
            raise DocumentError(f"PDFs may contain at most {MAX_PAGES} pages.", 413, "too_many_pages")
        for number, page in enumerate(pdf.pages, 1):
            native = page.extract_text() or ""
            if sum(c.isalnum() for c in native) < 3:
                blocks.ocr_text(ocr(render(page)), number)
                notes.append(f"{blocks.source}, page {number}: OCR was used; verify tables, dates and marks.")
                continue
            tables = page.find_tables()
            regions = [(t.bbox[1], t.bbox[0], table_text(t.extract()), "table", "native", t.bbox) for t in tables]
            filtered = page.filter(lambda obj: obj.get("object_type") != "char" or not any(inside(obj, t.bbox) for t in tables))
            lines = filtered.extract_text_lines()
            heights = [c.get("size", 0) for c in page.chars if c.get("size", 0) > 0]
            body_size = statistics.median(heights) if heights else 10
            paragraph, previous_bottom = [], 0

            def flush():
                if paragraph:
                    first, last = paragraph[0], paragraph[-1]
                    text = " ".join(line["text"] for line in paragraph)
                    regions.append((first["top"], first["x0"], text, None, "native",
                                    (first["x0"], first["top"], max(line["x1"] for line in paragraph), last["bottom"])))
                    paragraph.clear()

            for line in lines:
                kind = text_kind(line["text"])
                is_heading = any(c.get("size", 0) > body_size * 1.2 for c in line.get("chars", []))
                if line["top"] - previous_bottom > body_size * .8 or kind in {"list", "structured"} or is_heading:
                    flush()
                if kind in {"list", "structured"} or is_heading:
                    regions.append((line["top"], line["x0"], line["text"], "heading" if is_heading else kind,
                                    "native", (line["x0"], line["top"], line["x1"], line["bottom"])))
                else:
                    paragraph.append(line)
                previous_bottom = line["bottom"]
            flush()
            seen = set()
            for img in page.images:
                bbox = (max(page.bbox[0], img["x0"]), max(page.bbox[1], img["top"]),
                        min(page.bbox[2], img["x1"]), min(page.bbox[3], img["bottom"]))
                width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
                if bbox in seen or min(width, height) < 35 or width * height < page.width * page.height * .01:
                    continue
                seen.add(bbox)
                if sum(inside(c, bbox) for c in page.chars) > 30 and width * height > page.width * page.height * .8:
                    continue  # Scanned background already covered by a native text layer.
                text = ocr(render(page, bbox))
                regions.append((bbox[1], bbox[0], text, None, "ocr", bbox))
                notes.append(f"{blocks.source}, page {number}: image-region OCR was used; verify its content.")
            for _, _, text, kind, origin, bbox in sorted(regions, key=lambda r: (r[0], r[1])):
                if origin == "ocr":
                    blocks.ocr_text(text, number, bbox)
                else:
                    blocks.add(text, number, kind, origin, bbox)


def read_image(data):
    with python_warnings.catch_warnings():
        python_warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            image.close()
            raise DocumentError("Image is too large to process safely.", 413, "image_too_large")
        return image


def extract_source(name, data, mime=None):
    name = name.replace("\\", "/").split("/")[-1][:180]  # Metadata, never a filesystem path.
    suffix = Path(name).suffix.lower()
    allowed = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    if suffix not in allowed or mime not in {None, "", "application/octet-stream", allowed.get(suffix)}:
        raise DocumentError("Supported files: PDF, DOCX, PNG and JPEG with matching file types.", 415, "unsupported_file")
    notes, blocks = [], Blocks(name)
    try:
        if suffix == ".pdf":
            extract_pdf(data, blocks, notes)
        elif suffix == ".docx":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(item.file_size for item in archive.infolist()) > MAX_TOTAL_BYTES:
                    raise DocumentError("Expanded DOCX exceeds the document limit.", 413, "file_too_large")
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                body = ElementTree.fromstring(archive.read("word/document.xml")).find("w:body", ns)
                for element in body:
                    if element.tag.endswith("}tbl"):
                        rows = [[" ".join(n.text or "" for n in cell.findall(".//w:t", ns))
                                 for cell in row.findall("w:tc", ns)] for row in element.findall("w:tr", ns)]
                        blocks.add(table_text(rows), 0, "table")
                    else:
                        text = "".join(n.text or "" for n in element.findall(".//w:t", ns))
                        kind = "list" if element.find(".//w:numPr", ns) is not None else None
                        blocks.add(text, 0, kind)
                for item in archive.namelist():
                    if item.startswith("word/media/"):
                        with read_image(archive.read(item)) as img:
                            blocks.ocr_text(ocr(img), 0)
                        notes.append(f"{name}: embedded images used OCR; DOCX page numbers are unavailable.")
        else:
            with read_image(data) as img:
                if img.format != ("PNG" if suffix == ".png" else "JPEG"):
                    raise DocumentError("Image format does not match its extension.", 415, "unsupported_file")
                blocks.ocr_text(ocr(img), 1)
            notes.append(f"{name}: OCR was used; verify tables, dates and marks.")
    except DocumentError:
        raise
    except PDFPasswordIncorrect as exc:
        raise DocumentError("Password-protected PDFs are not supported.", 422, "encrypted_pdf") from exc
    except Exception as exc:
        if isinstance(exc.__context__, PDFPasswordIncorrect):
            raise DocumentError("Password-protected PDFs are not supported.", 422, "encrypted_pdf") from exc
        raise DocumentError("Could not read the document. Upload an unencrypted, readable file.") from exc
    if not blocks.items:
        raise DocumentError("No readable text was found in the document.", 422, "empty_document")
    return {"filename": name, "blocks": blocks.items,
            "text": "\n".join(b["content"] for b in blocks.items)}, notes
