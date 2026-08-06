from typing import List
from fastapi import FastAPI, UploadFile, File as FastAPIFile
from fastapi.middleware.cors import CORSMiddleware
from .utils import extract_document_info, extract_modules

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


async def process_documents(files: list[UploadFile]) -> str:
    output_text = ""
    for upload in files:
        filename = upload.filename
        content_type = upload.content_type

        output_text += f"--- {filename} ({content_type}) ---\n"

        if content_type == "application/pdf":
            output_text += extract_document_info(upload.file) + "\n"
        elif content_type.startswith("image/"):
            output_text += "--- placeholder for text extracted for an image upload ---\n"

    return output_text


@app.get("/")
async def root():
    return {"message": "Hello Ruben, im from the root."}


@app.post("/process-documents")
async def main(
    files: List[UploadFile] = FastAPIFile(...),
):
    document_text = await process_documents(files)

    modules = extract_modules()

    print(f"document text: \n{document_text}")

    return {"modules": modules}
