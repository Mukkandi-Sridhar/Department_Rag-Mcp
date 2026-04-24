import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app
from backend.auth.firebase_auth import AuthUser


client = TestClient(app)
MATCHING_QUESTION = "What does the policy say about internships?"
NO_MATCH_QUESTION = "What does the circular say about transport?"


class DummyEmbeddings:
    size = 8

    def _vector(self, text: str) -> list[float]:
        buckets = [0.0] * self.size
        for index, char in enumerate(text.lower()):
            buckets[index % self.size] += (ord(char) % 31) / 31.0
        length = max(len(text), 1)
        return [value / length for value in buckets]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _parse_sse_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        line = block.strip()
        if not line.startswith("data: "):
            continue
        try:
            events.append(json.loads(line[6:].strip()))
        except json.JSONDecodeError:
            continue
    return events


def _chunk_text(events: list[dict]) -> str:
    return "".join(str(event.get("content", "")) for event in events if event.get("type") == "chunk")


def _first_error(events: list[dict]) -> str:
    for event in events:
        if event.get("type") == "error":
            return str(event.get("content", ""))
    return ""


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(lines: list[str]) -> bytes:
    content_lines = ["BT", "/F1 12 Tf", "50 760 Td"]
    for index, line in enumerate(lines):
        if index:
            content_lines.append("0 -18 Td")
        content_lines.append(f"({_escape_pdf_text(line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            b"5 0 obj\n<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream\nendobj\n"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def _fake_auth_user() -> AuthUser:
    return AuthUser(
        uid="dev-hod-fac001",
        email="hod@rgmcet.edu.in",
        faculty_id_hint="FAC001",
        role_hint="hod",
    )


def _clean_chroma_state() -> None:
    from chromadb.api.client import SharedSystemClient

    SharedSystemClient.clear_system_cache()


def main() -> None:
    sample_lines = [
        "Placement policy for CSE AI and ML students.",
        "Students with zero backlogs and CGPA above 7.0 are eligible for campus placement drives.",
        "Internships are encouraged before the placement season begins.",
    ]

    class _Chunk:
        def __init__(self, content: str):
            self.content = content

    class _FakeStreamingClient:
        async def astream(self, _messages):
            yield _Chunk("The policy says internships are encouraged before the placement season begins.")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_path = Path(temp_dir)
        uploads_dir = temp_path / "uploads"
        chroma_dir = temp_path / "chroma"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        pdf_bytes = _build_pdf(sample_lines)

        with patch("backend.api.upload.verify_firebase_token", return_value=_fake_auth_user()), \
            patch("backend.api.chat.verify_firebase_token", return_value=_fake_auth_user()), \
            patch("backend.api.upload.settings.upload_dir", uploads_dir), \
            patch("backend.api.upload.settings.chroma_dir", chroma_dir), \
            patch("backend.rag.ingest.settings.chroma_dir", chroma_dir), \
            patch("backend.rag.retrieve.settings.chroma_dir", chroma_dir), \
            patch("backend.rag.ingest.get_embeddings", return_value=DummyEmbeddings()), \
            patch("backend.rag.retrieve.get_embeddings", return_value=DummyEmbeddings()), \
            patch("backend.llm.brain.get_streaming_client", return_value=_FakeStreamingClient()), \
            patch(
                "backend.api.chat.run_chat_graph",
                side_effect=[
                    {
                        "status": "answered",
                        "intent": "document_query",
                        "tool_used": "search_department_documents",
                        "answer_prompt": [{"role": "system", "content": "Use provided policy snippets."}],
                        "data": {"sources": ["placement_policy.pdf"]},
                        "error": None,
                    },
                    {
                        "status": "error",
                        "intent": "document_query",
                        "tool_used": "search_department_documents",
                        "answer": "No relevant documents found.",
                        "error": "no_document_match",
                    },
                ],
            ):

            _clean_chroma_state()

            upload_response = client.post(
                "/upload_pdf",
                headers={"Authorization": "Bearer dev:23091A3349"},
                files={"file": ("placement_policy.pdf", pdf_bytes, "application/pdf")},
            )
            upload_body = upload_response.json()
            _assert(upload_response.status_code == 200, f"Upload status failed: {upload_body}")
            _assert(upload_body["status"] == "answered", f"Upload failed: {upload_body}")
            _assert(upload_body["tool_used"] == "ingest_pdf", f"Upload tool failed: {upload_body}")

            match_response = client.post(
                "/chat",
                headers={"Authorization": "Bearer dev:23091A3349"},
                json={"message": MATCHING_QUESTION},
            )
            match_events = _parse_sse_events(match_response.text)
            _assert(match_response.status_code == 200, f"Match status failed: {match_response.text}")
            _assert(any(e.get("type") == "done" and e.get("intent") == "document_query" for e in match_events), f"Match intent failed: {match_events}")
            _assert("placement" in _chunk_text(match_events).lower(), f"Match answer weak: {match_events}")

            no_match_response = client.post(
                "/chat",
                headers={"Authorization": "Bearer dev:23091A3349"},
                json={"message": NO_MATCH_QUESTION},
            )
            no_match_events = _parse_sse_events(no_match_response.text)
            _assert(no_match_response.status_code == 200, f"No-match status failed: {no_match_response.text}")
            _assert("no relevant documents found" in _first_error(no_match_events).lower(), f"No-match error failed: {no_match_events}")

    print("Document flow verification passed.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"Document flow verification failed: {exc}")
        raise SystemExit(1)
