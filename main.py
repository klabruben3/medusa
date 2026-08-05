from typing import List
from fastapi import FastAPI, UploadFile, File as FastAPIFile
from fastapi.middleware.cors import CORSMiddleware
from actions import extract_document_info

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def process_documents(files: list[UploadFile]):
    output_text = ""
    for upload in files:
        filename = upload.filename
        content_type = upload.content_type

        output_text += f"--- {filename} ({content_type}) ---"

        if content_type == "application/pdf":
            output_text += "\n" + extract_document_info(upload.file) + "\n"
        elif content_type.startswith("image/"):
            output_text += "\n--- placeholder for text extracted for an image upload ---\n"

    return output_text


@app.get("/")
async def root():
    return {"message": "Hello Ruben, im from the root."}


@app.post("/process-documents")
async def main(
    files: List[UploadFile] = FastAPIFile(...),
):
    result = await process_documents(files)

    print(result)

    return {"message": "we got your documents"}
