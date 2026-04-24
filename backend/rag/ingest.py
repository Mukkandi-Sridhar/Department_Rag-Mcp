from pathlib import Path
from typing import Any

from pypdf import PdfReader

from backend.core.config import settings
from backend.rag.embeddings import get_embeddings


COLLECTION_NAME = "department_docs"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def _get_chromadb():
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "Document indexing is unavailable because chromadb is not installed."
        ) from exc

    return chromadb


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def _chunk_text(text: str) -> list[str]:
    text = _normalize_text(text)
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks


def ingest_pdf(file_path: str | Path, visibility: str = "student") -> dict[str, Any]:
    path = Path(file_path)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    chromadb = _get_chromadb()
    normalized_visibility = str(visibility or "student").strip().lower()
    if normalized_visibility not in {"student", "faculty"}:
        normalized_visibility = "student"

    reader = PdfReader(str(path))
    embeddings = get_embeddings()

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for page_index, page in enumerate(reader.pages):
        page_text = _normalize_text(page.extract_text() or "")
        for chunk_index, chunk in enumerate(_chunk_text(page_text)):
            doc_id = f"{path.stem}-p{page_index + 1}-c{chunk_index + 1}"
            ids.append(doc_id)
            documents.append(chunk)
            metadatas.append(
                {
                    "source": path.name,
                    "page": page_index + 1,
                    "chunk_index": chunk_index + 1,
                    "visibility": normalized_visibility,
                }
            )

    if not documents:
        raise RuntimeError(f"No readable text found in PDF: {path.name}")

    vectors = embeddings.embed_documents(documents)
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    try:
        collection.delete(where={"source": path.name})
    except Exception:
        pass

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=vectors,
    )

    return {
        "status": "indexed",
        "file": path.name,
        "chunks": len(documents),
        "pages": len(reader.pages),
        "visibility": normalized_visibility,
    }
