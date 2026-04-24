import asyncio
import time
from typing import Any
import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.auth.firebase_auth import verify_firebase_token
from backend.core.config import settings
from backend.database.neo4j_client import db_client
from backend.orchestration import run_chat_graph
from backend.llm.intent import normalize_query
from backend.llm.responses import build_response
from backend.core.policy import is_supported_role, normalize_role

router = APIRouter()

class ChatHistoryItem(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
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
    """Saves chat history to Firestore in sessions."""
    uid = entry.get("uid")
    session_id = entry.get("session_id")
    if not uid or not session_id:
        return

    try:
        db_client.save_chat_turn(
            uid=uid,
            session_id=session_id,
            message=entry.get("message"),
            answer=entry.get("answer"),
            intent=entry.get("intent"),
            tool_used=entry.get("tool_used")
        )
    except Exception as e:
        print(f"FAILED TO SAVE TO FIRESTORE: {e}")

def _finish(
    *,
    started_at: float,
    uid: str | None,
    reg_no: str | None,
    session_id: str | None,
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
    
    log_entry = _base_log(
        uid=uid,
        reg_no=reg_no,
        message=message,
        intent=intent,
        tool_used=tool_used,
        response=response,
    )
    log_entry["session_id"] = session_id
    log_entry["answer"] = answer
    _safe_log(log_entry)
    
    return response

@router.get("/session-history")
async def get_sessions(authorization: str | None = Header(default=None)):
    try:
        auth_user = verify_firebase_token(authorization)
        sessions = await asyncio.to_thread(db_client.get_chat_sessions, auth_user.uid)
        return {"status": "answered", "data": sessions}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.get("/session-history/{session_id}")
async def get_session_history(session_id: str, authorization: str | None = Header(default=None)):
    try:
        auth_user = verify_firebase_token(authorization)
        history = await asyncio.to_thread(db_client.get_chat_session_history, auth_user.uid, session_id)
        return {"status": "answered", "data": history}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/chat")
async def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    started_at = time.perf_counter()
    intent = "unknown"
    uid = None
    reg_no = None
    session_id = request.session_id
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
        payload = _finish(
            started_at=started_at,
            uid=uid,
            reg_no=reg_no,
            session_id=session_id,
            message=original_message,
            intent="unclear_query",
            status="needs_clarification",
            answer="Please enter a valid question.",
        )
        async def err_stream(): yield f"data: {json.dumps({'type': 'error', 'content': payload['answer']})}\n\n"
        return StreamingResponse(err_stream(), media_type="text/event-stream")

    try:
        auth_user = verify_firebase_token(authorization)
        uid = auth_user.uid

        profile = await asyncio.wait_for(
            asyncio.to_thread(db_client.get_user_profile, auth_user),
            timeout=settings.student_tool_timeout_seconds,
        )

        if not profile:
            payload = _finish(
                started_at=started_at,
                uid=uid,
                reg_no=reg_no,
                session_id=session_id,
                message=original_message,
                intent=intent,
                status="error",
                answer="Your user profile was not found. Please contact the department admin.",
                error="profile_not_found",
            )
            async def err_stream(): yield f"data: {json.dumps({'type': 'error', 'content': payload['answer']})}\n\n"
            return StreamingResponse(err_stream(), media_type="text/event-stream")

        role = normalize_role(profile.get("role"))
        reg_no = str(profile.get("reg_no", "")).strip().upper()

        if not is_supported_role(role):
            payload = _finish(
                started_at=started_at,
                uid=uid,
                reg_no=reg_no or None,
                session_id=session_id,
                message=original_message,
                intent=intent,
                status="error",
                answer="This role is not supported in the current version.",
                error="role_not_supported",
            )
            async def err_stream(): yield f"data: {json.dumps({'type': 'error', 'content': payload['answer']})}\n\n"
            return StreamingResponse(err_stream(), media_type="text/event-stream")

        if role == "student" and not reg_no:
            payload = _finish(
                started_at=started_at,
                uid=uid,
                reg_no=None,
                session_id=session_id,
                message=original_message,
                intent=intent,
                status="error",
                answer="Your student profile is not linked. Please contact the department admin.",
                error="profile_not_linked",
            )
            async def err_stream(): yield f"data: {json.dumps({'type': 'error', 'content': payload['answer']})}\n\n"
            return StreamingResponse(err_stream(), media_type="text/event-stream")

        async def stream_generator():
            # 1. HEARTBEAT
            yield f"data: {json.dumps({'type': 'chunk', 'content': ''})}\n\n"
            
            nonlocal intent, current_tool
            try:
                graph_result = await run_chat_graph(
                    original_message=original_message,
                    query=query,
                    history=history,
                    uid=uid,
                    reg_no=reg_no,
                    role=role,
                )
            except Exception as ge:
                yield f"data: {json.dumps({'type': 'error', 'content': f'Orchestration failed: {str(ge)}'})}\n\n"
                return

            intent = graph_result.get("intent", "unknown")
            current_tool = graph_result.get("tool_used")

            if graph_result.get("status") == "error":
                payload = _finish(
                    started_at=started_at, uid=uid, reg_no=reg_no, session_id=session_id, message=original_message,
                    intent=intent, status="error", answer=graph_result.get("answer", "Error"),
                    error=graph_result.get("error", "graph_error")
                )
                yield f"data: {json.dumps({'type': 'error', 'content': payload['answer']})}\n\n"
                return

            answer_prompt = graph_result.get("answer_prompt")
            if not answer_prompt:
                payload = _finish(
                    started_at=started_at, uid=uid, reg_no=reg_no, session_id=session_id, message=original_message,
                    intent=intent, status=graph_result.get("status", "error"), answer=graph_result.get("answer", "")
                )
                yield f"data: {json.dumps({'type': 'chunk', 'content': payload['answer']})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'intent': intent})}\n\n"
                return

            from backend.llm.brain import get_streaming_client
            client = get_streaming_client()
            full_answer = ""
            has_content = False
            
            try:
                async for chunk in client.astream(answer_prompt):
                    content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if content:
                        has_content = True
                        full_answer += content
                        yield f"data: {json.dumps({'type': 'chunk', 'content': content})}\n\n"
                
                if not has_content:
                    fallback = "I attempted to retrieve the records, but the database returned an empty result. Please try rephrasing."
                    full_answer = fallback
                    yield f"data: {json.dumps({'type': 'chunk', 'content': fallback})}\n\n"
                    
            except Exception:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Response streaming failed. Please try again.'})}\n\n"

            _finish(
                started_at=started_at, uid=uid, reg_no=reg_no, session_id=session_id, message=original_message,
                intent=intent, status="answered", answer=full_answer, 
                data=graph_result.get("data"), tool_used=current_tool
            )
            yield f"data: {json.dumps({'type': 'done', 'intent': intent})}\n\n"

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    except asyncio.TimeoutError:
        payload = _finish(
            started_at=started_at, uid=uid, reg_no=reg_no, session_id=session_id, message=original_message,
            intent=intent, status="error", answer="Request took too long. Please try again.", error="timeout"
        )
        async def err_stream(): yield f"data: {json.dumps({'type': 'error', 'content': payload['answer']})}\n\n"
        return StreamingResponse(err_stream(), media_type="text/event-stream")
    except Exception as exc:
        import traceback
        logger_msg = traceback.format_exc()
        print(f"Chat execution error: {logger_msg}")
        payload = _finish(
            started_at=started_at, uid=uid, reg_no=reg_no, session_id=session_id, message=original_message,
            intent=intent, status="error", answer="Internal Server Error", error="internal_error"
        )
        async def err_stream(): yield f"data: {json.dumps({'type': 'error', 'content': payload['answer']})}\n\n"
        return StreamingResponse(err_stream(), media_type="text/event-stream")
