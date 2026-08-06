import pdfplumber
from typing import BinaryIO
from .text_utils import is_mid_sentence, extract_english_portion, filter_relevant_blocks


def _merge_bbox(a, b):
    if a is None:
        return b
    return (
        min(a[0], b[0]),
        min(a[1], b[1]),
        max(a[2], b[2]),
        max(a[3], b[3]),
    )


def _word_in_table(word_bbox, table_bbox, tolerance=2):
    wx0, wtop, wx1, wbot = word_bbox
    center_x = (wx0 + wx1) / 2
    center_y = (wtop + wbot) / 2

    tx0, ttop, tx1, tbot = table_bbox
    tx0, ttop, tx1, tbot = tx0 - tolerance, ttop - \
        tolerance, tx1 + tolerance, tbot + tolerance

    return tx0 <= center_x <= tx1 and ttop <= center_y <= tbot


def page_to_blocks(page):
    blocks = []

    tables = page.find_tables()
    table_bboxes = [t.bbox for t in tables]
    for t in tables:
        blocks.append({
            "type": "table",
            "content": t.extract(),
            "bbox": t.bbox,
            "top": t.bbox[1],
        })

    # TODO: if actual image text is needed, run OCR (e.g. pytesseract) on the
    # cropped region before treating this as "extracted" text.
    for img in page.images:
        blocks.append({
            "type": "image",
            "content": img,
            "bbox": (img["x0"], img["top"], img["x1"], img["bottom"]),
            "top": img["top"],
        })

    residual = ""
    residual_bbox = None

    for word in page.extract_words():
        word_bbox = (word["x0"], word["top"], word["x1"], word["bottom"])
        if any(_word_in_table(word_bbox, tb) for tb in table_bboxes):
            continue

        residual_bbox = _merge_bbox(residual_bbox, word_bbox)

        if is_mid_sentence(word["text"]):
            residual += word["text"] + " "
            continue

        sentence = residual + word["text"]
        residual = ""

        english_content = extract_english_portion(sentence)
        if english_content is None:
            residual_bbox = None
            continue

        blocks.append({
            "type": "text",
            "content": english_content,
            "bbox": residual_bbox,
            "top": residual_bbox[1],
        })
        residual_bbox = None

    # Flush trailing text that never hit a sentence-ending period
    if residual.strip():
        english_content = extract_english_portion(residual.strip())
        if english_content is not None:
            blocks.append({
                "type": "text",
                "content": english_content,
                "bbox": residual_bbox,
                "top": residual_bbox[1] if residual_bbox else 0,
            })

    blocks.sort(key=lambda b: b["top"])
    return blocks


def format_table(table_content):
    formated_table = ""

    for row in table_content:
        for col in row:
            if not col:
                continue
            formated_table += f"{col} | "
        formated_table += "\n"

    return formated_table.rstrip()


def extract_document_info(file: BinaryIO):
    document_info = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            blocks = filter_relevant_blocks(page_to_blocks(page))
            for block in blocks:
                if block["type"] == "text":
                    document_info += f"\n{block['content']}\n"
                elif block["type"] == "image":
                    document_info += "\n--- Image on page (not OCR'd) ---\n"
                elif block["type"] == "table":
                    document_info += f"\n{format_table(block['content'])}\n"

    return document_info
