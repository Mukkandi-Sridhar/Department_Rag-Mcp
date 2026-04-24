from __future__ import annotations
import json
import asyncio
import re
from functools import lru_cache
from typing import Any, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
    LANGGRAPH_AVAILABLE = True
except ImportError:
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False

from backend.llm.brain import (
    build_document_answer_messages_history,
    build_hybrid_answer_messages_history,
    build_student_answer_messages_history,
    build_faculty_answer_messages_history,
    build_general_answer_messages_history,
    VALID_INTENTS,
)
from backend.core.policy import can_access_student_progress, can_run_analytics

class ChatGraphState(TypedDict, total=False):
    original_message: str
    query: str
    history: list[dict[str, str]]
    uid: str | None
    reg_no: str | None
    role: str | None
    plan: dict[str, Any]
    intent: str
    tool_used: str | None
    requested_fields: list[str]
    action_payload: dict[str, Any]
    student_context: dict[str, Any]
    documents: list[dict[str, Any]]
    hybrid_student_missing: bool
    hybrid_documents_missing: bool
    status: str
    answer: str
    answer_prompt: list[Any]
    data: dict[str, Any]
    error: str | None

# Helper to call MCP tools internally
async def _call_mcp_tool(
    name: str,
    arguments: dict,
    *,
    actor_uid: str = "internal",
    actor_role: str = "system",
) -> str:
    from mcp.types import TextContent
    from backend.mcp.server import process_tool_call
    results = await process_tool_call(name, arguments, actor_uid=actor_uid, actor_role=actor_role)
    texts = [r.text for r in results if isinstance(r, TextContent)]
    return "\n".join(texts)

async def _plan_node(state: ChatGraphState) -> ChatGraphState:
    role = state.get("role", "student")
    from backend.llm.brain import plan_query_async
    plan = await plan_query_async(state["query"], role=role, history=state.get("history"))
    return {
        "plan": plan,
        "intent": plan["intent"],
        "tool_used": plan.get("tool"),
        "requested_fields": plan.get("student_fields", []),
        "action_payload": plan.get("action_payload", {}),
    }

async def _rbac_guard_node(state: ChatGraphState) -> ChatGraphState:
    role = state.get("role", "student")
    intent = state.get("intent", "unclear_query")
    payload = state.get("action_payload", {})
    
    if intent == "admin_query" and not can_run_analytics(role):
        return {"status": "error", "error": "permission_denied"}
        
    if intent == "faculty_query" and not can_run_analytics(role):
        return {"status": "error", "error": "permission_denied"}
        
    if intent == "student_data_query":
        if not can_access_student_progress(role):
            return {"status": "error", "error": "permission_denied"}
        
    return {"status": "ok", "error": None}

def _route_from_plan(state: ChatGraphState) -> str:
    if state.get("status") == "error" and state.get("error") == "permission_denied":
        return "permission_denied"

    intent = state.get("intent", "unclear_query")
    if intent in VALID_INTENTS:
        return intent
    return "unsupported"

async def _guardrail_node(state: ChatGraphState) -> ChatGraphState:
    from langchain_core.messages import AIMessage
    query = state.get("query", "").lower()
    
    # Handle meta-queries about the system itself
    if any(word in query for word in ["mcp", "architecture", "who are you", "what can you do", "system"]):
        return {
            "status": "answered",
            "answer_prompt": [AIMessage(content="I am the AIML Department Assistant, built using the Model Context Protocol (MCP). I can help you look up student records, check academic eligibility, and search department documents. How can I assist you with department matters today?")],
            "answer": "",
            "data": {},
            "error": None,
        }
        
    return {
        "status": "answered",
        "answer_prompt": [AIMessage(content="I am here to assist with matters related to the AIML department, academic performance, or student records. If you have specific questions about students or department policies, feel free to ask!")],
        "answer": "",
        "data": {},
        "error": None,
    }

async def _permission_denied_node(state: ChatGraphState) -> ChatGraphState:
    return {
        "status": "error",
        "answer": "You do not have permission to perform this action.",
        "data": {},
        "error": "permission_denied",
    }

async def _direct_response_node(state: ChatGraphState) -> ChatGraphState:
    from backend.llm.brain import build_general_answer_messages_history
    prompt = build_general_answer_messages_history(state["query"], role=state.get("role", "student"), history=state.get("history"))
    return {
        "status": "answered",
        "answer_prompt": prompt,
        "answer": "",
        "data": {},
        "error": None,
    }

async def _unclear_query_node(state: ChatGraphState) -> ChatGraphState:
    from backend.llm.brain import build_general_answer_messages_history
    prompt = build_general_answer_messages_history(state["query"], role=state.get("role", "student"), history=state.get("history"))
    return {
        "status": "needs_clarification",
        "answer_prompt": prompt,
        "answer": "",
        "data": {},
        "error": None,
    }

async def _unsupported_node(state: ChatGraphState) -> ChatGraphState:
    return {
        "intent": state.get("intent", "unknown"),
        "status": "error",
        "answer": "I could not route that request.",
        "answer_prompt": [],
        "data": {},
        "error": "unsupported_intent",
    }

async def _student_retrieval_node(state: ChatGraphState) -> ChatGraphState:
    role = state.get("role", "student")
    payload = state.get("action_payload", {})

    if role in {"faculty", "hod"} and payload.get("query"):
        query = payload.get("query", "").strip()
    elif role in {"faculty", "hod"} and payload.get("reg_no"):
        query = payload.get("reg_no", "").strip().upper()
    elif role in {"faculty", "hod"}:
        # Fallback to original user query if planner payload is sparse.
        query = (state.get("query") or "").strip()
    else:
        query = (state.get("reg_no") or "").strip().upper()

    query = _extract_lookup_term(query)
        
    try:
        profile_text = await _call_mcp_tool(
            "get_student_profile",
            {"query": query},
            actor_uid=state.get("uid") or "internal",
            actor_role=role,
        )
        
        if "No student found" in profile_text:
            return {"status": "error", "answer": profile_text, "error": "not_found"}
            
        try:
            student_context = json.loads(profile_text)
        except (json.JSONDecodeError, TypeError):
            # If not JSON, it might be a direct message (e.g. "Multiple students found")
            return {"status": "answered", "answer": profile_text, "error": None}

        # Eligibility is derived from the same profile fields and does not
        # require a second tool call.
        cgpa = student_context.get("cgpa")
        backlogs = student_context.get("backlogs")
        if cgpa is not None and backlogs is not None:
            try:
                student_context["eligibility"] = {
                    "eligible": float(cgpa) >= 7.0 and int(backlogs) == 0,
                    "cgpa": cgpa,
                    "backlogs": backlogs,
                }
            except (ValueError, TypeError):
                pass
        
        return {
            "student_context": student_context,
            "data": {"student_context": student_context},
            "error": None
        }
    except Exception as e:
        return {"status": "error", "answer": f"MCP Retrieval Failed: {str(e)}", "error": "mcp_error"}


def _extract_lookup_term(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return q

    reg_match = re.search(r"\b[0-9]{2,}[A-Za-z][A-Za-z0-9]{4,}\b", q)
    if reg_match:
        return reg_match.group(0).upper()

    lower_q = q.lower()
    for marker in ("about ", "of ", "for ", "student ", "reg no ", "reg_no "):
        idx = lower_q.rfind(marker)
        if idx != -1 and idx + len(marker) < len(q):
            candidate = q[idx + len(marker):].strip(" .,:;!?")
            if candidate:
                return candidate

    return q

def _route_after_student_retrieval(state: ChatGraphState) -> str:
    if state.get("status") == "error": return "end"
    return "student_answer"

async def _student_answer_node(state: ChatGraphState) -> ChatGraphState:
    from backend.llm.brain import build_student_answer_messages_history
    student_context = state.get("student_context", {})
    prompt = build_student_answer_messages_history(state["query"], student_context, history=state.get("history"))
    return {"status": "answered", "answer_prompt": prompt, "answer": "", "error": None}

async def _faculty_node(state: ChatGraphState) -> ChatGraphState:
    tool = state.get("tool_used")
    payload = state.get("action_payload", {})
    uid = state.get("uid", "internal")
    role = state.get("role", "faculty")
    from backend.llm.brain import build_faculty_answer_messages_history
    
    if not tool:
        prompt = build_faculty_answer_messages_history(state["query"], {"action_result": "No specific database tool was needed."}, history=state.get("history"))
        return {
            "status": "answered",
            "answer_prompt": prompt,
            "answer": "",
            "data": {},
            "error": None
        }

    try:
        result_text = await _call_mcp_tool(tool, payload, actor_uid=uid, actor_role=role)
        if tool == "search_students":
            lower_result = result_text.lower()
            if lower_result.startswith("cypher error:"):
                prompt = build_faculty_answer_messages_history(
                    state["query"],
                    {
                        "action_result": (
                            "I could not run that database search due to a query syntax issue. "
                            "Please rephrase your request in plain language (for example: "
                            "'top 5 students by cgpa' or 'count girls with high risk')."
                        )
                    },
                    history=state.get("history"),
                )
                return {
                    "status": "needs_clarification",
                    "answer_prompt": prompt,
                    "answer": "",
                    "data": {"action_result": result_text, "error_recovery": "retry_nl_rephrase"},
                    "error": None,
                }
            if lower_result.startswith("search failed:"):
                return {
                    "status": "error",
                    "answer": "I could not complete that student search right now. Please try again.",
                    "data": {"action_result": result_text},
                    "error": "search_failed",
                }
        prompt = build_faculty_answer_messages_history(state["query"], {"action_result": result_text}, history=state.get("history"))
        return {
            "status": "answered",
            "answer_prompt": prompt,
            "answer": "",
            "data": {"action_result": result_text},
            "error": None
        }
    except Exception as e:
        return {"status": "error", "answer": f"Faculty Tool Failed: {str(e)}", "error": "mcp_error"}

async def _document_retrieval_node(state: ChatGraphState) -> ChatGraphState:
    query = state["query"]
    try:
        docs_text = await _call_mcp_tool(
            "search_department_documents",
            {"query": query},
            actor_uid=state.get("uid") or "internal",
            actor_role=state.get("role", "student"),
        )
        return {
            "documents": [{"text": docs_text, "source": {"document": "MCP Search"}}],
            "error": None
        }
    except Exception as e:
        return {"status": "error", "answer": f"MCP Document Search Failed: {str(e)}", "error": "mcp_error"}

def _route_after_document_retrieval(state: ChatGraphState) -> str:
    if state.get("status") == "error": return "end"
    return "document_answer"

async def _document_answer_node(state: ChatGraphState) -> ChatGraphState:
    from backend.llm.brain import build_document_answer_messages_history
    prompt = build_document_answer_messages_history(state["query"], state.get("documents", []), history=state.get("history"))
    return {"status": "answered", "answer_prompt": prompt, "answer": "", "error": None}

async def _hybrid_retrieval_node(state: ChatGraphState) -> ChatGraphState:
    role = state.get("role", "student")
    payload = state.get("action_payload", {})
    query = state["query"]

    if role == "hod" and payload.get("query"):
        student_query = payload.get("query", "").strip()
    elif role == "hod" and payload.get("reg_no"):
        # Backward compatibility
        student_query = payload.get("reg_no", "").strip().upper()
    else:
        student_query = (state.get("reg_no") or "").strip().upper()

    actor_uid = state.get("uid") or "internal"
    student_task = _call_mcp_tool(
        "get_student_profile",
        {"query": student_query},
        actor_uid=actor_uid,
        actor_role=role,
    )
    document_task = _call_mcp_tool(
        "search_department_documents",
        {"query": query, "role": role},
        actor_uid=actor_uid,
        actor_role=role,
    )
    student_result, document_result = await asyncio.gather(
        student_task,
        document_task,
        return_exceptions=True,
    )

    student_context: dict[str, Any] = {}
    student_missing = True
    if not isinstance(student_result, Exception):
        profile_text = str(student_result or "").strip()
        if profile_text and "No student found" not in profile_text:
            try:
                student_context = json.loads(profile_text)
                student_missing = not bool(student_context)
            except (json.JSONDecodeError, TypeError):
                student_missing = True

    documents: list[dict[str, Any]] = []
    documents_missing = True
    if not isinstance(document_result, Exception):
        docs_text = str(document_result or "").strip()
        if docs_text and "No relevant documents found" not in docs_text:
            documents = [{"text": docs_text, "source": {"document": "MCP Search"}}]
            documents_missing = False

    if isinstance(student_result, Exception) and isinstance(document_result, Exception):
        return {
            "status": "error",
            "answer": "I could not retrieve student records or matching documents right now.",
            "error": "mcp_error",
        }

    return {
        "student_context": student_context,
        "documents": documents,
        "hybrid_student_missing": student_missing,
        "hybrid_documents_missing": documents_missing,
        "data": {
            "student_context": student_context,
            "documents": documents,
            "hybrid_student_missing": student_missing,
            "hybrid_documents_missing": documents_missing,
        },
        "error": None,
    }

def _route_after_hybrid_retrieval(state: ChatGraphState) -> str:
    if state.get("status") == "error":
        return "end"
    return "hybrid_answer"

async def _hybrid_answer_node(state: ChatGraphState) -> ChatGraphState:
    prompt = build_hybrid_answer_messages_history(
        state["query"],
        state.get("student_context", {}),
        state.get("documents", []),
        history=state.get("history"),
    )
    return {"status": "answered", "answer_prompt": prompt, "answer": "", "error": None}

@lru_cache(maxsize=1)
def _get_chat_graph():
    if not LANGGRAPH_AVAILABLE or StateGraph is None: return None
    graph = StateGraph(ChatGraphState)
    graph.add_node("plan", _plan_node)
    graph.add_node("rbac_guard", _rbac_guard_node)
    graph.add_node("direct_response", _direct_response_node)
    graph.add_node("unclear_query", _unclear_query_node)
    graph.add_node("student_retrieval", _student_retrieval_node)
    graph.add_node("student_answer", _student_answer_node)
    graph.add_node("document_retrieval", _document_retrieval_node)
    graph.add_node("document_answer", _document_answer_node)
    graph.add_node("hybrid_retrieval", _hybrid_retrieval_node)
    graph.add_node("hybrid_answer", _hybrid_answer_node)
    graph.add_node("faculty_query", _faculty_node)
    graph.add_node("permission_denied", _permission_denied_node)
    graph.add_node("unsupported", _unsupported_node)
    graph.add_node("out_of_scope", _guardrail_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "rbac_guard")
    graph.add_conditional_edges("rbac_guard", _route_from_plan, {
        "direct_response": "direct_response",
        "unclear_query": "unclear_query",
        "student_data_query": "student_retrieval",
        "document_query": "document_retrieval",
        "hybrid_query": "hybrid_retrieval",
        "faculty_query": "faculty_query",
        "admin_query": "faculty_query",
        "permission_denied": "permission_denied",
        "unsupported": "unsupported",
        "out_of_scope": "out_of_scope",
    })
    
    graph.add_conditional_edges("student_retrieval", _route_after_student_retrieval, {"student_answer": "student_answer", "end": END})
    graph.add_edge("student_answer", END)
    
    graph.add_conditional_edges("document_retrieval", _route_after_document_retrieval, {"document_answer": "document_answer", "end": END})
    graph.add_edge("document_answer", END)
    graph.add_conditional_edges("hybrid_retrieval", _route_after_hybrid_retrieval, {"hybrid_answer": "hybrid_answer", "end": END})
    graph.add_edge("hybrid_answer", END)

    graph.add_edge("direct_response", END)
    graph.add_edge("unclear_query", END)
    graph.add_edge("faculty_query", END)
    graph.add_edge("permission_denied", END)
    graph.add_edge("unsupported", END)
    graph.add_edge("out_of_scope", END)
    return graph.compile()

async def _run_chat_fallback(initial_state: ChatGraphState) -> ChatGraphState:
    state: ChatGraphState = dict(initial_state)
    state.update(await _plan_node(state))
    state.update(await _rbac_guard_node(state))
    next_step = _route_from_plan(state)
    
    if next_step == "direct_response":
        state.update(await _direct_response_node(state))
    elif next_step == "unclear_query":
        state.update(await _unclear_query_node(state))
    elif next_step == "permission_denied":
        state.update(await _permission_denied_node(state))
    elif next_step == "student_data_query":
        state.update(await _student_retrieval_node(state))
        if _route_after_student_retrieval(state) == "student_answer":
            state.update(await _student_answer_node(state))
    elif next_step == "admin_query" or next_step == "faculty_query":
        state.update(await _faculty_node(state))
    elif next_step == "document_query":
        state.update(await _document_retrieval_node(state))
        if _route_after_document_retrieval(state) == "document_answer":
            state.update(await _document_answer_node(state))
    elif next_step == "hybrid_query":
        state.update(await _hybrid_retrieval_node(state))
        if _route_after_hybrid_retrieval(state) == "hybrid_answer":
            state.update(await _hybrid_answer_node(state))
    elif next_step == "out_of_scope":
        state.update(await _guardrail_node(state))
    else:
        state.update(await _unsupported_node(state))
    return state

async def run_chat_graph(*, original_message: str, query: str, history: list[dict[str, str]] | None, uid: str | None, reg_no: str | None, role: str | None) -> ChatGraphState:
    initial_state: ChatGraphState = {
        "original_message": original_message,
        "query": query,
        "history": history or [],
        "uid": uid,
        "reg_no": reg_no,
        "role": role,
    }
    graph = _get_chat_graph()
    if graph is None: return await _run_chat_fallback(initial_state)
    return dict(await graph.ainvoke(initial_state))
