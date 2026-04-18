import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv(encoding="utf-8-sig")

ROOT = Path(__file__).resolve().parent.parent
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
STUDENT_EMAIL = "student.test@rgmcet.edu.in"
STUDENT_REG_NO = "23091A3349"
STUDENT_NAME = "Mukkandi Sridhar"
STUDENT_BIRTH_YEAR = "2006"
STUDENT_LOGIN_CODE = "MUKK2006"


def _run_step(name: str, args: list[str], env: dict[str, str] | None = None) -> None:
    print(f"\n=== {name} ===")
    result = subprocess.run(
        args,
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed.")


def _run_optional_step(name: str, args: list[str], env: dict[str, str] | None = None) -> None:
    print(f"\n=== {name} ===")
    result = subprocess.run(
        args,
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        print(f"{name} did not complete. Continuing with the existing Firebase configuration.")


def _wait_for_backend(timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{API_URL}/health", timeout=5)
            if response.status_code == 200:
                return
            last_error = f"Unexpected status {response.status_code}: {response.text}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(1)

    raise RuntimeError(
        f"Backend did not become healthy at {API_URL}/health within {timeout_seconds}s. "
        f"Last error: {last_error}"
    )


def main() -> None:
    python = sys.executable

    _run_step(
        "Run local chat contract checks",
        [python, "scripts/run_chat_contract_checks.py"],
    )

    _run_optional_step(
        "Try to enable Firebase email/password auth",
        [python, "scripts/enable_firebase_auth.py"],
    )

    _run_step(
        "Create reference student auth user",
        [
            python,
            "scripts/create_auth_user.py",
            "--email",
            STUDENT_EMAIL,
            "--role",
            "student",
            "--reg-no",
            STUDENT_REG_NO,
            "--name",
            STUDENT_NAME,
            "--birth-year",
            STUDENT_BIRTH_YEAR,
        ],
    )

    env = os.environ.copy()
    env["AUTH_MODE"] = "firebase"
    env["DATA_BACKEND"] = "firestore"

    print("\n=== Start backend in Firebase mode ===")
    backend = subprocess.Popen(
        [python, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        _wait_for_backend()
        _run_step(
            "Verify real student flow",
            [
                python,
                "scripts/verify_student_flow.py",
                "--api-url",
                API_URL,
                "--email",
                STUDENT_EMAIL,
                "--password",
                STUDENT_LOGIN_CODE,
                "--expect-reg-no",
                STUDENT_REG_NO,
            ],
            env=env,
        )
    finally:
        backend.terminate()
        try:
            backend.wait(timeout=10)
        except subprocess.TimeoutExpired:
            backend.kill()

    print("\nStudent MVP bootstrap completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Bootstrap failed: {exc}")
        raise SystemExit(1)
