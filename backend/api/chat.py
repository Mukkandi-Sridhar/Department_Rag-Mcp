import asyncio
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.auth.firebase_auth import verify_firebase_token
from backend.config import settings
from backend.database.firestore import db_client
from backend.database.validation import validate_student
from backend.llm.formatter import format_student_answer
from backend.llm.intent import detect_intent, normalize_query
from backend.llm.responses import build_response
from backend.tools.tools import get_student_data, retrieve_documents


router = APIRouter()


class ChatRequest(BaseModel):
    message: str


def _duration_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _base_log(
    *,
    uid: str | None,
    reg_no: str | None,
    message: str,
    intent: str,
    tool_used: str | None,
    response: dict[str, Any],
) -> dict[str, Any]:
    return {
        "uid": uid,
        "reg_no": reg_no,
        "message": message,
        "intent": intent,
        "tool_used": tool_used,
        "status": response["status"],
        "duration_ms": response["duration_ms"],
        "error": response["error"],
    }


def _safe_log(entry: dict[str, Any]) -> None:
    try:
        db_client.log_chat(entry)
    except Exception:
        # Logging must never break the user request.
        pass


def _is_google_api_error(exc: Exception) -> bool:
    return exc.__class__.__module__.startswith("google.api_core")


def _finish(
    *,
    started_at: float,
    uid: str | None,
    reg_no: str | None,
    message: str,
    intent: str,
    status: str,
    answer: str,
    data: dict[str, Any] | None = None,
    tool_used: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    response = build_response(
        status=status,
        intent=intent,
        answer=answer,
        data=data,
        tool_used=tool_used,
        error=error,
        duration_ms=_duration_ms(started_at),
    )
    _safe_log(
        _base_log(
            uid=uid,
            reg_no=reg_no,
            message=message,
            intent=intent,
            tool_used=tool_used,
            response=response,
        )
    )
    return response


@router.post("/chat")
async def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    started_at = time.perf_counter()
    intent = "unknown"
    uid = None
    reg_no = None
    current_tool = None
    original_message = request.message or ""
    query = normalize_query(original_message)

    if not query:
        return _finish(
            started_at=started_at,
            uid=uid,
            reg_no=reg_no,
            message=original_message,
            intent="unclear_query",
            status="needs_clarification",
            answer="Please enter a valid question.",
        )

    try:
        auth_user = verify_firebase_token(authorization)
        uid = auth_user.uid

        profile = await asyncio.wait_for(
            asyncio.to_thread(db_client.get_user_profile, auth_user),
            timeout=settings.student_tool_timeout_seconds,
        )

        if not profile:
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=reg_no,
                message=original_message,
                intent=intent,
                status="error",
                answer="Your user profile was not found. Please contact the department admin.",
                error="profile_not_found",
            )

        role = str(profile.get("role", "")).lower()
        reg_no = str(profile.get("reg_no", "")).strip().upper()

        if role in {"faculty", "hod"}:
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=None,
                message=original_message,
                intent=intent,
                status="error",
                answer=f"{role.upper()} login is recognized, but {role.upper()} chat tools are not enabled yet.",
                data={
                    "role": role,
                    "faculty_id": str(profile.get("faculty_id", "")).strip(),
                },
                error="role_tools_not_enabled",
            )

        if role != "student":
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=reg_no or None,
                message=original_message,
                intent=intent,
                status="error",
                answer="This role is not supported in the current version.",
                error="role_not_supported",
            )

        if not reg_no:
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=None,
                message=original_message,
                intent=intent,
                status="error",
                answer="Your student profile is not linked. Please contact the department admin.",
                error="profile_not_linked",
            )

        intent = detect_intent(query)

        if intent == "unclear_query":
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=reg_no,
                message=original_message,
                intent=intent,
                status="needs_clarification",
                answer=(
                    "You can ask things like: 'Do I have backlogs?', "
                    "'What is my CGPA?', 'Am I placement ready?', "
                    "or ask about a document."
                ),
            )

        if intent == "student_data_query":
            tool_used = "get_student_data"
            current_tool = tool_used
            raw_student = await asyncio.wait_for(
                asyncio.to_thread(get_student_data, reg_no),
                timeout=settings.student_tool_timeout_seconds,
            )

            if not raw_student:
                return _finish(
                    started_at=started_at,
                    uid=uid,
                    reg_no=reg_no,
                    message=original_message,
                    intent=intent,
                    status="error",
                    answer="Your student record was not found in the system.",
                    tool_used=tool_used,
                    error="student_record_not_found",
                )

            student = validate_student(raw_student)
            answer = format_student_answer(query, student)
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=reg_no,
                message=original_message,
                intent=intent,
                status="answered",
                answer=answer,
                data=student,
                tool_used=tool_used,
            )

        if intent == "document_query":
            tool_used = "retrieve_documents"
            current_tool = tool_used
            docs = await asyncio.wait_for(
                asyncio.to_thread(retrieve_documents, query),
                timeout=settings.rag_tool_timeout_seconds,
            )

            if not docs:
                return _finish(
                    started_at=started_at,
                    uid=uid,
                    reg_no=reg_no,
                    message=original_message,
                    intent=intent,
                    status="error",
                    answer="I could not find relevant information in the uploaded documents.",
                    tool_used=tool_used,
                    error="no_document_match",
                )

            answer = docs[0]["text"]
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=reg_no,
                message=original_message,
                intent=intent,
                status="answered",
                answer=answer,
                data={"sources": [doc.get("source", {}) for doc in docs]},
                tool_used=tool_used,
            )

        return _finish(
            started_at=started_at,
            uid=uid,
            reg_no=reg_no,
            message=original_message,
            intent=intent,
            status="error",
            answer="I could not route that request.",
            error="unsupported_intent",
        )

    except asyncio.TimeoutError:
        return _finish(
            started_at=started_at,
            uid=uid,
            reg_no=reg_no,
            message=original_message,
            intent=intent,
            status="error",
            answer="Request took too long. Please try again.",
            tool_used=current_tool,
            error="timeout",
        )
    except HTTPException as exc:
        return _finish(
            started_at=started_at,
            uid=uid,
            reg_no=reg_no,
            message=original_message,
            intent=intent,
            status="error",
            answer=str(exc.detail),
            error="auth_error",
        )
    except Exception as exc:
        if _is_google_api_error(exc):
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=reg_no,
                message=original_message,
                intent=intent,
                status="error",
                answer="Student data is temporarily unavailable. Please try again later.",
                tool_used=current_tool,
                error="firestore_unavailable",
            )

        return _finish(
            started_at=started_at,
            uid=uid,
            reg_no=reg_no,
            message=original_message,
            intent=intent,
            status="error",
            answer="I could not complete that request right now.",
            tool_used=current_tool,
            error="internal_error",
        )
