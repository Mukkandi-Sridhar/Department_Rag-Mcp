import logging
import traceback
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.chat import router as chat_router
from backend.api.me import router as me_router
from backend.api.upload import router as upload_router
from backend.api.admin import router as admin_router
from backend.auth.firebase_auth import verify_firebase_token

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Diagnostic Middleware to catch low-level 500 errors
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize SSE transport safely in app state
    logger.info("Initializing Application Lifespan...")
    try:
        from mcp.server.sse import SseServerTransport
        app.state.sse = SseServerTransport("/mcp/messages")
        logger.info("MCP SSE Transport initialized successfully in app.state.")
    except Exception as e:
        logger.error(f"Failed to initialize SSE Transport: {e}")
        app.state.sse = None
    yield
    # Shutdown
    logger.info("Shutting down Application...")

app = FastAPI(
    title="Department AI MVP", 
    version="1.1.0-mcp",
    lifespan=lifespan
)

# Diagnostic Middleware: Capture any unhandled exception and write to a log file
@app.middleware("http")
async def diagnostic_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        error_file = Path(__file__).resolve().parent.parent / "error_traceback.log"
        with open(error_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- ERROR LOG {Path(__file__).name} ---\n")
            f.write(traceback.format_exc())
            f.write("\n---------------------------\n")
        logger.error(f"DIAGNOSTIC: Caught exception: {e}. Traceback written to {error_file}")
        return Response("Internal Server Error (Captured by Diagnostic Middleware)", status_code=500)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Lazy-load MCP server
def get_mcp_app():
    from backend.mcp.server import app as mcp_app
    return mcp_app

def _require_mcp_auth(authorization: str | None) -> None:
    verify_firebase_token(authorization)

@app.get("/mcp/sse")
async def handle_sse(request: Request, authorization: str | None = Header(default=None)):
    _require_mcp_auth(authorization)
    sse = getattr(request.app.state, "sse", None)
    if not sse:
        return Response("SSE Transport not available", status_code=503)
    mcp_app = get_mcp_app()
    async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp_app.run(read_stream, write_stream, mcp_app.create_initialization_options())

@app.post("/mcp/messages")
async def handle_messages(request: Request, authorization: str | None = Header(default=None)):
    _require_mcp_auth(authorization)
    sse = getattr(request.app.state, "sse", None)
    if not sse:
        return Response("SSE Transport not available", status_code=503)
    await sse.handle_post_request(request.scope, request.receive, request._send)

app.include_router(chat_router)
app.include_router(me_router)
app.include_router(upload_router)
app.include_router(admin_router)

app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")



@app.get("/")
def frontend_index():
    # Hardened redirect
    return Response(
        status_code=307,
        headers={"Location": "/login"}
    )


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
