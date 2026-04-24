import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.auth.firebase_auth import AuthUser
from backend.core.config import settings
from backend.core.firebase_app import get_firestore_client


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

    def update_student_data(self, reg_no: str, fields: dict[str, Any]) -> bool:
        reg_no = reg_no.strip().upper()
        if not fields:
            return True

        if settings.data_backend == "csv":
            return self._update_student_in_csv(reg_no, fields)

        db = self._get_firestore()
        doc_ref = db.collection("students").document(reg_no)
        if not doc_ref.get().exists:
            return False
            
        doc_ref.update(fields)
        return True

    def add_student(self, data: dict[str, Any]) -> bool:
        reg_no = data.get("reg_no", "").strip().upper()
        if not reg_no:
            return False

        if settings.data_backend == "csv":
            return self._add_student_to_csv(data)

        db = self._get_firestore()
        doc_ref = db.collection("students").document(reg_no)
        if doc_ref.get().exists:
            return False # already exists
            
        doc_ref.set(data)
        return True

    def remove_student(self, reg_no: str) -> bool:
        reg_no = reg_no.strip().upper()

        if settings.data_backend == "csv":
            return self._remove_student_from_csv(reg_no)

        db = self._get_firestore()
        doc_ref = db.collection("students").document(reg_no)
        if not doc_ref.get().exists:
            return False
            
        doc_ref.delete()
        return True

    def list_all_students(self) -> list[dict[str, Any]]:
        if settings.data_backend == "csv":
            return self._list_students_from_csv()

        db = self._get_firestore()
        docs = db.collection("students").stream()
        return [doc.to_dict() for doc in docs]

    def log_chat(self, entry: dict[str, Any]) -> None:
        entry = dict(entry)
        entry["created_at"] = datetime.now(timezone.utc).isoformat()

        if settings.data_backend == "csv":
            self._append_local_log(entry)
            return

        db = self._get_firestore()
        db.collection("chat_logs").add(entry)

    def get_chat_sessions(self, uid: str) -> list[dict[str, Any]]:
        if settings.data_backend == "csv":
            return []
        db = self._get_firestore()
        # Fetching sessions sub-collection for a user
        docs = db.collection("user_chats").document(uid).collection("sessions").order_by("updated_at", direction="DESCENDING").stream()
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]

    def get_chat_session_history(self, uid: str, session_id: str) -> list[dict[str, Any]]:
        if settings.data_backend == "csv":
            return []
        db = self._get_firestore()
        doc = db.collection("user_chats").document(uid).collection("sessions").document(session_id).get()
        if not doc.exists:
            return []
        return doc.to_dict().get("messages", [])

    def save_chat_turn(self, uid: str, session_id: str, message: str, answer: str, intent: str = None, tool_used: str = None) -> None:
        if settings.data_backend == "csv":
            return

        from firebase_admin import firestore
        db = self._get_firestore()
        doc_ref = db.collection("user_chats").document(uid).collection("sessions").document(session_id)
        
        # Consistent with frontend message structure + metadata
        now = datetime.now(timezone.utc).timestamp()
        chat_turn = {
            "query": message,
            "answer": answer,
            "intent": intent,
            "tool_used": tool_used,
            "timestamp": now
        }
        
        doc = doc_ref.get()
        update_data = {"updated_at": now}
        
        if not doc.exists:
            # Set initial title and creation time
            update_data["title"] = message[:40] + ("..." if len(message) > 40 else "")
            update_data["created_at"] = now
            doc_ref.set(update_data)
        else:
            doc_ref.update(update_data)
            
        doc_ref.update({
            "messages": firestore.ArrayUnion([chat_turn])
        })

    def _get_student_from_csv(self, reg_no: str) -> dict[str, Any] | None:
        path = Path(settings.csv_path)
        if not path.exists():
            raise RuntimeError(f"CSV file not found: {path}")

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                if row.get("reg_no", "").strip().upper() == reg_no:
                    return row

        return None
        
    def _list_students_from_csv(self) -> list[dict[str, Any]]:
        path = Path(settings.csv_path)
        if not path.exists():
            raise RuntimeError(f"CSV file not found: {path}")

        results = []
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                if row.get("reg_no"):
                    results.append(row)

        return results

    def _update_student_in_csv(self, reg_no: str, fields: dict[str, Any]) -> bool:
        # Atomic replace with tempfile
        path = Path(settings.csv_path)
        if not path.exists():
            return False
            
        found = False
        temp_fd, temp_path = tempfile.mkstemp(dir=path.parent, text=True)
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as infile, os.fdopen(temp_fd, "w", encoding="utf-8", newline="") as outfile:
                reader = csv.DictReader(infile)
                fieldnames = reader.fieldnames or ["reg_no", "name", "cgpa", "backlogs", "placement", "risk", "performance"]
                writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                writer.writeheader()
                for row in reader:
                    if row.get("reg_no", "").strip().upper() == reg_no:
                        row.update({k: str(v) for k, v in fields.items()})
                        found = True
                    writer.writerow(row)
            if found:
                os.replace(temp_path, path)
            else:
                os.remove(temp_path)
            return found
        except Exception:
            os.remove(temp_path)
            raise

    def _add_student_to_csv(self, data: dict[str, Any]) -> bool:
        path = Path(settings.csv_path)
        reg_no = data.get("reg_no", "").strip().upper()
        
        if not path.exists():
            # Create file
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(data.keys()))
                writer.writeheader()
                writer.writerow(data)
            return True
            
        # Ensure doesn't exist
        if self._get_student_from_csv(reg_no):
            return False
            
        # Append
        with path.open("a", encoding="utf-8", newline="") as f:
            reader_f = path.open("r", encoding="utf-8-sig")
            fieldnames = csv.DictReader(reader_f).fieldnames or list(data.keys())
            reader_f.close()
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow({k: data.get(k, "") for k in fieldnames})
        return True

    def _remove_student_from_csv(self, reg_no: str) -> bool:
        path = Path(settings.csv_path)
        if not path.exists():
            return False
            
        found = False
        temp_fd, temp_path = tempfile.mkstemp(dir=path.parent, text=True)
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as infile, os.fdopen(temp_fd, "w", encoding="utf-8", newline="") as outfile:
                reader = csv.DictReader(infile)
                fieldnames = reader.fieldnames or ["reg_no", "name", "cgpa", "backlogs", "placement", "risk", "performance"]
                writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                writer.writeheader()
                for row in reader:
                    if row.get("reg_no", "").strip().upper() == reg_no:
                        found = True
                    else:
                        writer.writerow(row)
            if found:
                os.replace(temp_path, path)
            else:
                os.remove(temp_path)
            return found
        except Exception:
            os.remove(temp_path)
            raise

    def _append_local_log(self, entry: dict[str, Any]) -> None:
        path = Path(settings.local_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=True) + "\n")


db_client = DatabaseClient()
