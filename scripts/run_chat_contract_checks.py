import time
import json
from contextlib import ExitStack
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app
from backend.auth.firebase_auth import AuthUser


client = TestClient(app)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _parse_sse_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        line = block.strip()
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload:
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return events


def _post_chat(message: str, token: str = "Bearer test-token") -> list[dict]:
    response = client.post(
        "/chat",
        json={"message": message},
        headers={"Authorization": token},
    )
    _assert(response.status_code == 200, f"/chat returned status {response.status_code}: {response.text}")
    events = _parse_sse_events(response.text)
    _assert(events, f"/chat returned empty SSE payload: {response.text!r}")
    return events


def _error_text(events: list[dict]) -> str:
    for event in events:
        if event.get("type") == "error":
            return str(event.get("content", ""))
    return ""


def _chunk_text(events: list[dict]) -> str:
    return "".join(str(event.get("content", "")) for event in events if event.get("type") == "chunk")


def _fake_auth_user() -> AuthUser:
    return AuthUser(uid="firebase-student-1", email="23091a3349@rgmcet.edu.in")


def _check_empty_message() -> None:
    events = _post_chat("")
    error = _error_text(events)
    _assert("valid question" in error.lower(), f"Empty message failed: {events}")


def _check_invalid_token() -> None:
    with patch("backend.api.chat.verify_firebase_token", side_effect=HTTPException(status_code=401, detail="Invalid token")):
        events = _post_chat("Do I have backlogs?", token="Bearer invalid")
    error = _error_text(events)
    _assert("internal server error" in error.lower(), f"Invalid token path failed: {events}")


def _check_missing_profile() -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch("backend.api.chat.verify_firebase_token", return_value=_fake_auth_user())
        )
        stack.enter_context(
            patch("backend.api.chat.db_client.get_user_profile", return_value=None)
        )
        events = _post_chat("Do I have backlogs?")
    _assert("profile was not found" in _error_text(events).lower(), f"Missing profile failed: {events}")


def _check_missing_reg_no() -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch("backend.api.chat.verify_firebase_token", return_value=_fake_auth_user())
        )
        stack.enter_context(
            patch(
                "backend.api.chat.db_client.get_user_profile",
                return_value={"uid": "firebase-student-1", "role": "student", "email": "23091a3349@rgmcet.edu.in"},
            )
        )
        events = _post_chat("Do I have backlogs?")
    _assert("not linked" in _error_text(events).lower(), f"Missing reg_no failed: {events}")


def _check_graph_error() -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch("backend.api.chat.verify_firebase_token", return_value=_fake_auth_user())
        )
        stack.enter_context(
            patch(
                "backend.api.chat.db_client.get_user_profile",
                return_value={
                    "uid": "firebase-student-1",
                    "role": "student",
                    "email": "23091a3349@rgmcet.edu.in",
                    "reg_no": "23091A3349",
                },
            )
        )
        stack.enter_context(
            patch(
                "backend.api.chat.run_chat_graph",
                return_value={"status": "error", "intent": "student_data_query", "answer": "Student not found", "error": "not_found"},
            )
        )
        events = _post_chat("Do I have backlogs?")

    _assert("student not found" in _error_text(events).lower(), f"Graph error path failed: {events}")


def _slow_student_lookup(_reg_no: str):
    time.sleep(0.2)
    return {
        "reg_no": "23091A3349",
        "name": "Mukkandi Sridhar",
        "cgpa": 7.83,
        "backlogs": 0,
        "risk": "Medium",
        "performance": "Good Performer",
        "placement": "Placement possible after improvement",
    }


def _check_timeout() -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch("backend.api.chat.verify_firebase_token", return_value=_fake_auth_user())
        )
        stack.enter_context(patch("backend.api.chat.db_client.get_user_profile", side_effect=lambda *_: _slow_student_lookup("x")))
        stack.enter_context(patch("backend.api.chat.settings.student_tool_timeout_seconds", 0.05))
        events = _post_chat("Do I have backlogs?")
    _assert("too long" in _error_text(events).lower(), f"Timeout failed: {events}")


def _check_greeting() -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch("backend.api.chat.verify_firebase_token", return_value=_fake_auth_user())
        )
        stack.enter_context(
            patch(
                "backend.api.chat.db_client.get_user_profile",
                return_value={
                    "uid": "firebase-student-1",
                    "role": "student",
                    "email": "23091a3349@rgmcet.edu.in",
                    "reg_no": "23091A3349",
                },
            )
        )
        stack.enter_context(
            patch(
                "backend.api.chat.run_chat_graph",
                return_value={
                    "status": "answered",
                    "intent": "direct_response",
                    "tool_used": None,
                    "answer_prompt": None,
                    "answer": "Hello. I can help with your academics and department documents.",
                    "data": {},
                    "error": None,
                },
            )
        )
        events = _post_chat("hello")

    text = _chunk_text(events)
    _assert("hello" in text.lower(), f"Greeting answer failed: {events}")


def main() -> None:
    _check_empty_message()
    _check_invalid_token()
    _check_missing_profile()
    _check_missing_reg_no()
    _check_graph_error()
    _check_timeout()
    _check_greeting()
    print("Chat contract checks passed.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Contract checks failed: {exc}")
        raise SystemExit(1)
