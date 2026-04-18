import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(encoding="utf-8-sig")

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    auth_mode = os.getenv("AUTH_MODE", "firebase").lower()
    data_backend = os.getenv("DATA_BACKEND", "firestore").lower()

    firebase_service_account_path = (
        os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        or ""
    )
    firebase_project_id = os.getenv("FIREBASE_PROJECT_ID", "")

    csv_path = Path(os.getenv("CSV_PATH", BASE_DIR / "students_data_new.csv"))
    local_log_path = Path(os.getenv("LOCAL_LOG_PATH", BASE_DIR / "logs" / "chat_logs.jsonl"))

    chroma_dir = Path(os.getenv("CHROMA_DIR", BASE_DIR / "storage" / "chroma"))
    upload_dir = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "storage" / "uploads"))

    student_tool_timeout_seconds = float(os.getenv("STUDENT_TOOL_TIMEOUT_SECONDS", "3"))
    rag_tool_timeout_seconds = float(os.getenv("RAG_TOOL_TIMEOUT_SECONDS", "8"))

    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    openai_chat_model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")


settings = Settings()
