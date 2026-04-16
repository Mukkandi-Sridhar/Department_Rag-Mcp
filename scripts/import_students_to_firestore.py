import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.firebase_app import get_firestore_client, validate_service_account_file

CSV_PATH = Path(os.getenv("CSV_PATH", ROOT / "students_data_new.csv"))


def clean_row(row: dict) -> dict:
    return {
        "reg_no": str(row.get("reg_no", "")).strip().upper(),
        "name": str(row.get("name", "")).strip(),
        "program": str(row.get("program", "")).strip(),
        "gender": str(row.get("gender", "")).strip(),
        "category": str(row.get("category", "")).strip(),
        "performance": str(row.get("performance", "")).strip(),
        "cgpa": float(row.get("cgpa") or 0),
        "backlogs": int(float(row.get("backlogs") or 0)),
        "risk": str(row.get("risk", "")).strip(),
        "strengths": str(row.get("strengths", "")).strip(),
        "weaknesses": str(row.get("weaknesses", "")).strip(),
        "activities": str(row.get("activities", "")).strip(),
        "certifications": str(row.get("certifications", "")).strip(),
        "placement": str(row.get("placement", "")).strip(),
    }


def main() -> None:
    try:
        from google.api_core.exceptions import GoogleAPIError, PermissionDenied
    except ImportError:
        GoogleAPIError = Exception
        PermissionDenied = Exception

    validate_service_account_file()

    if not CSV_PATH.exists():
        raise RuntimeError(f"CSV file not found: {CSV_PATH}")

    db = get_firestore_client()
    count = 0

    try:
        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                student = clean_row(row)
                if not student["reg_no"]:
                    continue
                db.collection("students").document(student["reg_no"]).set(student)
                count += 1
    except PermissionDenied as exc:
        raise RuntimeError(
            "Firestore permission denied. Enable Cloud Firestore API for project "
            "'deptrag' and make sure Firestore is created in the Firebase console."
        ) from exc
    except GoogleAPIError as exc:
        raise RuntimeError(f"Firestore import failed: {exc}") from exc

    print(f"Imported {count} students into Firestore.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Import failed: {exc}")
        raise SystemExit(1)
