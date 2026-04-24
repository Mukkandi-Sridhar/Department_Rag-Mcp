from __future__ import annotations

from typing import Final


ROLE_STUDENT: Final[str] = "student"
ROLE_FACULTY: Final[str] = "faculty"
ROLE_HOD: Final[str] = "hod"

ROLE_CAN_ANALYTICS: Final[set[str]] = {ROLE_FACULTY, ROLE_HOD}
ROLE_CAN_MANAGE_DOCS: Final[set[str]] = {ROLE_FACULTY, ROLE_HOD}
ROLE_CAN_ADMIN_MUTATIONS: Final[set[str]] = {ROLE_FACULTY, ROLE_HOD}
ROLE_CAN_STUDENT_SELF: Final[set[str]] = {ROLE_STUDENT, ROLE_FACULTY, ROLE_HOD}
SUPPORTED_ROLES: Final[set[str]] = {ROLE_STUDENT, ROLE_FACULTY, ROLE_HOD}


def normalize_role(role: str | None, default: str = ROLE_STUDENT) -> str:
    value = str(role or "").strip().lower()
    return value if value else default


def can_run_analytics(role: str | None) -> bool:
    return normalize_role(role) in ROLE_CAN_ANALYTICS


def can_manage_documents(role: str | None) -> bool:
    return normalize_role(role) in ROLE_CAN_MANAGE_DOCS


def can_mutate_student_data(role: str | None) -> bool:
    return normalize_role(role) in ROLE_CAN_ADMIN_MUTATIONS


def can_access_student_progress(role: str | None) -> bool:
    return normalize_role(role) in ROLE_CAN_STUDENT_SELF


def is_supported_role(role: str | None) -> bool:
    return normalize_role(role) in SUPPORTED_ROLES

