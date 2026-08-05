import pdfplumber
from typing import BinaryIO

def page_to_blocks(page):
    blocks = []

    # Tables first — cheap-ish, and we need their bboxes to exclude their text
    tables = page.find_tables()
    table_bboxes = [t.bbox for t in tables]
    for t in tables:
        blocks.append({
            "type": "table",
            "content": t.extract(),
            "bbox": t.bbox,
            "top": t.bbox[1],
        })

    # Images — already extracted, no per-word parsing needed
    for img in page.images:
        blocks.append({
            "type": "image",
            "content": img,
            "bbox": (img["x0"], img["top"], img["x1"], img["bottom"]),
            "top": img["top"],
        })

    # Text lines — much faster than extract_words()
    for line in page.extract_text_lines():
        line_bbox = (line["x0"], line["top"], line["x1"], line["bottom"])
        # skip lines that fall inside a table bbox to avoid duplicating table text
        if any(_overlaps(line_bbox, tb) for tb in table_bboxes):
            continue
        blocks.append({
            "type": "text",
            "content": line["text"],
            "bbox": line_bbox,
            "top": line["top"],
        })

    blocks.sort(key=lambda b: b["top"])
    return blocks


def _overlaps(a, b):
    ax0, atop, ax1, abot = a
    bx0, btop, bx1, bbot = b
    return not (ax1 < bx0 or ax0 > bx1 or abot < btop or atop > bbot)


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
            for block in page_to_blocks(page):
                if block["type"] == "text":
                    document_info += f"\n{block['content']}\n"
                elif block["type"] == "image":
                    document_info += "\n--- Text extracted from an image ---\n"
                elif block["type"] == "table":
                    document_info += f"\n{format_table(block['content'])}\n"

    return document_info
