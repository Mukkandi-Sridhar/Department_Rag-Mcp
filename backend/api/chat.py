import asyncio
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.auth.firebase_auth import verify_firebase_token
from backend.config import settings
from backend.database.firestore import db_client
from backend.orchestration import run_chat_graph
from backend.llm.intent import normalize_query
from backend.llm.responses import build_response


router = APIRouter()


class ChatHistoryItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatHistoryItem] = Field(default_factory=list)


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
    history = [
        {
            "role": item.role.strip().lower(),
            "content": item.content.strip(),
        }
        for item in request.history
        if item.content.strip()
    ]

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
            role_label = "HOD" if role == "hod" else "Faculty"
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=None,
                message=original_message,
                intent=intent,
                status="error",
                answer=f"{role_label} login is recognized, but {role_label} chat tools are not enabled yet.",
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

        graph_result = await asyncio.to_thread(
            run_chat_graph,
            original_message=original_message,
            query=query,
            history=history,
            uid=uid,
            reg_no=reg_no,
            role=role,
        )
        intent = graph_result.get("intent", intent)
        current_tool = graph_result.get("tool_used")

        if not graph_result.get("status") or not graph_result.get("answer"):
            return _finish(
                started_at=started_at,
                uid=uid,
                reg_no=reg_no,
                message=original_message,
                intent=intent,
                status="error",
                answer="I could not route that request.",
                error="graph_incomplete",
            )

        return _finish(
            started_at=started_at,
            uid=uid,
            reg_no=reg_no,
            message=original_message,
            intent=intent,
            status=graph_result["status"],
            answer=graph_result["answer"],
            data=graph_result.get("data"),
            tool_used=current_tool,
            error=graph_result.get("error"),
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
