from typing import Any


def build_response(
    status: str,
    intent: str,
    answer: str,
    data: dict[str, Any] | None = None,
    tool_used: str | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "intent": intent,
        "answer": answer,
        "data": data or {},
        "tool_used": tool_used,
        "error": error,
        "duration_ms": duration_ms,
    }
