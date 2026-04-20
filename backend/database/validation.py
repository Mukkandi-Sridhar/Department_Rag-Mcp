import re
from typing import Any

UPDATABLE_FIELDS = {"cgpa", "backlogs", "placement", "performance", "risk", "name"}


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

    sanitized = {}

    reg_no = str(data.get("reg_no", "")).strip().upper()
    if re.match(r"^[A-Z0-9]{10}$", reg_no):
        sanitized["reg_no"] = reg_no

    name = str(data.get("name", "")).strip()
    if name:
        sanitized["name"] = name

    try:
        cgpa = float(data.get("cgpa", 0))
        if 0.0 <= cgpa <= 10.0:
            sanitized["cgpa"] = cgpa
    except (TypeError, ValueError):
        pass

    try:
        backlogs = int(data.get("backlogs", 0))
        if backlogs >= 0:
            sanitized["backlogs"] = backlogs
    except (TypeError, ValueError):
        pass

    placement = str(data.get("placement", "")).strip().lower()
    if placement in {"yes", "no"}:
        sanitized["placement"] = placement

    for field in ["performance", "risk"]:
        val = str(data.get(field, "")).strip()
        if val:
            sanitized[field] = val

    return sanitized


def validate_student_update(fields: dict[str, Any]) -> dict[str, Any]:
    """Validates partial update fields using the UPDATABLE_FIELDS whitelist."""
    validated = {}
    
    # We pass it through full validation first
    full_val = validate_student(fields)
    
    for k, v in full_val.items():
        if k in UPDATABLE_FIELDS:
            validated[k] = v
            
    return validated
