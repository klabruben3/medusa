from typing import List
from fastapi import FastAPI, UploadFile, File as FastAPIFile
from fastapi.middleware.cors import CORSMiddleware
from .types.schema import Block
from .utils import extract_document_info
from .ai.generate_module import create_module
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://academiq-nwu.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def process_documents(files: list[UploadFile]):
    blocks: list[Block] = []
    ingestion_id = str(uuid.uuid4())

    for upload in files:
        content_type = upload.content_type

        if content_type == "application/pdf":
            blocks.extend(extract_document_info(upload))
        elif content_type.startswith("image/"):
            print("--- placeholder for text extracted from an image upload ---")

    return await create_module(blocks, ingestion_id)


@app.get("/")
async def root():
    return {"message": "Hello Ruben, im from the root."}


@app.post("/process-documents")
async def main(
    files: List[UploadFile] = FastAPIFile(...),
):
    module = await process_documents(files)

    return {"module": module}
