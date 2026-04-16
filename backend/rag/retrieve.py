from typing import Any

from backend.config import settings
from backend.rag.embeddings import get_embeddings


def retrieve_documents(query: str, k: int = 3) -> list[dict[str, Any]]:
    from langchain_community.vectorstores import Chroma

    if not settings.chroma_dir.exists():
        return []

    vectordb = Chroma(
        persist_directory=str(settings.chroma_dir),
        embedding_function=get_embeddings(),
    )
    docs = vectordb.similarity_search(query, k=k)

    return [
        {
            "text": doc.page_content,
            "source": {
                "document": doc.metadata.get("source", "Unknown"),
                "page": doc.metadata.get("page"),
            },
        }
        for doc in docs
    ]
