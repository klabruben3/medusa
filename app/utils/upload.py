import pdfplumber
from fastapi import UploadFile
from ..types.schema import Block
from .categorize import page_to_blocks


def extract_document_info(uploaded_file: UploadFile) -> dict:
    blocks: list[Block] = []

    with pdfplumber.open(uploaded_file.file) as pdf:
        for page in pdf.pages:
            blocks.extend(page_to_blocks(page))

    return blocks


# exports: extract_document_info
