import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.auth.firebase_auth import AuthUser
from backend.config import settings
from backend.firebase_app import get_firestore_client


class DatabaseClient:
    def __init__(self) -> None:
        self._firestore_client = None

    def _get_firestore(self):
        if self._firestore_client is not None:
            return self._firestore_client

        self._firestore_client = get_firestore_client()
        return self._firestore_client

    def get_user_profile(self, auth_user: AuthUser) -> dict[str, Any] | None:
        if auth_user.role_hint == "student" and auth_user.reg_no_hint:
            return {
                "uid": auth_user.uid,
                "role": "student",
                "reg_no": auth_user.reg_no_hint,
                "email": auth_user.email,
            }

        if auth_user.role_hint in {"faculty", "hod"} and auth_user.faculty_id_hint:
            return {
                "uid": auth_user.uid,
                "role": auth_user.role_hint,
                "faculty_id": auth_user.faculty_id_hint,
                "email": auth_user.email,
            }

        if settings.data_backend == "csv":
            return None

        db = self._get_firestore()
        snapshot = db.collection("users").document(auth_user.uid).get()
        if not snapshot.exists:
            return None

        profile = snapshot.to_dict()
        profile["uid"] = auth_user.uid
        return profile

    def get_student_data(self, reg_no: str) -> dict[str, Any] | None:
        reg_no = reg_no.strip().upper()

        if settings.data_backend == "csv":
            return self._get_student_from_csv(reg_no)

        db = self._get_firestore()
        snapshot = db.collection("students").document(reg_no).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict()

    def log_chat(self, entry: dict[str, Any]) -> None:
        entry = dict(entry)
        entry["created_at"] = datetime.now(timezone.utc).isoformat()

        if settings.data_backend == "csv":
            self._append_local_log(entry)
            return

        db = self._get_firestore()
        db.collection("chat_logs").add(entry)

    def _get_student_from_csv(self, reg_no: str) -> dict[str, Any] | None:
        path = Path(settings.csv_path)
        if not path.exists():
            raise RuntimeError(f"CSV file not found: {path}")

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                if row.get("reg_no", "").strip().upper() == reg_no:
                    return row

        return None

    def _append_local_log(self, entry: dict[str, Any]) -> None:
        path = Path(settings.local_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=True) + "\n")


db_client = DatabaseClient()
