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

from backend.config import settings
from backend.database.validation import validate_student
from backend.llm.brain import (
    generate_document_answer_with_history,
    generate_student_answer_with_history,
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
    student_context: dict[str, Any]
    documents: list[dict[str, Any]]
    status: str
    answer: str
    data: dict[str, Any]
    error: str | None

# Helper to call MCP tools internally
async def _call_mcp_tool(name: str, arguments: dict) -> str:
    from mcp.types import TextContent
    mcp_app = _get_mcp_app()
    results = await mcp_app.call_tool(name, arguments)
    texts = [r.text for r in results if isinstance(r, TextContent)]
    return "\n".join(texts)

def _plan_node(state: ChatGraphState) -> ChatGraphState:
    plan = plan_query(state["query"], history=state.get("history"))
    return {
        "plan": plan,
        "intent": plan["intent"],
        "tool_used": plan.get("tool"),
        "requested_fields": plan.get("student_fields", []),
    }

def _route_from_plan(state: ChatGraphState) -> str:
    intent = state.get("intent", "unclear_query")
    if intent in {"direct_response", "unclear_query", "student_data_query", "document_query"}:
        return intent
    return "unsupported"

def _direct_response_node(state: ChatGraphState) -> ChatGraphState:
    return {
        "status": "answered",
        "answer": state.get("plan", {}).get("answer", "Hello. Ask me about your academics or documents."),
        "data": {},
        "error": None,
    }

def _unclear_query_node(state: ChatGraphState) -> ChatGraphState:
    return {
        "status": "needs_clarification",
        "answer": state.get("plan", {}).get("answer", "Please ask more clearly about backlogs, CGPA, or documents."),
        "data": {},
        "error": None,
    }

def _unsupported_node(state: ChatGraphState) -> ChatGraphState:
    return {
        "intent": state.get("intent", "unknown"),
        "status": "error",
        "answer": "I could not route that request.",
        "data": {},
        "error": "unsupported_intent",
    }

def _student_retrieval_node(state: ChatGraphState) -> ChatGraphState:
    reg_no = (state.get("reg_no") or "").strip().upper()
    try:
        # Use MCP Tool for profile
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        profile_text = loop.run_until_complete(_call_mcp_tool("get_student_profile", {"reg_no": reg_no}))
        student_context = json.loads(profile_text)
        
        # Also run eligibility check via MCP
        eligibility_text = loop.run_until_complete(_call_mcp_tool("calculate_eligibility", {"reg_no": reg_no}))
        eligibility_report = json.loads(eligibility_text)
        student_context["eligibility"] = eligibility_report
        
        return {
            "student_context": student_context,
            "data": {"student_context": student_context, "eligibility": eligibility_report},
            "error": None
        }
    except Exception as e:
        return {"status": "error", "answer": f"MCP Retrieval Failed: {str(e)}", "error": "mcp_error"}

def _route_after_student_retrieval(state: ChatGraphState) -> str:
    if state.get("status") == "error": return "end"
    return "student_answer"

def _student_answer_node(state: ChatGraphState) -> ChatGraphState:
    student_context = state.get("student_context", {})
    answer = generate_student_answer_with_history(state["query"], student_context, history=state.get("history"))
    return {"status": "answered", "answer": answer, "error": None}

def _document_retrieval_node(state: ChatGraphState) -> ChatGraphState:
    query = state["query"]
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        docs_text = loop.run_until_complete(_call_mcp_tool("search_department_documents", {"query": query}))
        # Mocking the docs structure for the final answer node
        return {
            "documents": [{"text": docs_text, "source": {"document": "MCP Search"}}],
            "error": None
        }
    except Exception as e:
        return {"status": "error", "answer": f"MCP Document Search Failed: {str(e)}", "error": "mcp_error"}

def _route_after_document_retrieval(state: ChatGraphState) -> str:
    if state.get("status") == "error": return "end"
    return "document_answer"

def _document_answer_node(state: ChatGraphState) -> ChatGraphState:
    answer = generate_document_answer_with_history(state["query"], state.get("documents", []), history=state.get("history"))
    return {"status": "answered", "answer": answer, "error": None}

@lru_cache(maxsize=1)
def _get_chat_graph():
    if not LANGGRAPH_AVAILABLE or StateGraph is None: return None
    graph = StateGraph(ChatGraphState)
    graph.add_node("plan", _plan_node)
    graph.add_node("direct_response", _direct_response_node)
    graph.add_node("unclear_query", _unclear_query_node)
    graph.add_node("student_retrieval", _student_retrieval_node)
    graph.add_node("student_answer", _student_answer_node)
    graph.add_node("document_retrieval", _document_retrieval_node)
    graph.add_node("document_answer", _document_answer_node)
    graph.add_node("unsupported", _unsupported_node)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", _route_from_plan, {
        "direct_response": "direct_response",
        "unclear_query": "unclear_query",
        "student_data_query": "student_retrieval",
        "document_query": "document_retrieval",
        "unsupported": "unsupported",
    })
    graph.add_conditional_edges("student_retrieval", _route_after_student_retrieval, {"student_answer": "student_answer", "end": END})
    graph.add_conditional_edges("document_retrieval", _route_after_document_retrieval, {"document_answer": "document_answer", "end": END})
    graph.add_edge("direct_response", END)
    graph.add_edge("unclear_query", END)
    graph.add_edge("student_answer", END)
    graph.add_edge("document_answer", END)
    graph.add_edge("unsupported", END)
    return graph.compile()

def _run_chat_fallback(initial_state: ChatGraphState) -> ChatGraphState:
    state: ChatGraphState = dict(initial_state)
    state.update(_plan_node(state))
    next_step = _route_from_plan(state)
    if next_step == "direct_response":
        state.update(_direct_response_node(state))
    elif next_step == "unclear_query":
        state.update(_unclear_query_node(state))
    elif next_step == "student_data_query":
        state.update(_student_retrieval_node(state))
        if _route_after_student_retrieval(state) == "student_answer":
            state.update(_student_answer_node(state))
    elif next_step == "document_query":
        state.update(_document_retrieval_node(state))
        if _route_after_document_retrieval(state) == "document_answer":
            state.update(_document_answer_node(state))
    else:
        state.update(_unsupported_node(state))
    return state

def run_chat_graph(*, original_message: str, query: str, history: list[dict[str, str]] | None, uid: str | None, reg_no: str | None, role: str | None) -> ChatGraphState:
    initial_state: ChatGraphState = {
        "original_message": original_message,
        "query": query,
        "history": history or [],
        "uid": uid,
        "reg_no": reg_no,
        "role": role,
    }
    graph = _get_chat_graph()
    if graph is None: return _run_chat_fallback(initial_state)
    return dict(graph.invoke(initial_state))
