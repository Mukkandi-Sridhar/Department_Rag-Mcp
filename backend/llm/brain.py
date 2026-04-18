import json
from functools import lru_cache
from typing import Any

from openai import OpenAI

from backend.config import settings


PLANNER_SYSTEM_PROMPT = """You are the retrieval planner for a college department AI assistant.
Return only valid JSON with this exact shape:
{
  "intent": "direct_response" | "student_data_query" | "document_query" | "unclear_query",
  "tool": "get_student_data" | "retrieve_documents" | null,
  "student_fields": ["reg_no" | "name" | "cgpa" | "backlogs" | "risk" | "performance" | "placement"],
  "answer": "short user-facing message"
}

Routing rules:
- Greetings, thanks, casual conversation, and simple help messages -> direct_response with no tool.
- Questions about the current student's backlogs, CGPA, placement readiness, risk, performance, or profile summary -> student_data_query with tool get_student_data.
- Questions about policies, syllabus, circulars, PDFs, regulations, or uploaded documents -> document_query with tool retrieve_documents.
- If the user is ambiguous and you need them to ask more clearly -> unclear_query with no tool and a helpful guidance message.

Field-selection rules:
- For student_data_query, include only the student fields truly needed to answer the question.
- Do not include extra student fields just because they exist.
- For document_query, direct_response, and unclear_query, student_fields must be [].

Mandatory routing examples:
- "hi" -> {"intent":"direct_response","tool":null,"student_fields":[]}
- "do i have backlogs?" -> {"intent":"student_data_query","tool":"get_student_data","student_fields":["backlogs"]}
- "what is my cgpa?" -> {"intent":"student_data_query","tool":"get_student_data","student_fields":["cgpa"]}
- "am i placement ready?" -> {"intent":"student_data_query","tool":"get_student_data","student_fields":["placement"]}
- "give me my profile summary" -> {"intent":"student_data_query","tool":"get_student_data","student_fields":["name","reg_no","cgpa","backlogs","risk","performance","placement"]}
- "what does the policy say about internships?" -> {"intent":"document_query","tool":"retrieve_documents","student_fields":[]}
- "tell me something" -> {"intent":"unclear_query","tool":null,"student_fields":[]}

For greetings and casual messages, do not ask the user to rephrase. Reply warmly and mention that you can help with academics or department documents.

Be concise. Never mention internal routing or tools in the answer field."""

STUDENT_ANSWER_SYSTEM_PROMPT = """You answer student academic questions using verified structured student data.
Be concise, direct, and helpful.
Do not invent data. Use only the provided student record."""

DOCUMENT_ANSWER_SYSTEM_PROMPT = """You answer department document questions using only the retrieved document snippets.
Be concise, factual, and direct.
If the snippets are weak, answer cautiously and only using what is present."""

ALLOWED_STUDENT_FIELDS = {
    "reg_no",
    "name",
    "cgpa",
    "backlogs",
    "risk",
    "performance",
    "placement",
}


def _get_client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    return OpenAI(api_key=settings.openai_api_key)


def _chat_json(messages: list[dict[str, str]]) -> dict[str, Any]:
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.openai_chat_model,
        response_format={"type": "json_object"},
        messages=messages,
        temperature=0,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def _chat_text(messages: list[dict[str, str]]) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=messages,
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()


def _build_messages(
    system_prompt: str,
    user_query: str,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": system_prompt}]
    
    # Process history
    for entry in history or []:
        role = str(entry.get("role", "")).strip().lower()
        content = str(entry.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
            
    # Add final user query
    messages.append({"role": "user", "content": user_query})
    return messages


def plan_query(query: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    messages = _build_messages(PLANNER_SYSTEM_PROMPT, query, history)
    data = _chat_json(messages)

    intent = str(data.get("intent", "unclear_query")).strip().lower()
    tool = data.get("tool")
    answer = str(data.get("answer", "")).strip()
    raw_student_fields = data.get("student_fields") or []

    if intent not in {
        "direct_response",
        "student_data_query",
        "document_query",
        "unclear_query",
    }:
        intent = "unclear_query"

    if tool not in {"get_student_data", "retrieve_documents"}:
        tool = None

    student_fields: list[str] = []
    if isinstance(raw_student_fields, list):
        for field in raw_student_fields:
            field_name = str(field).strip().lower()
            if field_name in ALLOWED_STUDENT_FIELDS and field_name not in student_fields:
                student_fields.append(field_name)

    if intent != "student_data_query":
        student_fields = []
    elif not student_fields:
        student_fields = list(ALLOWED_STUDENT_FIELDS)

    if not answer:
        if intent == "direct_response":
            answer = "Hello. Ask me about your academics or department documents."
        elif intent == "unclear_query":
            answer = (
                "You can ask things like: 'Do I have backlogs?', "
                "'What is my CGPA?', 'Am I placement ready?', or ask about a document."
            )

    return {
        "intent": intent,
        "tool": tool,
        "student_fields": student_fields,
        "answer": answer,
    }


def generate_student_answer(query: str, student: dict[str, Any]) -> str:
    return generate_student_answer_with_history(query, student, history=None)


def generate_student_answer_with_history(
    query: str,
    student: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> str:
    student_json = json.dumps(student, ensure_ascii=True)
    user_prompt = (
        f"User question: {query}\n"
        f"Student record: {student_json}"
    )
    messages = _build_messages(STUDENT_ANSWER_SYSTEM_PROMPT, user_prompt, history)
    return _chat_text(messages)


def generate_document_answer(query: str, docs: list[dict[str, Any]]) -> str:
    return generate_document_answer_with_history(query, docs, history=None)


def generate_document_answer_with_history(
    query: str,
    docs: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
) -> str:
    snippets = []
    for doc in docs[:3]:
        snippets.append(
            {
                "source": doc.get("source", {}),
                "text": doc.get("text", ""),
            }
        )

    user_prompt = (
        f"User question: {query}\n"
        f"Retrieved snippets: {json.dumps(snippets, ensure_ascii=True)}"
    )
    messages = _build_messages(DOCUMENT_ANSWER_SYSTEM_PROMPT, user_prompt, history)
    return _chat_text(messages)

