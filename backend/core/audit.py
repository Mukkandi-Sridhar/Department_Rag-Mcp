import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.core.firebase_app import get_firestore_client

def log_action(actor_uid: str, role: str, action: str, target: str, fields: dict | None, result: str) -> None:
    """Logs an administrative action (update/add/remove/upload) to file or Firestore."""
    entry = {
        "actor_uid": actor_uid,
        "role": role,
        "action": action,
        "target": target,
        "fields": fields,
        "result": result,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    if settings.data_backend == "csv":
        path = Path(settings.admin_action_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=True) + "\n")
    else:
        try:
            db = get_firestore_client()
            db.collection("audit_logs").add(entry)
        except Exception as e:
            # Audit log failure should ideally alert someone, but we silently proceed for now.
            print(f"Failed to write audit log to firestore: {e}")
