from __future__ import annotations
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
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

from backend.core.config import settings
from backend.database.validation import validate_student
from backend.llm.brain import (
    build_document_answer_messages_history,
    build_student_answer_messages_history,
    build_admin_answer_messages_history,
    build_faculty_answer_messages_history,
    build_general_answer_messages_history,
    plan_query,
)

# Lazy-load helper for MCP internally
def _get_mcp_app():
    from backend.mcp.server import app as mcp_app
    return mcp_app

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
    status: str
    answer: str
    answer_prompt: list[Any]
    data: dict[str, Any]
    error: str | None

# Helper to call MCP tools internally
async def _call_mcp_tool(name: str, arguments: dict) -> str:
    from mcp.types import TextContent
    from backend.mcp.server import process_tool_call
    results = await process_tool_call(name, arguments)
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
    
    if intent == "admin_query" and role != "hod":
        return {"status": "error", "error": "permission_denied"}
        
    if intent == "faculty_query" and role not in {"faculty", "hod"}:
        return {"status": "error", "error": "permission_denied"}
        
    if intent == "student_data_query" and role not in {"student", "hod"}:
        return {"status": "error", "error": "permission_denied"}
        
    return {"status": "ok", "error": None}

def _route_from_plan(state: ChatGraphState) -> str:
    if state.get("status") == "error" and state.get("error") == "permission_denied":
        return "permission_denied"

    intent = state.get("intent", "unclear_query")
    if intent in {"direct_response", "unclear_query", "student_data_query", "document_query", "faculty_query", "out_of_scope"}:
        return intent
    return "unsupported"

async def _guardrail_node(state: ChatGraphState) -> ChatGraphState:
    from langchain_core.messages import AIMessage
    return {
        "status": "answered",
        "answer_prompt": [AIMessage(content="I am the AIML Department Assistant. I can only assist you with matters related to the AIML department, academic performance, or student records. I cannot answer general knowledge or out-of-scope questions.")],
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
    
    if role == "hod" and payload.get("reg_no"):
        reg_no = payload.get("reg_no", "").strip().upper()
    else:
        reg_no = (state.get("reg_no") or "").strip().upper()
        
    try:
        profile_text = await _call_mcp_tool("get_student_profile", {"reg_no": reg_no})
        
        if "No student found" in profile_text:
            return {"status": "error", "answer": profile_text, "error": "not_found"}
            
        student_context = json.loads(profile_text)
        
        eligibility_text = await _call_mcp_tool("calculate_eligibility", {"reg_no": reg_no})
        try:
            eligibility_report = json.loads(eligibility_text)
            student_context["eligibility"] = eligibility_report
        except:
            pass
        
        return {
            "student_context": student_context,
            "data": {"student_context": student_context},
            "error": None
        }
    except Exception as e:
        return {"status": "error", "answer": f"MCP Retrieval Failed: {str(e)}", "error": "mcp_error"}

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

    payload["_actor_uid"] = uid
    payload["_role"] = role
    
    try:
        result_text = await _call_mcp_tool(tool, payload)
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
        docs_text = await _call_mcp_tool("search_department_documents", {"query": query})
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
