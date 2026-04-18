import asyncio
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from backend.auth.firebase_auth import verify_firebase_token
from backend.config import settings
from backend.database.firestore import db_client
from backend.llm.responses import build_response


router = APIRouter()


def _duration_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


@router.get("/me")
async def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    started_at = time.perf_counter()
    intent = "profile_query"
    uid = None

    try:
        auth_user = verify_firebase_token(authorization)
        uid = auth_user.uid
        profile = await asyncio.wait_for(
            asyncio.to_thread(db_client.get_user_profile, auth_user),
            timeout=settings.student_tool_timeout_seconds,
        )

        if not profile:
            return build_response(
                status="error",
                intent=intent,
                answer="Your user profile was not found. Please contact the department admin.",
                error="profile_not_found",
                duration_ms=_duration_ms(started_at),
            )

        safe_profile = {
            "uid": uid,
            "role": str(profile.get("role", "")).lower(),
            "email": profile.get("email") or auth_user.email or "",
        }
        if profile.get("reg_no"):
            safe_profile["reg_no"] = str(profile.get("reg_no", "")).strip().upper()
        if profile.get("faculty_id"):
            safe_profile["faculty_id"] = str(profile.get("faculty_id", "")).strip()

        return build_response(
            status="answered",
            intent=intent,
            answer="Profile loaded successfully.",
            data=safe_profile,
            tool_used="get_user_profile",
            duration_ms=_duration_ms(started_at),
        )

    except asyncio.TimeoutError:
        return build_response(
            status="error",
            intent=intent,
            answer="Request took too long. Please try again.",
            error="timeout",
            duration_ms=_duration_ms(started_at),
        )
    except HTTPException as exc:
        return build_response(
            status="error",
            intent=intent,
            answer=str(exc.detail),
            error="auth_error",
            duration_ms=_duration_ms(started_at),
        )
    except Exception:
        return build_response(
            status="error",
            intent=intent,
            answer="I could not load your profile right now.",
            error="internal_error",
            duration_ms=_duration_ms(started_at),
        )
