import asyncio
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app
from backend.auth.firebase_auth import AuthUser
from backend.mcp.server import process_tool_call


client = TestClient(app)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _auth_user_for_role(role: str) -> AuthUser:
    role = role.strip().lower()
    if role == "student":
        return AuthUser(
            uid="dev-student-23091A3349",
            email="student@rgmcet.edu.in",
            reg_no_hint="23091A3349",
            role_hint="student",
        )
    return AuthUser(
        uid=f"dev-{role}-fac001",
        email=f"{role}@rgmcet.edu.in",
        faculty_id_hint="FAC001",
        role_hint=role,
    )


def _profile_for_role(role: str) -> dict:
    role = role.strip().lower()
    profile = {"uid": f"{role}-uid", "role": role, "email": f"{role}@rgmcet.edu.in"}
    if role == "student":
        profile["reg_no"] = "23091A3349"
    return profile


async def _run_mcp_tool(name: str, role: str, arguments: dict | None = None) -> str:
    result = await process_tool_call(
        name,
        arguments or {},
        actor_uid=f"{role}-uid",
        actor_role=role,
    )
    return result[0].text if result else ""


def _check_mcp_policy_matrix() -> None:
    student_text = asyncio.run(_run_mcp_tool("update_student_data", "student", {"reg_no": "23091A3349", "fields": {"cgpa": 8.1}}))
    _assert("permission denied" in student_text.lower(), f"Student must be denied update_student_data: {student_text}")

    faculty_text = asyncio.run(_run_mcp_tool("search_students", "faculty", {"query": "MATCH (s:Student) RETURN count(s) AS count"}))
    _assert("count" in faculty_text.lower() or "no records" in faculty_text.lower(), f"Faculty should access search_students: {faculty_text}")

    hod_text = asyncio.run(_run_mcp_tool("get_student_schema", "hod", {}))
    _assert("properties" in hod_text.lower(), f"HOD should access get_student_schema: {hod_text}")

    student_doc_text = asyncio.run(_run_mcp_tool("delete_department_document", "student", {"filename": "x.pdf"}))
    _assert("permission denied" in student_doc_text.lower(), f"Student must be denied doc delete: {student_doc_text}")


def _check_upload_endpoint_policy() -> None:
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    with ExitStack() as stack:
        stack.enter_context(patch("backend.api.upload.verify_firebase_token", return_value=_auth_user_for_role("student")))
        stack.enter_context(patch("backend.api.upload.db_client.get_user_profile", return_value=_profile_for_role("student")))
        response = client.post(
            "/upload_pdf",
            headers={"Authorization": "Bearer dev:student:23091A3349"},
            files={"file": ("student_try.pdf", pdf_bytes, "application/pdf")},
        )
        _assert(response.status_code == 403, f"Student upload should be forbidden: {response.status_code} {response.text}")


def _check_admin_endpoint_policy() -> None:
    with ExitStack() as stack:
        stack.enter_context(patch("backend.api.admin.verify_firebase_token", return_value=_auth_user_for_role("faculty")))
        stack.enter_context(patch("backend.api.admin.db_client.get_user_profile", return_value=_profile_for_role("faculty")))
        stack.enter_context(patch("backend.api.admin.db_client.list_all_students", return_value=[]))
        faculty_response = client.get("/admin/students", headers={"Authorization": "Bearer dev:faculty:FAC001"})
        _assert(faculty_response.status_code == 200, f"Faculty should access /admin/students: {faculty_response.status_code} {faculty_response.text}")

    with ExitStack() as stack:
        stack.enter_context(patch("backend.api.admin.verify_firebase_token", return_value=_auth_user_for_role("student")))
        stack.enter_context(patch("backend.api.admin.db_client.get_user_profile", return_value=_profile_for_role("student")))
        student_response = client.get("/admin/students", headers={"Authorization": "Bearer dev:student:23091A3349"})
        _assert(student_response.status_code == 403, f"Student should be forbidden /admin/students: {student_response.status_code} {student_response.text}")


def main() -> None:
    _check_mcp_policy_matrix()
    _check_upload_endpoint_policy()
    _check_admin_endpoint_policy()
    print("Role policy matrix verification passed.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Role policy matrix verification failed: {exc}")
        raise SystemExit(1)

