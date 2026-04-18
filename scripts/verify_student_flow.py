import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv(encoding="utf-8-sig")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.get_id_token import fetch_id_token


DEFAULT_QUESTIONS = [
    "Do I have backlogs?",
    "What is my CGPA?",
    "Am I placement ready?",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the real student Firebase auth flow against /me and /chat."
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("API_URL", "http://127.0.0.1:8000"),
        help="FastAPI base URL, for example http://127.0.0.1:8000",
    )
    parser.add_argument("--token", default="", help="Existing Firebase ID token")
    parser.add_argument("--email", default="", help="Firebase Auth email")
    parser.add_argument("--password", default="", help="Firebase Auth password")
    parser.add_argument(
        "--expect-reg-no",
        default="",
        help="Optional expected student reg_no for /me and /chat validation",
    )
    return parser.parse_args()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _raise_for_bad_status(response: requests.Response, label: str) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{label} returned non-JSON response: {response.text}") from exc

    if response.status_code >= 400:
        raise RuntimeError(f"{label} failed with status {response.status_code}: {body}")

    return body


def _verify_me(api_url: str, token: str, expected_reg_no: str) -> dict:
    try:
        response = requests.get(
            f"{api_url.rstrip('/')}/me",
            headers=_auth_headers(token),
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            f"GET /me could not reach the backend at {api_url}. "
            "Start FastAPI with AUTH_MODE=firebase before running this check."
        ) from exc
    body = _raise_for_bad_status(response, "GET /me")

    if body.get("status") != "answered":
        raise RuntimeError(f"GET /me returned unexpected status: {body}")

    data = body.get("data", {})
    if data.get("role") != "student":
        raise RuntimeError(f"GET /me expected role=student, got: {body}")

    if expected_reg_no and str(data.get("reg_no", "")).upper() != expected_reg_no.upper():
        raise RuntimeError(
            f"GET /me returned reg_no={data.get('reg_no')}, expected {expected_reg_no}"
        )

    return body


def _verify_chat(api_url: str, token: str, question: str, expected_reg_no: str) -> dict:
    try:
        response = requests.post(
            f"{api_url.rstrip('/')}/chat",
            json={"message": question},
            headers=_auth_headers(token),
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            f"POST /chat could not reach the backend at {api_url}. "
            "Start FastAPI with AUTH_MODE=firebase before running this check."
        ) from exc
    body = _raise_for_bad_status(response, f"POST /chat [{question}]")

    if body.get("status") != "answered":
        raise RuntimeError(f"POST /chat failed for '{question}': {body}")

    if body.get("intent") != "student_data_query":
        raise RuntimeError(f"POST /chat returned wrong intent for '{question}': {body}")

    if body.get("tool_used") != "get_student_data":
        raise RuntimeError(f"POST /chat returned wrong tool for '{question}': {body}")

    if "duration_ms" not in body:
        raise RuntimeError(f"POST /chat missing duration_ms for '{question}': {body}")

    data = body.get("data", {})
    if expected_reg_no and str(data.get("reg_no", "")).upper() != expected_reg_no.upper():
        raise RuntimeError(
            f"POST /chat returned reg_no={data.get('reg_no')} for '{question}', "
            f"expected {expected_reg_no}"
        )

    return body


def _resolve_token(args: argparse.Namespace) -> str:
    if args.token.strip():
        return args.token.strip()

    if args.email.strip() and args.password:
        return fetch_id_token(args.email.strip(), args.password)

    raise RuntimeError("Provide --token, or both --email and --password.")


def main() -> None:
    args = parse_args()
    token = _resolve_token(args)

    print("Verifying GET /me ...")
    me_body = _verify_me(args.api_url, token, args.expect_reg_no)
    print(json.dumps(me_body, indent=2))

    for question in DEFAULT_QUESTIONS:
        print(f"\nVerifying POST /chat -> {question}")
        chat_body = _verify_chat(args.api_url, token, question, args.expect_reg_no)
        print(json.dumps(chat_body, indent=2))

    print("\nStudent auth flow verification passed.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Verification failed: {exc}")
        raise SystemExit(1)
