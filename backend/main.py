from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.chat import router as chat_router
from backend.api.me import router as me_router
from backend.api.upload import router as upload_router
from backend.api.admin import router as admin_router


from mcp.server.sse import SseServerTransport

app = FastAPI(title="Department AI MVP", version="1.1.0-mcp")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Lazy-load MCP server to speed up initial startup
def get_mcp_app():
    from backend.mcp.server import app as mcp_app
    return mcp_app

# SSE Transport for MCP
sse = SseServerTransport("/mcp/messages")

@app.get("/mcp/sse")
async def handle_sse(request: Request):
    mcp_app = get_mcp_app()
    async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp_app.run(read_stream, write_stream, mcp_app.create_initialization_options())

@app.post("/mcp/messages")
async def handle_messages(request: Request):
    await sse.handle_post_request(request.scope, request.receive, request._send)

app.include_router(chat_router)
app.include_router(me_router)
app.include_router(upload_router)
app.include_router(admin_router)
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")



@app.get("/")
def frontend_index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/login")
def frontend_login():
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/dashboard")
def frontend_dashboard():
    return FileResponse(FRONTEND_DIR / "dashboard.html")


@app.get("/profile")
def frontend_profile():
    return FileResponse(FRONTEND_DIR / "profile.html")


@app.get("/documents")
def frontend_documents():
    return FileResponse(FRONTEND_DIR / "documents.html")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

