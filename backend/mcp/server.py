import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from pydantic import AnyUrl

from backend.database.firestore import db_client
from backend.rag.retrieve import retrieve_documents as retrieve_documents_from_rag
from backend.database.validation import validate_student

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
            "capabilities": ["student_lookup", "rag_search"]
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
    return [
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
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Execute an academic tool."""
    if name == "get_student_profile":
        reg_no = arguments.get("reg_no", "").strip().upper()
        if not reg_no:
            return [TextContent(type="text", text="Error: Registration number required.")]
        
        data = db_client.get_student_data(reg_no)
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
        raw_data = db_client.get_student_data(reg_no)
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

    raise ValueError(f"Unknown tool: {name}")
