# Department AI MVP

This repository is now shaped around one production-style vertical slice:

- FastAPI backend
- Firebase Authentication gate
- Firestore-ready student data access
- Local CSV fallback for development only
- Rule-based intent detection
- Strict response builder
- Student data validation before response
- Tool timeouts
- Structured request logging
- PDF-only RAG with Chroma
- Thin Gradio test UI

The goal is not to build every department feature at once. Phase 1 proves one safe flow end to end:

```text
Student logs in
Frontend calls /chat
Backend verifies identity
Backend gets the student's reg_no
Intent is detected
Tool is called with timeout
Response is validated and structured
Request is logged
JSON is returned
```

## Phase 1 Scope

Supported questions:

- "Do I have backlogs?"
- "Do I have pending subjects?"
- "What is my CGPA?"
- "Am I placement ready?"
- Department document/PDF questions after PDF upload

Not included yet:

- Faculty flows
- HOD analytics
- Marks module
- Multi-turn clarification sessions
- Dashboards

## Project Structure

```text
backend/
  main.py                 FastAPI app
  api/chat.py             /chat pipeline
  api/upload.py           /upload_pdf endpoint
  auth/firebase_auth.py   Firebase token verification and dev auth
  database/firestore.py   Firestore access plus local CSV fallback
  database/validation.py  Student data validation
  llm/intent.py           Rule-based intent detection
  llm/formatter.py        Deterministic answer formatting
  llm/responses.py        Single response builder
  rag/                    PDF ingestion and retrieval
  tools/tools.py          Phase 1 tool layer

frontend/gradio_app.py    Thin UI that calls FastAPI
frontend/firebase_app.js  Firebase Web SDK config for future browser auth
scripts/import_students_to_firestore.py
students_data_new.csv     Seed/local development data
```

## Setup

Python 3.10+ is recommended.

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env`.

For local development against Firestore with dev tokens, use:

```env
AUTH_MODE=dev
DATA_BACKEND=firestore
FIREBASE_SERVICE_ACCOUNT_PATH=C:\Users\sridh\Downloads\deptrag-firebase-adminsdk-fbsvc-688bd70b2e.json
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\sridh\Downloads\deptrag-firebase-adminsdk-fbsvc-688bd70b2e.json
FIREBASE_PROJECT_ID=deptrag
```

In this mode, call `/chat` with:

```text
Authorization: Bearer dev:23091A3349
```

For production, use Firebase:

```env
AUTH_MODE=firebase
DATA_BACKEND=firestore
FIREBASE_SERVICE_ACCOUNT_PATH=C:\Users\sridh\Downloads\deptrag-firebase-adminsdk-fbsvc-688bd70b2e.json
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\sridh\Downloads\deptrag-firebase-adminsdk-fbsvc-688bd70b2e.json
FIREBASE_PROJECT_ID=deptrag
```

Production mode requires real Firebase ID tokens and `users/{uid}` documents with
`role` and `reg_no` fields. Dev mode skips `users/{uid}` and maps
`Bearer dev:<reg_no>` directly to a synthetic student profile.

Dev auth supports these local-only formats:

```text
Bearer dev:<reg_no>
Bearer dev:student:<reg_no>
Bearer dev:faculty:<faculty_id>
Bearer dev:hod:<faculty_id>
```

## Run Backend

```bash
uvicorn app:app --reload
```

Health check:

```bash
GET http://127.0.0.1:8000/health
```

Chat request:

```bash
POST http://127.0.0.1:8000/chat
Authorization: Bearer dev:23091A3349
Content-Type: application/json

{
  "message": "Do I have backlogs?"
}
```

Expected response shape:

```json
{
  "status": "answered",
  "intent": "student_data_query",
  "answer": "You currently have 0 backlogs.",
  "data": {
    "reg_no": "23091A3349",
    "name": "Mukkandi Sridhar",
    "cgpa": 7.83,
    "backlogs": 0,
    "risk": "Medium",
    "performance": "Good Performer",
    "placement": "Placement possible after improvement"
  },
  "tool_used": "get_student_data",
  "error": null,
  "duration_ms": 120
}
```

## Run Gradio Client

Start the backend first, then:

```bash
python frontend/gradio_app.py
```

Use `dev:23091A3349` as the token in local development.

## Firebase Web Config

The browser Firebase config is stored in `frontend/firebase_app.js`. Use it later
from a proper web frontend to sign in users and send Firebase ID tokens to
`/chat`:

```text
Authorization: Bearer <firebase_id_token>
```

This web config is not the service account. The backend still uses the Admin SDK
credentials from `GOOGLE_APPLICATION_CREDENTIALS`.

## Import Students To Firestore

After configuring Firebase credentials:

```bash
python scripts/import_students_to_firestore.py
```

This imports `students_data_new.csv` into:

```text
students/{reg_no}
```

Faculty records can be imported with:

```bash
python scripts/import_faculty_to_firestore.py
```

This imports the available faculty profiles into:

```text
faculty/{faculty_id}
```

Current seeded faculty includes one HOD profile:

```text
faculty/g_kishor_kumar
```

Create real Firebase Auth role mappings with:

```bash
python scripts/set_user_mapping.py --uid <firebase_uid> --role student --reg-no 23091A3349 --email <email>
python scripts/set_user_mapping.py --uid <firebase_uid> --role hod --faculty-id g_kishor_kumar --email kishorgulla@yahoo.co.in
```

Faculty and HOD logins are recognized by `/chat`, but their chat tools are not
enabled yet.

## API Contract

Every response must go through `build_response()` and follow this shape:

```json
{
  "status": "answered | needs_clarification | error",
  "intent": "student_data_query | document_query | unclear_query | unknown",
  "answer": "User-facing answer",
  "data": {},
  "tool_used": "get_student_data | retrieve_documents | null",
  "error": null,
  "duration_ms": 120
}
```

## Security Notes

- Do not commit `.env`.
- Do not copy the Firebase service-account JSON into this repository.
- Rotate any OpenAI or Gemini key that was ever pushed or blocked by GitHub push protection.
- Student data is not stored in Chroma.
- Structured facts come from Firestore in production.
- PDF/circular/syllabus answers come from RAG.
