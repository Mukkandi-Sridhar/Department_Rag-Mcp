from dataclasses import dataclass

from fastapi import HTTPException, status

from backend.core.config import settings
from backend.core.firebase_app import initialize_firebase_app


@dataclass(frozen=True)
class AuthUser:
    uid: str
    email: str | None = None
    display_name: str | None = None
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

    initialize_firebase_app()

    try:
        from firebase_admin import auth
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        email = decoded_token.get("email")
        
        # Extract role/reg_no from custom claims if present
        role_hint = decoded_token.get("role", "student")
        reg_no_hint = decoded_token.get("reg_no")
        faculty_id_hint = decoded_token.get("faculty_id")

        return AuthUser(
            uid=uid,
            email=email,
            role_hint=role_hint,
            reg_no_hint=reg_no_hint,
            faculty_id_hint=faculty_id_hint,
            display_name=decoded_token.get("name", email)
        )
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Firebase token verification failed: {exc}")
        
        # Determine if this was a network failure (DNS, etc)
        details = "Invalid Firebase token"
        exc_str = str(exc).lower()
        if "getaddrinfo" in exc_str or "certificatefetcherror" in exc_str or "transporterror" in exc_str:
            details = "Network error during Firebase verification. Please check your internet connection."

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=details,
        ) from exc
