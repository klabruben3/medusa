from dotenv import load_dotenv
from .clean_text import is_mid_sentence, extract_english_portion
from ..types.schema import Block
from .chroma_connection import get_chroma_collection
import voyageai
from .categories import categories

load_dotenv()

vo = voyageai.Client()

# page_to_blocks utils


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


def format_table(table_content):
    formated_table = ""

    for row in table_content:
        for col in row:
            if not col:
                continue
            formated_table += f"{col} | "
        formated_table += "\n"

    return formated_table.rstrip()
###


def page_to_blocks(page):
    blocks: list[Block] = []

    tables = page.find_tables()
    table_bboxes = [t.bbox for t in tables]
    for t in tables:
        blocks.append({
            "content": format_table(t.extract()),
            "bbox": t.bbox,
            "top": t.bbox[1],
        })

    # TODO: if actual image text is needed, run OCR (e.g. pytesseract) on the
    # cropped region before treating this as "extracted" text.
    for img in page.images:
        blocks.append({
            "content": "--- text to represent extracted text from an image in a document ---",
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
                "content": english_content,
                "bbox": residual_bbox,
                "top": residual_bbox[1] if residual_bbox else 0,
            })

    blocks.sort(key=lambda b: b["top"])
    return blocks


async def create_categorized_documents(blocks: list[Block], id: str):
    collection = get_chroma_collection()
    contents = [block["content"] for block in blocks]

    # embedding ai
    documents_result = vo.embed(
        contents,
        model="voyage-4-lite",
        input_type="document"
    )

    query_result = vo.embed(
        [category["query"]
         for category in categories],
        model="voyage-4-lite",
        input_type="query"
    )
    # # #

    collection.add(
        ids=[
            f"{id}_{i}"
            for i in range(len(contents))
        ],

        documents=contents,

        embeddings=documents_result.embeddings,

        metadatas=[
            {
                "ingestion_id": id
            }
            for _ in blocks
        ]
    )

    query_results = collection.query(
        query_embeddings=query_result.embeddings,
        n_results=5,
        where={
            "ingestion_id": id
        }
    )

    categorized_documents = [
        {
            "category": category["category"],
            "documents": query_results["documents"][i],
            "ids": query_results["ids"][i],
            "distances": query_results["distances"][i]
        }
        for i, category in enumerate(categories)
    ]
    
    return categorized_documents

# exports: page_to_blocks, create_categorized_documents
