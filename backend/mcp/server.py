import json
import logging
import asyncio
from pathlib import Path

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
from backend.core.config import settings
from backend.core.policy import can_manage_documents, can_mutate_student_data, can_run_analytics, normalize_role

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
            description="Retrieve the complete academic profile for a student. Accepts either a Registration Number (e.g. 23091A3349) or a student name (e.g. Sridhar). The system automatically determines which type of query it is.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Registration Number OR student name. Examples: '23091A3349' or 'Sridhar' or 'Ammar'"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_student_schema",
            description="Get available Student properties and inferred types from Neo4j (dynamic schema).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="search_department_documents",
            description="Search through college policies, syllabus, and regulations using RAG.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The natural language query to search for"},
                    "role": {"type": "string", "description": "Caller role for visibility filtering: student|faculty|hod"}
                },
                "required": ["query"]
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
        ),
        Tool(
            name="delete_department_document",
            description="Delete a document from uploads and vector index.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "PDF filename to delete"}
                },
                "required": ["filename"]
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
            ),
            Tool(
                name="search_students",
                description="Advanced search using Cypher query. Use for filters, counts, or comparisons. Schema: (s:Student {reg_no, name, email, gender, cgpa:Float, backlogs:Int, category, updated_at}).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "cypher": {"type": "string", "description": "Read-only Cypher query. Example: MATCH (s:Student) WHERE s.backlogs > 2 RETURN s.name"}
                    },
                    "required": ["cypher"]
                }
            )
        ])
        
    return tools

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Execute an academic tool (MCP entry point)."""
    return await process_tool_call(name, arguments or {})

async def process_tool_call(
    name: str,
    arguments: dict,
    *,
    actor_uid: str = "internal",
    actor_role: str = "system",
) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Internal logic for executing tools, shared by MCP and Graph."""
    try:
        arguments = dict(arguments or {})
        arguments.pop("_actor_uid", None)
        arguments.pop("_role", None)
        role = normalize_role(actor_role, default="system")

        def _forbidden(message: str = "Permission denied for this tool.") -> list[TextContent]:
            return [TextContent(type="text", text=message)]

        def _require_policy(check: bool) -> list[TextContent] | None:
            if not check:
                return _forbidden()
            return None
        
        if name == "get_student_profile":
            query = arguments.get("query", "").strip()
            if not query:
                return [TextContent(type="text", text="Error: Query required.")]

            results = await asyncio.to_thread(db_client.find_student_by_query, query)
            if not results:
                return [TextContent(type="text", text=f"No student found matching: {query}")]

            if len(results) == 1:
                return [TextContent(type="text", text=json.dumps(results[0], indent=2))]
            else:
                summary = [f"{r.get('reg_no', '?')} — {r.get('name', 'Unknown')}" for r in results]
                return [TextContent(
                    type="text",
                    text=f"Multiple matches found:\n" + "\n".join(summary) + "\n\nPlease specify Registration Number."
                )]

        elif name == "get_student_schema":
            denied = _require_policy(can_run_analytics(role))
            if denied:
                return denied
            schema = await asyncio.to_thread(db_client.get_student_schema)
            return [TextContent(type="text", text=json.dumps(schema, indent=2))]

        elif name == "search_department_documents":
            query = arguments.get("query", "")
            role = arguments.get("role", "student")
            if not query:
                return [TextContent(type="text", text="Error: Query required.")]
            
            docs = retrieve_documents_from_rag(query, role=role)
            if not docs:
                return [TextContent(type="text", text="No relevant documents found.")]
            
            results = [f"Source {i+1}: {doc.get('text')}" for i, doc in enumerate(docs[:3])]
            return [TextContent(type="text", text="\n\n".join(results))]

        elif name == "list_department_documents":
            docs = [f.name for f in settings.upload_dir.glob("*.pdf")]
            return [TextContent(type="text", text=json.dumps(docs, indent=2))]

        elif name == "delete_department_document":
            denied = _require_policy(can_manage_documents(role))
            if denied:
                return denied
            filename = str(arguments.get("filename", "")).strip()
            if not filename: return [TextContent(type="text", text="Error: filename required.")]
            file_path = settings.upload_dir / Path(filename).name
            if file_path.exists(): file_path.unlink()
            return [TextContent(type="text", text=f"Deleted {filename}")]

        elif name == "update_student_data":
            denied = _require_policy(can_mutate_student_data(role))
            if denied:
                return denied
            reg_no = arguments.get("reg_no", "").strip().upper()
            fields = validate_student_update(arguments.get("fields", {}))
            success = await asyncio.to_thread(db_client.update_student_data, reg_no, fields)
            return [TextContent(type="text", text="Success" if success else "Failed")]

        elif name == "add_student":
            denied = _require_policy(can_mutate_student_data(role))
            if denied:
                return denied
            success = await asyncio.to_thread(db_client.add_student, validate_student(arguments.get("data", {})))
            return [TextContent(type="text", text="Success" if success else "Failed")]

        elif name == "remove_student":
            denied = _require_policy(can_mutate_student_data(role))
            if denied:
                return denied
            reg_no = arguments.get("reg_no", "").strip().upper()
            success = await asyncio.to_thread(db_client.remove_student, reg_no)
            return [TextContent(type="text", text="Success" if success else "Failed")]

        elif name == "list_students":
            denied = _require_policy(can_run_analytics(role))
            if denied:
                return denied
            students = await asyncio.to_thread(db_client.list_all_students)
            return [TextContent(type="text", text=json.dumps(students, indent=2))]

        elif name == "search_students":
            denied = _require_policy(can_run_analytics(role))
            if denied:
                return denied
            cypher = arguments.get("cypher", "").strip()
            if not cypher:
                return [TextContent(type="text", text="Error: Cypher query required.")]
            
            # Execute with query retry logic (max 1 retry)
            result = await asyncio.to_thread(db_client.query_students, cypher)
            
            if result.get("error") and result.get("suggestion") == "retry":
                return [TextContent(
                    type="text", 
                    text=f"Cypher Error: {result['error']}\nSuggestion: Correct the syntax and try once more."
                )]
            
            if result.get("error"):
                return [TextContent(type="text", text=f"Search Failed: {result['error']}")]
            
            data = result.get("data", [])
            if not data:
                return [TextContent(type="text", text="No records matched the criteria.")]
                
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.error(f"Tool {name} execution failed: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]
