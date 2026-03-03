"""
RedAmon Agent WebSocket API

FastAPI application providing WebSocket endpoint for real-time agent communication.
Supports session-based conversation continuity and phase-based approval flow.

Endpoints:
    WS /ws/agent - WebSocket endpoint for real-time bidirectional streaming
    GET /health - Health check
    GET /defaults - Agent default settings (camelCase, for frontend)
    GET /models - Available AI models from all configured providers
"""

import base64
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from logging_config import setup_logging
from orchestrator import AgentOrchestrator
from orchestrator_helpers import normalize_content
from utils import get_session_count
from websocket_api import WebSocketManager, websocket_endpoint

# Initialize logging with file rotation
setup_logging(log_level=logging.INFO, log_to_console=True, log_to_file=True)
logger = logging.getLogger(__name__)

orchestrator: Optional[AgentOrchestrator] = None
ws_manager: Optional[WebSocketManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Initializes the orchestrator and WebSocket manager on startup and cleans up on shutdown.
    """
    global orchestrator, ws_manager

    logger.info("Starting RedAmon Agent API...")

    # Initialize orchestrator
    orchestrator = AgentOrchestrator()
    await orchestrator.initialize()

    # Initialize WebSocket manager
    ws_manager = WebSocketManager()

    logger.info("RedAmon Agent API ready (WebSocket)")

    yield

    logger.info("Shutting down RedAmon Agent API...")
    if orchestrator:
        await orchestrator.close()


app = FastAPI(
    title="RedAmon Agent API",
    description="WebSocket API for real-time agent communication with phase tracking, MCP tools, and Neo4j integration",
    version="3.0.0",
    lifespan=lifespan
)

# Add CORS middleware for webapp (allow all origins for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Must be False when allow_origins is ["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# RESPONSE MODELS (for /health endpoint only)
# =============================================================================

class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str
    version: str
    tools_loaded: int
    active_sessions: int


# =============================================================================
# ENDPOINTS
# =============================================================================


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """
    Health check endpoint.

    Returns the API status, version, number of loaded tools, and active sessions.
    """
    tools_count = 0
    if orchestrator and orchestrator.tool_executor:
        tools_count = len(orchestrator.tool_executor.get_all_tools())

    sessions_count = get_session_count()

    return HealthResponse(
        status="ok" if orchestrator and orchestrator._initialized else "initializing",
        version="3.0.0",
        tools_loaded=tools_count,
        active_sessions=sessions_count
    )


@app.get("/defaults", tags=["System"])
async def get_defaults():
    """
    Get default agent settings for frontend project creation.

    Returns DEFAULT_AGENT_SETTINGS with camelCase keys prefixed with 'agent'
    for frontend compatibility (e.g., OPENAI_MODEL -> agentOpenaiModel).
    """
    from project_settings import DEFAULT_AGENT_SETTINGS

    def to_camel_case(snake_str: str, prefix: str = "agent") -> str:
        """Convert SCREAMING_SNAKE_CASE to prefixCamelCase."""
        prefixed = f"{prefix}_{snake_str}" if prefix else snake_str
        components = prefixed.lower().split('_')
        return components[0] + ''.join(x.title() for x in components[1:])

    # STEALTH_MODE is a project-level setting (not agent-specific), served by
    # recon defaults as "stealthMode".  Exclude it here to avoid creating a
    # duplicate "agentStealthMode" key that Prisma doesn't recognise.
    SKIP_KEYS = {'STEALTH_MODE'}

    # HYDRA_* keys map to Prisma fields without the 'agent' prefix
    # (e.g. HYDRA_ENABLED -> hydraEnabled, not agentHydraEnabled)
    NO_PREFIX_KEYS = {k for k in DEFAULT_AGENT_SETTINGS if k.startswith(('HYDRA_', 'PHISHING_'))}

    camel_case_defaults = {}
    for k, v in DEFAULT_AGENT_SETTINGS.items():
        if k in SKIP_KEYS:
            continue
        if k in NO_PREFIX_KEYS:
            camel_case_defaults[to_camel_case(k, prefix="")] = v
        else:
            camel_case_defaults[to_camel_case(k)] = v

    return camel_case_defaults


@app.get("/models", tags=["System"])
async def get_models():
    """
    Fetch available AI models from all configured providers.

    Returns a dict keyed by provider name, each containing a list of models
    with {id, name, context_length, description}. Results are cached for 1 hour.
    Only providers with valid API keys in the environment are queried.
    """
    from model_providers import fetch_all_models
    return await fetch_all_models()


@app.get("/files", tags=["Files"])
async def download_file(
    path: str = Query(..., description="File path inside kali-sandbox (must be under /tmp/)"),
):
    """
    Download a file from kali-sandbox via the kali_shell MCP tool.

    Reads the file using base64 encoding through the existing MCP tool,
    decodes it, and returns the binary content.
    Security: Only paths under /tmp/ are allowed.
    """
    # Security: restrict to /tmp/ paths and prevent directory traversal
    if not path.startswith("/tmp/"):
        return Response(content="Forbidden: only /tmp/ paths allowed", status_code=403)
    normalized = os.path.normpath(path)
    if not normalized.startswith("/tmp/"):
        return Response(content="Forbidden: path traversal detected", status_code=403)

    if not orchestrator or not orchestrator.tool_executor:
        return Response(content="Agent not initialized", status_code=503)

    try:
        # Check file exists first
        check_result = await orchestrator.tool_executor.execute(
            "kali_shell",
            {"command": f"test -f {normalized} && stat -c '%s' {normalized}"},
            "informational",
            skip_phase_check=True,
        )
        if not check_result.get("success") or not check_result.get("output", "").strip():
            return Response(content="File not found", status_code=404)

        # Read file as base64
        b64_result = await orchestrator.tool_executor.execute(
            "kali_shell",
            {"command": f"base64 -w0 {normalized}"},
            "informational",
            skip_phase_check=True,
        )
        if not b64_result.get("success"):
            return Response(
                content=f"Error reading file: {b64_result.get('error', 'unknown')}",
                status_code=500,
            )

        b64_str = (b64_result.get("output") or "").strip()
        file_bytes = base64.b64decode(b64_str)
        filename = os.path.basename(normalized)

        # Content type mapping for common payload/document types
        ext = os.path.splitext(filename)[1].lower()
        content_types = {
            ".exe": "application/x-msdownload",
            ".elf": "application/x-elf",
            ".pdf": "application/pdf",
            ".docm": "application/vnd.ms-word.document.macroEnabled.12",
            ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
            ".apk": "application/vnd.android.package-archive",
            ".war": "application/x-webarchive",
            ".ps1": "text/plain",
            ".py": "text/plain",
            ".sh": "text/plain",
            ".hta": "text/html",
            ".lnk": "application/x-ms-shortcut",
            ".rtf": "application/rtf",
            ".vba": "text/plain",
            ".macho": "application/x-mach-binary",
        }
        content_type = content_types.get(ext, "application/octet-stream")

        return Response(
            content=file_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(file_bytes)),
            },
        )
    except Exception as e:
        logger.error(f"File download error: {e}")
        return Response(content=f"Error reading file: {str(e)}", status_code=500)


# =============================================================================
# COMMAND WHISPERER — NLP-to-command translation using the project's LLM
# =============================================================================

_COMMAND_WHISPERER_SYSTEM_PROMPT = """You are a command-line expert for penetration testing.
The user has an active {session_type} session and needs a command.

Session type details:
- "meterpreter": Meterpreter commands (hashdump, getsystem, upload, download, sysinfo, getuid, ps, migrate, search, cat, ls, portfwd, route, load, etc.)
- "shell": Standard Linux/Unix shell commands (find, grep, cat, ls, whoami, id, uname, ifconfig, netstat, awk, sed, curl, wget, chmod, python, perl, etc.)

Rules:
1. Output ONLY the command — no explanations, no markdown, no commentary
2. Single command (use && or ; to chain if needed)
3. No sudo unless explicitly requested
4. Prefer concise, commonly-used flags
5. If ambiguous, pick the most likely interpretation"""


class CommandWhispererRequest(BaseModel):
    prompt: str
    session_type: str
    project_id: str


@app.post("/command-whisperer", tags=["Sessions"])
async def command_whisperer(body: CommandWhispererRequest):
    """Translate a natural language request into a shell command using the project's LLM."""
    if not orchestrator or not orchestrator._initialized:
        return JSONResponse(content={"error": "Agent not initialized"}, status_code=503)

    # Ensure LLM is set up for this project
    if not orchestrator.llm:
        try:
            orchestrator._apply_project_settings(body.project_id)
        except Exception as e:
            logger.error(f"Command whisperer LLM setup error: {e}")
            return JSONResponse(
                content={"error": "LLM not configured. Open the AI assistant first or check API keys."},
                status_code=503,
            )

    if not orchestrator.llm:
        return JSONResponse(content={"error": "LLM not available"}, status_code=503)

    try:
        system_prompt = _COMMAND_WHISPERER_SYSTEM_PROMPT.format(
            session_type=body.session_type,
        )
        response = await orchestrator.llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=body.prompt),
        ])

        command = normalize_content(response.content).strip()

        # Strip markdown code fences if the LLM wraps the answer
        if command.startswith("```") and command.endswith("```"):
            command = command[3:-3].strip()
        if command.startswith(("bash\n", "sh\n", "shell\n")):
            command = command.split("\n", 1)[1].strip()

        return {"command": command}

    except Exception as e:
        logger.error(f"Command whisperer error: {e}")
        return JSONResponse(
            content={"error": f"Failed to generate command: {str(e)}"},
            status_code=500,
        )


# =============================================================================
# SESSION MANAGEMENT PROXY — proxies to kali-sandbox:8013 session endpoints
# =============================================================================

# Derive base URL from existing progress URL (already in docker-compose)
_SESSION_BASE = os.environ.get(
    "MCP_METASPLOIT_PROGRESS_URL", "http://kali-sandbox:8013/progress"
).rsplit("/progress", 1)[0]


@app.get("/sessions", tags=["Sessions"])
async def get_sessions():
    """List all active Metasploit sessions, background jobs, and non-MSF sessions."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{_SESSION_BASE}/sessions")
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except httpx.TimeoutException:
        return JSONResponse(content={"error": "Session manager timeout"}, status_code=504)
    except Exception as e:
        logger.error(f"Session proxy error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=502)


@app.post("/sessions/{session_id}/interact", tags=["Sessions"])
async def interact_session(session_id: int, body: dict):
    """Send a command to a specific Metasploit session."""
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(
                f"{_SESSION_BASE}/sessions/{session_id}/interact", json=body
            )
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except httpx.TimeoutException:
        return JSONResponse(content={"error": "Session interaction timeout"}, status_code=504)
    except Exception as e:
        logger.error(f"Session interact proxy error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=502)


@app.post("/sessions/{session_id}/kill", tags=["Sessions"])
async def kill_session(session_id: int):
    """Kill a specific Metasploit session."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{_SESSION_BASE}/sessions/{session_id}/kill")
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.error(f"Session kill proxy error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=502)


@app.post("/jobs/{job_id}/kill", tags=["Sessions"])
async def kill_job(job_id: int):
    """Kill a background Metasploit job."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{_SESSION_BASE}/jobs/{job_id}/kill")
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.error(f"Job kill proxy error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=502)


@app.post("/session-chat-map", tags=["Sessions"])
async def session_chat_map(body: dict):
    """Register a mapping between a Metasploit session ID and agent chat session ID."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{_SESSION_BASE}/session-chat-map", json=body)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.error(f"Session chat map proxy error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=502)


@app.post("/non-msf-sessions", tags=["Sessions"])
async def register_non_msf_session(body: dict):
    """Register a non-Metasploit session (netcat, socat, etc.)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{_SESSION_BASE}/non-msf-sessions", json=body)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.error(f"Non-MSF session register proxy error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=502)


@app.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent communication.

    Provides bidirectional streaming of:
    - LLM thinking process
    - Tool executions and outputs
    - Phase transitions
    - Approval requests
    - Agent questions
    - Todo list updates

    The client must send an 'init' message first to authenticate the session.
    """
    if not orchestrator:
        await websocket.close(code=1011, reason="Orchestrator not initialized")
        return

    if not ws_manager:
        await websocket.close(code=1011, reason="WebSocket manager not initialized")
        return

    await websocket_endpoint(websocket, orchestrator, ws_manager)


# =============================================================================
# CYPHERFIX WEBSOCKET ENDPOINTS
# =============================================================================


@app.websocket("/ws/cypherfix-triage")
async def cypherfix_triage_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for CypherFix triage agent.

    Runs vulnerability triage: collects findings from Neo4j graph,
    correlates and prioritizes them, generates remediation items.
    """
    from cypherfix_triage.websocket_handler import handle_triage_websocket
    await handle_triage_websocket(websocket)


@app.websocket("/ws/cypherfix-codefix")
async def cypherfix_codefix_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for CypherFix CodeFix agent.

    Runs automated code remediation: clones repo, explores codebase,
    implements fix, streams diff blocks for review, creates PR.
    """
    from cypherfix_codefix.websocket_handler import handle_codefix_websocket
    await handle_codefix_websocket(websocket)
