import argparse
import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv


load_dotenv(encoding="utf-8-sig")

DEFAULT_FIREBASE_WEB_API_KEY = "AIzaSyDPlsZ8EEULeLC-zkz_eS-U2NGAIOhpV7k"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Get a Firebase ID token using email/password auth."
    )
    parser.add_argument("--email", required=True, help="Firebase Auth email")
    parser.add_argument("--password", required=True, help="Firebase Auth password")
    parser.add_argument(
        "--api-key",
        default="",
        help="Optional Firebase Web API key. Falls back to FIREBASE_WEB_API_KEY or the project default.",
    )
    return parser.parse_args()


def resolve_firebase_web_api_key(explicit_api_key: str = "") -> str:
    return (
        explicit_api_key.strip()
        or os.getenv("FIREBASE_WEB_API_KEY", "").strip()
        or DEFAULT_FIREBASE_WEB_API_KEY
    )


def fetch_id_token(email: str, password: str, api_key: str = "") -> str:
    resolved_api_key = resolve_firebase_web_api_key(api_key)
    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={resolved_api_key}"
    )
    payload = json.dumps(
        {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        if "CONFIGURATION_NOT_FOUND" in error_body:
            raise RuntimeError(
                "Firebase Authentication is not enabled. Enable Authentication "
                "and the Email/Password provider in Firebase Console."
            ) from exc
        raise RuntimeError(f"Firebase login failed: {error_body}") from exc

    return body["idToken"]


def main() -> None:
    args = parse_args()

    try:
        print(fetch_id_token(args.email, args.password, args.api_key))
    except RuntimeError as exc:
        print(f"Login failed: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
