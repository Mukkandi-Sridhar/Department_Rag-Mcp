from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_str(value: Any, default: str = "Unknown") -> str:
    text = str(value if value not in (None, "") else default).strip()
    return text or default


def validate_student(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}

    return {
        "reg_no": _safe_str(data.get("reg_no"), ""),
        "name": _safe_str(data.get("name")),
        "cgpa": _safe_float(data.get("cgpa")),
        "backlogs": _safe_int(data.get("backlogs")),
        "risk": _safe_str(data.get("risk")),
        "performance": _safe_str(data.get("performance")),
        "placement": _safe_str(data.get("placement")),
    }
