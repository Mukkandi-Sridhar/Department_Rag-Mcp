def normalize_query(message: str | None) -> str:
    return " ".join((message or "").lower().strip().split())
