import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.firebase_app import get_firestore_client, validate_service_account_file


def build_mapping(args: argparse.Namespace) -> dict:
    role = args.role.lower()
    mapping = {
        "uid": args.uid,
        "role": role,
        "email": args.email or "",
    }
    if getattr(args, "login_code", ""):
        mapping["login_code"] = args.login_code.strip().upper()

    if role == "student":
        if not args.reg_no:
            raise RuntimeError("--reg-no is required for role=student")
        mapping["reg_no"] = args.reg_no.strip().upper()
        return mapping

    if role in {"faculty", "hod"}:
        if not args.faculty_id:
            raise RuntimeError("--faculty-id is required for role=faculty or role=hod")
        mapping["faculty_id"] = args.faculty_id.strip()
        return mapping

    raise RuntimeError("role must be one of: student, faculty, hod")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update a Firestore users/{uid} role mapping."
    )
    parser.add_argument("--uid", required=True, help="Firebase Auth UID")
    parser.add_argument("--role", required=True, choices=["student", "faculty", "hod"])
    parser.add_argument("--email", default="", help="User email for reference")
    parser.add_argument("--reg-no", default="", help="Student register number")
    parser.add_argument("--faculty-id", default="", help="Faculty document ID")
    parser.add_argument(
        "--login-code",
        default="",
        help="Optional college login code, e.g. MUKK2006",
    )
    return parser.parse_args()


def main() -> None:
    validate_service_account_file()
    args = parse_args()
    mapping = build_mapping(args)

    db = get_firestore_client()
    db.collection("users").document(args.uid).set(mapping)
    print(f"Updated users/{args.uid} with role={mapping['role']}.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Mapping failed: {exc}")
        raise SystemExit(1)
