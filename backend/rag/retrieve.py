import re
from typing import Any

from backend.config import settings
from backend.rag.embeddings import get_embeddings
from backend.rag.ingest import COLLECTION_NAME


STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "document",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "pdf",
    "say",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


def _get_chromadb():
    try:
        import chromadb
    except ImportError:
        return None

    return chromadb


def _query_terms(query: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) >= 3 and term not in STOPWORDS
    }


def _similarity_from_distance(distance: float | None) -> float | None:
    if distance is None:
        return None
    return round(1 / (1 + float(distance)), 4)


def retrieve_documents(query: str, k: int = 3) -> list[dict[str, Any]]:
    if not settings.chroma_dir.exists():
        return []

    chromadb = _get_chromadb()
    if chromadb is None:
        return []

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception:
        return []

    if collection.count() == 0:
        return []

    embeddings = get_embeddings()
    query_embedding = embeddings.embed_query(query)
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    query_terms = _query_terms(query)
    docs: list[dict[str, Any]] = []

    for text, metadata, distance in zip(documents, metadatas, distances):
        text = str(text or "").strip()
        if not text:
            continue

        matched_terms = sorted(
            term for term in query_terms if term in text.lower()
        )
        if query_terms and not matched_terms:
            continue

        metadata = metadata or {}
        docs.append(
            {
                "text": text,
                "score": _similarity_from_distance(distance),
                "matched_terms": matched_terms,
                "source": {
                    "document": metadata.get("source", "Unknown"),
                    "page": metadata.get("page"),
                    "chunk_index": metadata.get("chunk_index"),
                },
            }
        )

    return docs
