import json
from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


from backend.core.config import settings


PLANNER_SYSTEM_PROMPT = """You are the intelligent router for a college department AI assistant.
User role provided: {role}
Return only valid JSON with this exact shape:
{
  "intent": "direct_response" | "student_data_query" | "document_query" | "unclear_query" | "faculty_query" | "out_of_scope",
  "tool": "get_student_profile" | "search_department_documents" | "update_student_data" | "add_student" | "remove_student" | "list_students" | null,
  "student_fields": ["reg_no" | "name" | "cgpa" | "backlogs" | "risk" | "performance" | "placement"],
  "action_payload": {},
  "answer": "short message"
}

ROUTING EXAMPLES (CRITICAL):
- "what is my cgpa" (Role: STUDENT) -> {"intent": "student_data_query", "tool": "get_student_profile", "answer": "I will check your score."}
- "who has more backlogs" (Role: FACULTY) -> {"intent": "faculty_query", "tool": "list_students", "answer": "I am gathering the student roster."}
- "tell me about Ammar" (Role: FACULTY) -> {"intent": "faculty_query", "tool": "get_student_profile", "action_payload": {"reg_no": "AMMAR"}, "answer": "Fetching details for Ammar."}
- "update Sridhar's cgpa to 8.5" (Role: FACULTY) -> {"intent": "faculty_query", "tool": "update_student_data", "action_payload": {"reg_no": "SRIDHAR", "fields": {"cgpa": 8.5}}, "answer": "Updating record..."}

Routing based on ROLE:
- If role=="student", you CANNOT use any tool except "get_student_profile" to ask about their own data.
- If role=="FACULTY" or "HOD", you HAVE ADMIN ACCESS. You MUST pick a tool (e.g., "list_students" or "get_student_profile") if the user asks for ANY student record. NEVER say "out_of_scope" for student database queries when in faculty mode.

Questions about policies, syllabus, circulars, PDFs, etc -> document_query with tool search_department_documents.

For direct_response, set tool=null."""

STUDENT_ANSWER_SYSTEM_PROMPT = """You answer student academic and personal questions using verified structured student data.
Be concise, direct, and helpful. Use only the provided student record."""

DOCUMENT_ANSWER_SYSTEM_PROMPT = """You answer department document questions using only the retrieved document snippets.
Be concise, factual, and direct."""

FACULTY_ANSWER_SYSTEM_PROMPT = """You are the AI assistant in FACULTY/ADMIN mode.
You have FULL ACCESS to the department records. 
You answer faculty administrative questions based on the retrieved data.
If result data is present, summarize it professionally.
IMPORTANT: You are an administrator. Do NOT say you cannot access records. If the data is empty, say no records matched the filter."""

GENERAL_CONVERSATIONAL_PROMPT = """You are the intelligent assistant for the college department. 
Engage normally with the user based on their input. 
You are chatting with a user whose role is: {role}
"""

ALLOWED_STUDENT_FIELDS = {
    "reg_no",
    "name",
    "cgpa",
    "backlogs",
    "risk",
    "performance",
    "placement",
}


def _get_client():
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    # Assuming json mode for planner, generic for text
    return ChatOpenAI(api_key=settings.openai_api_key, model=settings.openai_chat_model)

def _chat_json(messages: list) -> dict[str, Any]:
    client = _get_client().bind(response_format={"type": "json_object"})
    response = client.invoke(messages)
    content = response.content or "{}"
    return json.loads(content)

def _chat_text(messages: list) -> str:
    client = _get_client()
    response = client.invoke(messages)
    return (response.content or "").strip()

def _build_messages(
    system_prompt: str,
    user_query: str,
    history: list[dict[str, str]] | None = None,
) -> list:
    messages = [SystemMessage(content=system_prompt)]
    
    # Process history
    for entry in history or []:
        role = str(entry.get("role", "")).strip().lower()
        content = str(entry.get("content", "")).strip()
        if content:
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
                
    # Add final user query
    messages.append(HumanMessage(content=user_query))
    return messages


@lru_cache(maxsize=1)
def _get_openai_model():
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    return ChatOpenAI(
        api_key=settings.openai_api_key, 
        model=settings.openai_chat_model,
        temperature=0
    )


def plan_query(query: str, role: str = "student", history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Synchronous plan wrapper."""
    system_prompt = PLANNER_SYSTEM_PROMPT.replace("{role}", role.upper())
    messages = _build_messages(system_prompt, query, history)
    
    try:
        # We use a JSON-ready client for planning
        client = _get_openai_model().bind(response_format={"type": "json_object"})
        response = client.invoke(messages)
        content = response.content or "{}"
        
        # Clean markdown if present
        if content.startswith("```"):
            content = content.split("```json")[-1].split("```")[0].strip()
            
        data = json.loads(content)
        return _validate_plan(data)
    except Exception as e:
        logger.error(f"Planning error: {e}")
        return _fallback_plan(str(e))

async def plan_query_async(query: str, role: str = "student", history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Asynchronous version of plan_query."""
    system_prompt = PLANNER_SYSTEM_PROMPT.replace("{role}", role.upper())
    messages = _build_messages(system_prompt, query, history)
    
    try:
        client = _get_openai_model().bind(response_format={"type": "json_object"})
        response = await client.ainvoke(messages)
        content = response.content or "{}"
        
        if content.startswith("```"):
            content = content.split("```json")[-1].split("```")[0].strip()
            
        data = json.loads(content)
        return _validate_plan(data)
    except Exception as e:
        logger.error(f"Async planning error: {e}")
        return _fallback_plan(str(e))

def _validate_plan(data: dict) -> dict:
    """Ensure the plan follows allowed fields and tools."""
    intent = str(data.get("intent", "unclear_query")).strip().lower()
    tool = data.get("tool")
    
    allowed_tools = {"get_student_profile", "search_department_documents", "update_student_data", "add_student", "remove_student", "list_students"}
    if tool not in allowed_tools:
        tool = None
        
    return {
        "intent": intent,
        "tool": tool,
        "student_fields": data.get("student_fields", []),
        "action_payload": data.get("action_payload", {}),
        "answer": data.get("answer", "I will help you with that.")
    }

def _fallback_plan(error_msg: str) -> dict:
    return {
        "intent": "unclear_query",
        "tool": None,
        "student_fields": [],
        "action_payload": {},
        "answer": f"I encountered a planning error: {error_msg}"
    }


def build_student_answer_messages(query: str, student: dict[str, Any]) -> list:
    return build_student_answer_messages_history(query, student, history=None)


def build_student_answer_messages_history(
    query: str,
    student: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> list:
    student_json = json.dumps(student, ensure_ascii=True)
    user_prompt = (
        f"User question: {query}\n"
        f"Student record: {student_json}"
    )
    return _build_messages(STUDENT_ANSWER_SYSTEM_PROMPT, user_prompt, history)


def build_document_answer_messages(query: str, docs: list[dict[str, Any]]) -> list:
    return build_document_answer_messages_history(query, docs, history=None)


def build_document_answer_messages_history(
    query: str,
    docs: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
) -> list:
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
    return _build_messages(DOCUMENT_ANSWER_SYSTEM_PROMPT, user_prompt, history)


def build_admin_answer_messages_history(
    query: str,
    admin_data: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> list:
    payload_json = json.dumps(admin_data, ensure_ascii=True)
    user_prompt = f"User asked: {query}\nResult data: {payload_json}"
    return _build_messages(ADMIN_ANSWER_SYSTEM_PROMPT, user_prompt, history)

def build_faculty_answer_messages_history(
    query: str,
    faculty_data: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> list:
    payload_json = json.dumps(faculty_data, ensure_ascii=True)
    user_prompt = f"User asked: {query}\nResult data: {payload_json}"
    return _build_messages(FACULTY_ANSWER_SYSTEM_PROMPT, user_prompt, history)


def build_general_answer_messages_history(
    query: str,
    role: str = "student",
    history: list[dict[str, str]] | None = None,
) -> list:
    system_prompt = GENERAL_CONVERSATIONAL_PROMPT.replace("{role}", role.upper())
    return _build_messages(system_prompt, query, history)

def get_streaming_client():
    return _get_client()


