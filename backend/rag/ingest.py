from pathlib import Path
from typing import Any

from backend.config import settings
from backend.rag.embeddings import get_embeddings


def ingest_pdf(file_path: str | Path) -> dict[str, Any]:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_community.vectorstores import Chroma

    path = Path(file_path)
    loader = PyPDFLoader(str(path))
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(documents)

    for chunk in chunks:
        chunk.metadata["source"] = path.name

    Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        persist_directory=str(settings.chroma_dir),
    ).persist()

    return {
        "status": "indexed",
        "file": path.name,
        "chunks": len(chunks),
    }
