import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, status

from backend.auth.firebase_auth import verify_firebase_token
from backend.core.config import settings
from backend.llm.responses import build_response
from backend.core.audit import log_action
from backend.database.neo4j_client import db_client
from backend.core.policy import can_manage_documents, normalize_role



router = APIRouter()


@router.post("/upload_pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    visibility: str = Form("student"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    started_at = time.perf_counter()
    auth_user = verify_firebase_token(authorization)
    profile = await asyncio.to_thread(db_client.get_user_profile, auth_user)
    role = normalize_role((profile or {}).get("role", auth_user.role_hint))

    if not can_manage_documents(role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty or HOD accounts can upload or change department documents.",
        )


    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported.",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / Path(file.filename).name

    content = await file.read()
    file_path.write_bytes(content)

    try:
        from backend.rag.ingest import ingest_pdf

        result = await asyncio.wait_for(
            asyncio.to_thread(ingest_pdf, file_path, visibility),
            timeout=settings.rag_tool_timeout_seconds,
        )
    except asyncio.TimeoutError:
        return build_response(
            status="error",
            intent="document_query",
            answer="PDF indexing took too long. Please try again.",
            error="timeout",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
        )
    except RuntimeError as exc:
        return build_response(
            status="error",
            intent="document_query",
            answer=str(exc),
            error="rag_unavailable",
            duration_ms=int((time.perf_counter() - started_at) * 1000),
        )

    log_action(auth_user.uid, role, "upload_document", file.filename, None, "success")
    chunks = int(result.get("chunks", 0))
    return build_response(
        status="answered",
        intent="document_query",
        answer=f"Document indexed successfully. Extracted {chunks} pieces of information.",
        data=result,
        tool_used="ingest_pdf",
        duration_ms=int((time.perf_counter() - started_at) * 1000),
    )

@router.delete("/documents/{filename}")
async def delete_document(
    filename: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    started_at = time.perf_counter()
    auth_user = verify_firebase_token(authorization)
    profile = await asyncio.to_thread(db_client.get_user_profile, auth_user)
    role = normalize_role((profile or {}).get("role", auth_user.role_hint))

    if not can_manage_documents(role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only faculty or HOD accounts can upload or change department documents.",
        )

    safe_name = Path(filename).name
    file_path = Path(settings.upload_dir) / safe_name
    removed_file = False
    if file_path.exists():
        file_path.unlink()
        removed_file = True

    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        collection = client.get_collection(name="department_docs")
        collection.delete(where={"source": safe_name})
    except Exception:
        pass

    log_action(auth_user.uid, role, "delete_document", safe_name, None, "success")
    if removed_file:
        answer = f"Document {safe_name} deleted successfully."
    else:
        answer = f"Document {safe_name} was not found. Index cleanup attempted."
    return build_response(
        status="answered",
        intent="document_query",
        answer=answer,
        data={"filename": safe_name, "deleted": removed_file},
        tool_used="delete_document",
        duration_ms=int((time.perf_counter() - started_at) * 1000),
    )
