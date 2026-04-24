import json
import logging
from functools import lru_cache
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field, ValidationError


from backend.core.config import settings

logger = logging.getLogger(__name__)

VALID_INTENTS = {
    "direct_response",
    "student_data_query",
    "document_query",
    "hybrid_query",
    "faculty_query",
    "admin_query",
    "unclear_query",
    "out_of_scope",
}

VALID_TOOLS = {
    "get_student_profile",
    "get_student_schema",
    "search_department_documents",
    "search_students",
    "update_student_data",
    "add_student",
    "remove_student",
    "list_students",
}

NULL_TOOL_VALUES = {None, "", "null", "none"}
PLANNER_CONFIDENCE_THRESHOLD = 0.35
INTENT_WITHOUT_TOOL = {"direct_response", "unclear_query", "out_of_scope"}
INTENT_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "student_data_query": {"get_student_profile"},
    "document_query": {"search_department_documents"},
    "hybrid_query": {"get_student_profile", "search_department_documents"},
    "faculty_query": {"search_students", "list_students", "get_student_schema"},
    "admin_query": {"search_students", "list_students", "get_student_schema", "update_student_data", "add_student", "remove_student"},
}


class PlannerOutput(BaseModel):
    intent: Literal[
        "direct_response",
        "student_data_query",
        "document_query",
        "hybrid_query",
        "faculty_query",
        "admin_query",
        "unclear_query",
        "out_of_scope",
    ] = "unclear_query"
    tool: Literal[
        "get_student_profile",
        "get_student_schema",
        "search_department_documents",
        "search_students",
        "update_student_data",
        "add_student",
        "remove_student",
        "list_students",
    ] | None = None
    student_fields: list[str] = Field(default_factory=list)
    action_payload: dict[str, Any] = Field(default_factory=dict)
    answer: str = "I will help you with that."
    confidence: float = 0.7


PLANNER_PROMPT_CORE = """You are an intelligent query router for the AIML Department AI at RGMCET.
Return only JSON: {"intent": str, "tool": str|null, "student_fields": [], "action_payload": {}, "answer": str, "confidence": float}

Intents: direct_response, student_data_query, document_query, hybrid_query, faculty_query, admin_query, unclear_query, out_of_scope
Tools: get_student_profile, search_department_documents, search_students, list_students, update_student_data, add_student, remove_student

Rules:
- Single student by name/reg_no → student_data_query + get_student_profile, action_payload: {"query": "name or reg_no"}
- Multiple students, filters, counts, rankings → faculty_query + search_students, action_payload: {"cypher": "MATCH..."}
- Documents/policies → document_query + search_department_documents
- Greetings/chitchat → direct_response, no tool

Neo4j Schema:
Student(reg_no, name, email, gender, cgpa:float, backlogs:int, category)
MATCH (s:Student)-[:ENROLLED_IN]->(p:Program) — use this for program/department filters
NEVER use s.program, s.department, s.branch — they do not exist
"""

PLANNER_PROMPT_STUDENT = """The user is a STUDENT at RGMCET AIML department.
- "my cgpa", "my backlogs", "my profile" → student_data_query + get_student_profile
- Cannot use admin tools
"""

PLANNER_PROMPT_FACULTY = """The user is FACULTY or HOD at RGMCET AIML department.
- Faculty have no personal academic records. If they ask "my cgpa/backlogs/marks" → direct_response, tell them to specify a student name or reg_no
- For student data queries use search_students with Cypher or get_student_profile
- For program queries always use: MATCH (s:Student)-[:ENROLLED_IN]->(p:Program) WHERE toLower(p.name) CONTAINS 'cse'

Cypher examples:
// backlogs filter
MATCH (s:Student) WHERE s.backlogs > 2 RETURN s.name, s.reg_no, s.backlogs ORDER BY s.backlogs DESC
// top cgpa
MATCH (s:Student) RETURN s.name, s.cgpa ORDER BY s.cgpa DESC LIMIT 5
// by program
MATCH (s:Student)-[:ENROLLED_IN]->(p:Program) WHERE toLower(p.name) CONTAINS 'cse' RETURN s.name, s.reg_no, s.cgpa, s.backlogs
// count
MATCH (s:Student) WHERE s.gender = 'Female' RETURN count(s) AS total
"""


def _planner_prompt_for_role(role: str) -> str:
    r = str(role or "student").strip().lower()
    if r in {"faculty", "hod"}:
        return f"{PLANNER_PROMPT_CORE}\n{PLANNER_PROMPT_FACULTY}"
    return f"{PLANNER_PROMPT_CORE}\n{PLANNER_PROMPT_STUDENT}"

STUDENT_ANSWER_SYSTEM_PROMPT = """You are an academic assistant for AIML department students at RGMCET. Present student data factually. No eligibility judgments or motivational language."""

DOCUMENT_ANSWER_SYSTEM_PROMPT = """Factual document assistant.
- Use only provided snippets.
- If empty, state information not found.
- Concise, factual, no fillers."""

HYBRID_ANSWER_SYSTEM_PROMPT = """Comprehensive integration assistant.
- Use provided student and document data.
- If one source is empty, still answer using the other.
- Never invent facts. Factual and direct."""

ADMIN_ANSWER_SYSTEM_PROMPT = """Admin assistant. Use only provided data. If empty, state clearly. Never invent records."""

FACULTY_ANSWER_SYSTEM_PROMPT = """You are an academic assistant for AIML department faculty at RGMCET. Present student data clearly. Show name and reg_no by default. No invented data."""

GENERAL_CONVERSATIONAL_PROMPT = """You are an AI assistant for the AIML department at RGMCET. Help with academic queries, student records, and department information. Role: {role}."""


def _get_client():
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    # Assuming json mode for planner, generic for text
    return ChatOpenAI(api_key=settings.openai_api_key, model=settings.openai_chat_model)

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
    system_prompt = _planner_prompt_for_role(role)
    messages = _build_messages(system_prompt, query, history)
    
    try:
        # Production pattern: schema-constrained structured output.
        planner = _get_openai_model().with_structured_output(PlannerOutput)
        response = planner.invoke(messages)
        data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        return _validate_plan(data, role=role, query=query)
    except Exception as e:
        logger.error(f"Planning error: {e}")
        return _fallback_plan(str(e))

async def plan_query_async(query: str, role: str = "student", history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Asynchronous version of plan_query."""
    system_prompt = _planner_prompt_for_role(role)
    messages = _build_messages(system_prompt, query, history)
    
    try:
        planner = _get_openai_model().with_structured_output(PlannerOutput)
        response = await planner.ainvoke(messages)
        data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        return _validate_plan(data, role=role, query=query)
    except Exception as e:
        logger.error(f"Async planning error: {e}")
        return _fallback_plan(str(e))

def _validate_plan(data: dict, role: str = "student", query: str = "") -> dict:
    """Ensure the plan follows allowed fields and tools."""
    # Role-aware override: faculty/hod have no personal academic records
    ACADEMIC_PERSONAL_KEYWORDS = {"backlogs", "cgpa", "marks", "attendance", "result", "grade", "gpa", "score"}
    PERSONAL_PRONOUNS = {"my", "mine", "i have", "do i", "what are my", "what is my"}
    
    if role in {"faculty", "hod"}:
        combined = query.lower()
        has_pronoun = any(p in combined for p in PERSONAL_PRONOUNS)
        has_academic = any(k in combined for k in ACADEMIC_PERSONAL_KEYWORDS)
        if has_pronoun and has_academic:
            return {
                "intent": "direct_response",
                "tool": None,
                "student_fields": [],
                "action_payload": {},
                "answer": "You are logged in as faculty. To look up a student's academic record, please provide their name or registration number.",
                "confidence": 1.0,
            }

    if not isinstance(data, dict):
        data = {}
    try:
        parsed = PlannerOutput.model_validate(data)
    except AttributeError:
        parsed = PlannerOutput.parse_obj(data)
    except ValidationError:
        return _fallback_plan("invalid_planner_schema")

    intent = str(parsed.intent).strip().lower()
    if intent not in VALID_INTENTS:
        intent = "unclear_query"

    raw_tool = parsed.tool
    normalized_tool = str(raw_tool).strip().lower() if raw_tool is not None else None
    if raw_tool in NULL_TOOL_VALUES or normalized_tool in NULL_TOOL_VALUES:
        tool = None
    elif normalized_tool in VALID_TOOLS:
        tool = normalized_tool
    else:
        tool = None

    try:
        confidence = float(parsed.confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if confidence < PLANNER_CONFIDENCE_THRESHOLD and intent not in {"out_of_scope"}:
        intent = "unclear_query"

    # Keep policy checks deterministic and compact.
    if intent in INTENT_WITHOUT_TOOL:
        tool = None
    elif tool is not None:
        allowed = INTENT_TOOL_ALLOWLIST.get(intent, set())
        if tool not in allowed:
            tool = None

    return {
        "intent": intent,
        "tool": tool,
        "student_fields": parsed.student_fields if isinstance(parsed.student_fields, list) else [],
        "action_payload": parsed.action_payload if isinstance(parsed.action_payload, dict) else {},
        "answer": parsed.answer,
        "confidence": confidence,
    }

def _fallback_plan(error_msg: str) -> dict:
    return {
        "intent": "unclear_query",
        "tool": None,
        "student_fields": [],
        "action_payload": {},
        "answer": f"I encountered a planning error: {error_msg}",
        "confidence": 0.0,
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

def build_hybrid_answer_messages_history(
    query: str,
    student: dict[str, Any] | None,
    docs: list[dict[str, Any]] | None,
    history: list[dict[str, str]] | None = None,
) -> list:
    student_json = json.dumps(student or {}, ensure_ascii=True)
    snippets = []
    for doc in (docs or [])[:3]:
        snippets.append(
            {
                "source": doc.get("source", {}),
                "text": doc.get("text", ""),
            }
        )
    user_prompt = (
        f"User question: {query}\n"
        f"Student record: {student_json}\n"
        f"Retrieved snippets: {json.dumps(snippets, ensure_ascii=True)}"
    )
    return _build_messages(HYBRID_ANSWER_SYSTEM_PROMPT, user_prompt, history)


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


