from ..utils.categorize import create_categorized_documents
from ..utils.chroma_connection import get_chroma_collection


async def create_module(blocks, ingestion_id):
    try:
        categorized_documents = await create_categorized_documents(
            blocks,
            ingestion_id
        )

        for category in categorized_documents:
            print(f"\n--- {category['category']} ---")

            for document in category["documents"]:
                print(f"{document}\n")

        # AI calls here #
        module = "--- Im supposed to represent a module ---"

        return module

    finally:
        collection = get_chroma_collection()

        collection.delete(
            where={
                "ingestion_id": ingestion_id
            }
        )
