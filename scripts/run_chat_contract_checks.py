import time
from contextlib import ExitStack
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app
from backend.auth.firebase_auth import AuthUser


client = TestClient(app)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _post_chat(message: str, token: str = "Bearer test-token") -> dict:
    response = client.post(
        "/chat",
        json={"message": message},
        headers={"Authorization": token},
    )
    body = response.json()
    _assert(response.status_code == 200, f"/chat returned status {response.status_code}: {body}")
    return body


def _fake_auth_user() -> AuthUser:
    return AuthUser(uid="firebase-student-1", email="student.test@rgmcet.edu.in")


def _student_route() -> dict:
    return {
        "intent": "student_data_query",
        "tool": "get_student_data",
        "answer": "",
    }


def _check_empty_message() -> None:
    body = _post_chat("")
    _assert(body["status"] == "needs_clarification", f"Empty message failed: {body}")
    _assert(body["intent"] == "unclear_query", f"Empty message intent failed: {body}")
    _assert(body["error"] is None, f"Empty message error failed: {body}")


def _check_invalid_token() -> None:
    body = _post_chat("Do I have backlogs?", token="Bearer invalid")
    _assert(body["status"] == "error", f"Invalid token status failed: {body}")
    _assert(body["error"] == "auth_error", f"Invalid token error failed: {body}")


def _check_missing_profile() -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch("backend.api.chat.verify_firebase_token", return_value=_fake_auth_user())
        )
        stack.enter_context(
            patch("backend.api.chat.db_client.get_user_profile", return_value=None)
        )
        body = _post_chat("Do I have backlogs?")

    _assert(body["status"] == "error", f"Missing profile status failed: {body}")
    _assert(body["error"] == "profile_not_found", f"Missing profile error failed: {body}")


def _check_missing_reg_no() -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch("backend.api.chat.verify_firebase_token", return_value=_fake_auth_user())
        )
        stack.enter_context(
            patch(
                "backend.api.chat.db_client.get_user_profile",
                return_value={"uid": "firebase-student-1", "role": "student", "email": "student.test@rgmcet.edu.in"},
            )
        )
        stack.enter_context(patch("backend.api.chat.route_query", return_value=_student_route()))
        body = _post_chat("Do I have backlogs?")

    _assert(body["status"] == "error", f"Missing reg_no status failed: {body}")
    _assert(body["error"] == "profile_not_linked", f"Missing reg_no error failed: {body}")


def _check_unknown_student() -> None:
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
                    "email": "student.test@rgmcet.edu.in",
                    "reg_no": "UNKNOWN123",
                },
            )
        )
        stack.enter_context(patch("backend.api.chat.route_query", return_value=_student_route()))
        stack.enter_context(patch("backend.api.chat.get_student_data", return_value=None))
        body = _post_chat("Do I have backlogs?")

    _assert(body["status"] == "error", f"Unknown student status failed: {body}")
    _assert(body["error"] == "student_record_not_found", f"Unknown student error failed: {body}")


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
        stack.enter_context(
            patch(
                "backend.api.chat.db_client.get_user_profile",
                return_value={
                    "uid": "firebase-student-1",
                    "role": "student",
                    "email": "student.test@rgmcet.edu.in",
                    "reg_no": "23091A3349",
                },
            )
        )
        stack.enter_context(patch("backend.api.chat.route_query", return_value=_student_route()))
        stack.enter_context(patch("backend.api.chat.get_student_data", side_effect=_slow_student_lookup))
        stack.enter_context(patch("backend.api.chat.settings.student_tool_timeout_seconds", 0.05))
        body = _post_chat("Do I have backlogs?")

    _assert(body["status"] == "error", f"Timeout status failed: {body}")
    _assert(body["error"] == "timeout", f"Timeout error failed: {body}")


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
                    "email": "student.test@rgmcet.edu.in",
                    "reg_no": "23091A3349",
                },
            )
        )
        stack.enter_context(
            patch(
                "backend.api.chat.route_query",
                return_value={
                    "intent": "direct_response",
                    "tool": None,
                    "answer": "Hello. I can help with your academics and department documents.",
                },
            )
        )
        body = _post_chat("hello")

    _assert(body["status"] == "answered", f"Greeting status failed: {body}")
    _assert(body["intent"] == "direct_response", f"Greeting intent failed: {body}")
    _assert("hello" in body["answer"].lower(), f"Greeting answer failed: {body}")


def main() -> None:
    _check_empty_message()
    _check_invalid_token()
    _check_missing_profile()
    _check_missing_reg_no()
    _check_unknown_student()
    _check_timeout()
    _check_greeting()
    print("Chat contract checks passed.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Contract checks failed: {exc}")
        raise SystemExit(1)
