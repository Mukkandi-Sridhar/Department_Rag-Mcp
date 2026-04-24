import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(encoding="utf-8-sig")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.firebase_app import get_firestore_client, initialize_firebase_app
from scripts.set_user_mapping import build_mapping


TITLE_WORDS = {
    "dr",
    "mr",
    "mrs",
    "ms",
    "prof",
    "professor",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Firebase Auth user and matching users/{uid} document."
    )
    parser.add_argument("--email", required=True, help="Firebase Auth email")
    parser.add_argument(
        "--password",
        default="",
        help=(
            "Firebase Auth password. If omitted, the script generates the login "
            "code from first 4 letters of name + birth year, for example MUKK2006."
        ),
    )
    parser.add_argument("--role", required=True, choices=["student", "faculty", "hod"])
    parser.add_argument("--reg-no", default="", help="Student register number")
    parser.add_argument("--faculty-id", default="", help="Faculty document ID")
    parser.add_argument("--name", default="", help="Name used for generated login code")
    parser.add_argument(
        "--date-of-birth",
        default="",
        help="Date of birth used for generated login code, e.g. 2006-04-15",
    )
    parser.add_argument(
        "--birth-year",
        default="",
        help="Birth year used for generated login code, e.g. 2006",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and print the login mapping without creating Firebase Auth user.",
    )
    return parser.parse_args()


def generate_login_code(name: str, date_of_birth: str = "", birth_year: str = "") -> str:
    if date_of_birth:
        return date_of_birth.strip()
    return "15082006"


def load_profile_defaults(args: argparse.Namespace) -> dict:
    if args.role == "student" and args.reg_no:
        db = get_firestore_client()
        snapshot = db.collection("students").document(args.reg_no.strip().upper()).get()
        return snapshot.to_dict() if snapshot.exists else {}

    if args.role in {"faculty", "hod"} and args.faculty_id:
        db = get_firestore_client()
        snapshot = db.collection("faculty").document(args.faculty_id.strip()).get()
        return snapshot.to_dict() if snapshot.exists else {}

    return {}


def resolve_password_and_login_code(args: argparse.Namespace) -> tuple[str, str]:
    if args.password:
        return args.password, args.password

    if args.role == "student" and args.reg_no:
        pwd = args.reg_no.strip().lower()
        return pwd, pwd
        
    return "CSEAIML", "CSEAIML"


def get_or_create_user(email: str, password: str):
    from firebase_admin import auth

    try:
        user = auth.get_user_by_email(email)
        auth.update_user(user.uid, password=password, disabled=False)
        return user, False
    except auth.UserNotFoundError:
        user = auth.create_user(email=email, password=password, disabled=False)
        return user, True
    except Exception as exc:
        message = str(exc)
        if "CONFIGURATION_NOT_FOUND" in message or "No auth provider found" in message:
            raise RuntimeError(
                "Firebase Authentication is not enabled for project 'deptrag'. "
                "Open Firebase Console > Authentication > Get started, then enable "
                "the Email/Password sign-in provider."
            ) from exc
        raise


def main() -> None:
    initialize_firebase_app()
    args = parse_args()
    password, login_code = resolve_password_and_login_code(args)

    if args.dry_run:
        preview_args = argparse.Namespace(
            uid="<firebase_uid>",
            role=args.role,
            email=args.email,
            reg_no=args.reg_no,
            faculty_id=args.faculty_id,
            login_code=login_code,
        )
        preview = build_mapping(preview_args)
        print("Dry run only. No Firebase Auth user was created.")
        print(f"Resolved email={args.email}")
        print(f"Resolved role={preview['role']}")
        print(f"Generated login_code={login_code or '<manual password supplied>'}")
        print(f"Mapping preview={preview}")
        return

    user, created = get_or_create_user(args.email, password)

    mapping_args = argparse.Namespace(
        uid=user.uid,
        role=args.role,
        email=args.email,
        reg_no=args.reg_no,
        faculty_id=args.faculty_id,
        login_code=login_code,
    )
    mapping = build_mapping(mapping_args)

    db = get_firestore_client()
    db.collection("users").document(user.uid).set(mapping)

    action = "Created" if created else "Updated"
    print(f"{action} Firebase Auth user: {args.email}")
    print(f"Mapped users/{user.uid} with role={mapping['role']}.")
    if login_code:
        print(f"Initial login_code={login_code}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Create user failed: {exc}")
        raise SystemExit(1)
