import json
from pathlib import Path

from backend.core.config import settings


def _resolve_service_account_path() -> Path:
    if not settings.firebase_service_account_path:
        raise RuntimeError(
            "Firebase service account path is not configured. Set "
            "FIREBASE_SERVICE_ACCOUNT_PATH or GOOGLE_APPLICATION_CREDENTIALS."
        )

    service_account_path = Path(settings.firebase_service_account_path).expanduser()
    if not service_account_path.exists():
        raise RuntimeError(
            f"Firebase service account file not found: {service_account_path}"
        )

    return service_account_path


def validate_service_account_file() -> dict:
    service_account_path = _resolve_service_account_path()

    try:
        with service_account_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Firebase service account file is not valid JSON.") from exc

    project_id = data.get("project_id")
    if settings.firebase_project_id and project_id != settings.firebase_project_id:
        raise RuntimeError(
            "Firebase project mismatch: service account belongs to "
            f"'{project_id}', but FIREBASE_PROJECT_ID is "
            f"'{settings.firebase_project_id}'."
        )

    if data.get("type") != "service_account":
        raise RuntimeError("Firebase credentials must be a service_account JSON file.")

    return {
        "project_id": project_id,
        "client_email": data.get("client_email"),
        "path": str(service_account_path),
    }


def initialize_firebase_app():
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        raise RuntimeError("firebase-admin is not installed") from exc

    if firebase_admin._apps:
        return firebase_admin.get_app()

    options = {}
    if settings.firebase_project_id:
        options["projectId"] = settings.firebase_project_id

    if settings.firebase_service_account_path:
        service_account_path = _resolve_service_account_path()
        validate_service_account_file()
        cred = credentials.Certificate(str(service_account_path))
        return firebase_admin.initialize_app(cred, options or None)

    return firebase_admin.initialize_app(options=options or None)


def get_firestore_client():
    initialize_firebase_app()

    try:
        from firebase_admin import firestore
    except ImportError as exc:
        raise RuntimeError("firebase-admin is not installed") from exc

    return firestore.client()
