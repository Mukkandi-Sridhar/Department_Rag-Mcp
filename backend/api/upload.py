import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Header, HTTPException, UploadFile, status

from backend.auth.firebase_auth import verify_firebase_token
from backend.config import settings
from backend.llm.responses import build_response
from backend.rag.ingest import ingest_pdf


router = APIRouter()


@router.post("/upload_pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    started_at = time.perf_counter()
    verify_firebase_token(authorization)

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
        result = await asyncio.wait_for(
            asyncio.to_thread(ingest_pdf, file_path),
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

    return build_response(
        status="answered",
        intent="document_query",
        answer="PDF indexed successfully.",
        data=result,
        tool_used="ingest_pdf",
        duration_ms=int((time.perf_counter() - started_at) * 1000),
    )
