import json
import logging
import os
import asyncio
from typing import Any

import mcp.server.stdio
from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from pydantic import AnyUrl

from backend.database.neo4j_client import db_client
from backend.rag.retrieve import retrieve_documents as retrieve_documents_from_rag
from backend.database.validation import validate_student, validate_student_update
from backend.core.audit import log_action
from backend.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("academic-mcp")

# Create the MCP Server
app = Server("academic-mcp")

@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available academic resources."""
    return [
        Resource(
            uri=AnyUrl("academic://config"),
            name="Department AI Configuration",
            description="Global settings and status of the department assistant.",
            mimeType="application/json",
        )
    ]

@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read specific academic resources."""
    if str(uri) == "academic://config":
        return json.dumps({
            "name": "Department AI",
            "version": "1.0.0-mcp",
            "capabilities": ["student_lookup", "rag_search", "admin_ops"]
        })
    
    if str(uri).startswith("academic://profile/"):
        reg_no = str(uri).split("/")[-1].upper()
        data = db_client.get_student_data(reg_no)
        if not data:
            raise ValueError(f"Student {reg_no} not found")
        return json.dumps(data, indent=2)
    
    raise ValueError(f"Unknown resource: {uri}")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available academic tools."""
    tools = [
        Tool(
            name="get_student_profile",
            description="Retrieve the complete academic profile for a student by Registration Number.",
            inputSchema={
                "type": "object",
                "properties": {
                    "reg_no": {"type": "string", "description": "Student Registration Number, e.g., 21091A0501"}
                },
                "required": ["reg_no"]
            }
        ),
        Tool(
            name="search_department_documents",
            description="Search through college policies, syllabus, and regulations using RAG.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The natural language query to search for"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="calculate_eligibility",
            description="Calculate placement readiness and academic risk for a student.",
            inputSchema={
                "type": "object",
                "properties": {
                    "reg_no": {"type": "string", "description": "Student Registration Number"}
                },
                "required": ["reg_no"]
            }
        ),
        Tool(
            name="list_department_documents",
            description="List all available uploaded department documents.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]
    
    if settings.enable_hod_tools:
        tools.extend([
            Tool(
                name="update_student_data",
                description="Update specific fields of an existing student record.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "reg_no": {"type": "string"},
                        "fields": {"type": "object", "description": "Fields to update"}
                    },
                    "required": ["reg_no", "fields"]
                }
            ),
            Tool(
                name="add_student",
                description="Add a new student record.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "data": {"type": "object", "description": "Full student record"}
                    },
                    "required": ["data"]
                }
            ),
            Tool(
                name="remove_student",
                description="Remove a student record.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "reg_no": {"type": "string"}
                    },
                    "required": ["reg_no"]
                }
            ),
            Tool(
                name="list_students",
                description="List all students.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            )
        ])
        
    return tools

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Execute an academic tool (MCP entry point)."""
    return await process_tool_call(name, arguments or {})

async def process_tool_call(name: str, arguments: dict) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Internal logic for executing tools, shared by MCP and Graph."""
    actor_uid = arguments.get("_actor_uid", "internal")
    # Pass caller_uid and role from kwargs? wait, MCP tools don't receive auth tokens.
    # In this app, MCP tools are called INTERNALLY by the graph using an internal event loop or client.
    # We will assume they are safe because the graph handles RBAC.
    # We use a dummy actor for internal tool calls since the graph logs to Chat logs anyway.
    actor_uid = arguments.get("_actor_uid", "internal")
    role = arguments.get("_role", "system")
    
    # Strip internal args
    if "_actor_uid" in arguments: del arguments["_actor_uid"]
    if "_role" in arguments: del arguments["_role"]
    
    if name == "get_student_profile":
        reg_no = arguments.get("reg_no", "").strip().upper()
        if not reg_no:
            return [TextContent(type="text", text="Error: Registration number required.")]
        
        data = await asyncio.to_thread(db_client.get_student_data, reg_no)
        if not data:
            return [TextContent(type="text", text=f"No student found with Registration Number: {reg_no}")]
        
        return [TextContent(type="text", text=json.dumps(data, indent=2))]

    elif name == "search_department_documents":
        query = arguments.get("query", "")
        if not query:
            return [TextContent(type="text", text="Error: Query required.")]
        
        docs = retrieve_documents_from_rag(query)
        if not docs:
            return [TextContent(type="text", text="No relevant documents found for that query.")]
        
        results = []
        for i, doc in enumerate(docs):
            source = doc.get("source", {})
            results.append(f"Source {i+1} ({source.get('document', 'Unknown')}): {doc.get('text')}")
        
        return [TextContent(type="text", text="\n\n".join(results))]

    elif name == "calculate_eligibility":
        reg_no = arguments.get("reg_no", "").strip().upper()
        raw_data = await asyncio.to_thread(db_client.get_student_data, reg_no)
        if not raw_data:
            return [TextContent(type="text", text="Student not found.")]
        
        data = validate_student(raw_data)
        cgpa = float(data.get("cgpa", 0))
        backlogs = int(data.get("backlogs", 0))
        placement = str(data.get("placement", "no")).lower()

        is_eligible = cgpa >= 7.0 and backlogs == 0
        risk = "High" if backlogs > 0 or cgpa < 6.0 else "Low"

        report = {
            "status": "Targeting Placement" if is_eligible else "Needs Improvement",
            "cgpa": cgpa,
            "backlogs": backlogs,
            "can_apply_for_placement": is_eligible,
            "current_placement_status": placement,
            "risk_level": risk,
            "recommendation": "Focus on clearing backlogs" if backlogs > 0 else "Focus on improving CGPA" if cgpa < 7.0 else "Ready for interviews"
        }
        
        return [TextContent(type="text", text=json.dumps(report, indent=2))]

    elif name == "list_department_documents":
        upload_dir = settings.upload_dir
        if not upload_dir.exists():
            return [TextContent(type="text", text="[]")]
        docs = []
        for f in upload_dir.glob("*.pdf"):
            docs.append(f.name)
        return [TextContent(type="text", text=json.dumps(docs, indent=2))]

    elif name == "update_student_data":
        reg_no = arguments.get("reg_no", "").strip().upper()
        fields = arguments.get("fields", {})
        valid_fields = validate_student_update(fields)
        if not valid_fields:
            return [TextContent(type="text", text="No valid fields provided to update.")]
            
        success = await asyncio.to_thread(db_client.update_student_data, reg_no, valid_fields)
        
        log_action(actor_uid, role, "update_student", reg_no, valid_fields, "success" if success else "failed")
            
        if not success:
            return [TextContent(type="text", text=f"Update failed. Student {reg_no} might not exist.")]
        return [TextContent(type="text", text=f"Successfully updated student {reg_no} with fields: {list(valid_fields.keys())}")]

    elif name == "add_student":
        data = arguments.get("data", {})
        validated = validate_student(data)
        reg_no = validated.get("reg_no")
        if not reg_no:
            return [TextContent(type="text", text="Error: valid 'reg_no' required in data.")]
            
        success = await asyncio.to_thread(db_client.add_student, validated)
        
        log_action(actor_uid, role, "add_student", reg_no, validated, "success" if success else "failed")
            
        if not success:
            return [TextContent(type="text", text=f"Failed to add student. {reg_no} might already exist.")]
        return [TextContent(type="text", text=f"Successfully added student {reg_no}.")]

    elif name == "remove_student":
        reg_no = arguments.get("reg_no", "").strip().upper()
        success = await asyncio.to_thread(db_client.remove_student, reg_no)
        
        log_action(actor_uid, role, "remove_student", reg_no, None, "success" if success else "failed")
        
        if not success:
            return [TextContent(type="text", text=f"Failed to remove student {reg_no}.")]
        return [TextContent(type="text", text=f"Successfully removed student {reg_no}.")]

    elif name == "list_students":
        students = await asyncio.to_thread(db_client.list_all_students)
        return [TextContent(type="text", text=json.dumps(students, indent=2))]

    raise ValueError(f"Unknown tool: {name}")
