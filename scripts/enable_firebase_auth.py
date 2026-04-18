import json
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2 import service_account


load_dotenv(encoding="utf-8-sig")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.firebase_app import validate_service_account_file


CONFIG_BASE = "https://identitytoolkit.googleapis.com"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def _get_access_token() -> tuple[str, str]:
    info = validate_service_account_file()
    credentials = service_account.Credentials.from_service_account_file(
        info["path"],
        scopes=SCOPES,
    )
    credentials.refresh(Request())
    return credentials.token, info["project_id"]


def _headers(access_token: str, project_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _initialize_auth(access_token: str, project_id: str) -> None:
    project_name = f"projects/{project_id}"
    url = f"{CONFIG_BASE}/v2/{project_name}/identityPlatform:initializeAuth"
    response = requests.post(url, headers=_headers(access_token, project_id), timeout=30)
    if response.status_code in {200, 204}:
        print("Identity Platform initialization succeeded.")
        return

    body = response.text
    if "BILLING_NOT_ENABLED" in body:
        raise RuntimeError(
            "Identity Platform initialization requires billing to be enabled for this project. "
            "If you are using standard Firebase Authentication, open Firebase Console > "
            "Authentication > Get started > Sign-in method > Email/Password and enable it there."
        )
    if response.status_code == 409:
        print("Identity Platform already initialized.")
        return

    raise RuntimeError(f"Identity Platform initialization failed: {body}")


def _get_config(access_token: str, project_id: str) -> requests.Response:
    config_name = quote(f"projects/{project_id}/config", safe="")
    url = f"{CONFIG_BASE}/admin/v2/{config_name}"
    return requests.get(url, headers=_headers(access_token, project_id), timeout=30)


def _enable_email_password(access_token: str, project_id: str) -> dict:
    config_name = f"projects/{project_id}/config"
    encoded_name = quote(config_name, safe="")
    update_mask = "signIn.email.enabled,signIn.email.passwordRequired"
    url = f"{CONFIG_BASE}/admin/v2/{encoded_name}?updateMask={update_mask}"
    payload = {
        "name": config_name,
        "signIn": {
            "email": {
                "enabled": True,
                "passwordRequired": True,
            }
        },
    }
    response = requests.patch(
        url,
        headers=_headers(access_token, project_id),
        data=json.dumps(payload),
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to enable email/password auth: {response.text}")

    return response.json()


def main() -> None:
    access_token, project_id = _get_access_token()

    config_response = _get_config(access_token, project_id)
    if config_response.status_code == 404:
        print("Identity Platform config not found. Initializing auth first...")
        _initialize_auth(access_token, project_id)
    elif config_response.status_code != 200:
        raise RuntimeError(f"Could not read auth config: {config_response.text}")

    config = _enable_email_password(access_token, project_id)
    sign_in = config.get("signIn", {})
    email = sign_in.get("email", {})

    if not email.get("enabled") or not email.get("passwordRequired"):
        raise RuntimeError(
            "Email/password auth update did not stick. Check project IAM and auth settings."
        )

    print("Email/password auth is enabled.")
    print(json.dumps({"project": project_id, "signIn": sign_in}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Enable auth failed: {exc}")
        raise SystemExit(1)
