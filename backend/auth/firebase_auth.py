from dataclasses import dataclass

from fastapi import HTTPException, status

from backend.config import settings
from backend.firebase_app import initialize_firebase_app


@dataclass(frozen=True)
class AuthUser:
    uid: str
    email: str | None = None
    reg_no_hint: str | None = None
    role_hint: str | None = None
    faculty_id_hint: str | None = None


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization must be Bearer <token>",
        )

    return token.strip()


def verify_firebase_token(authorization: str | None) -> AuthUser:
    token = _extract_bearer_token(authorization)

    if settings.auth_mode == "dev":
        if not token.startswith("dev:"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Use Bearer dev:<reg_no> in AUTH_MODE=dev",
            )
        parts = [part.strip() for part in token.split(":")]

        if len(parts) == 2:
            reg_no = parts[1].upper()
            return AuthUser(
                uid=f"dev-student-{reg_no}",
                email=None,
                reg_no_hint=reg_no,
                role_hint="student",
            )

        if len(parts) == 3 and parts[1].lower() == "student":
            reg_no = parts[2].upper()
            return AuthUser(
                uid=f"dev-student-{reg_no}",
                email=None,
                reg_no_hint=reg_no,
                role_hint="student",
            )

        if len(parts) == 3 and parts[1].lower() in {"faculty", "hod"}:
            role = parts[1].lower()
            faculty_id = parts[2]
            return AuthUser(
                uid=f"dev-{role}-{faculty_id}",
                email=None,
                role_hint=role,
                faculty_id_hint=faculty_id,
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Use Bearer dev:<reg_no>, dev:student:<reg_no>, "
                "dev:faculty:<faculty_id>, or dev:hod:<faculty_id> "
                "in AUTH_MODE=dev"
            ),
        )

    try:
        from firebase_admin import auth
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="firebase-admin is not installed",
        ) from exc

    try:
        initialize_firebase_app()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    try:
        decoded = auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase token",
        ) from exc

    return AuthUser(uid=decoded["uid"], email=decoded.get("email"))
