"""
RedAmon Claude Code Proxy
=========================
Runs on the HOST machine. Exposes two APIs:

  POST /claude               — tool use (claude --print, raw text output)
  POST /v1/chat/completions  — OpenAI-compatible chat API for LLM orchestrator
  GET  /v1/models            — OpenAI-compatible model list
  GET  /health               — liveness probe

The agent container calls this via host.docker.internal:8099 so it uses the
host's existing Claude Code login session (macOS Keychain OAuth) — no API
key needs to be configured anywhere in RedAmon.

Start:  ./redamon.sh start-claude-proxy
Stop:   ./redamon.sh stop-claude-proxy
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [claude-proxy] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

CLAUDE_BIN = shutil.which("claude") or os.environ.get("CLAUDE_BIN", "claude")
PROXY_PORT = int(os.environ.get("CLAUDE_PROXY_PORT", "8099"))
TASK_TIMEOUT = int(os.environ.get("CLAUDE_PROXY_TIMEOUT", "300"))

# Claude Code models available via subscription (no API key needed)
CLAUDE_CODE_MODELS = [
    {
        "id": "claude-code/claude-opus-4-6",
        "object": "model",
        "created": 1700000000,
        "owned_by": "anthropic",
        "display_name": "Claude Opus 4.6 (via Claude Code)",
        "context_length": 200000,
    },
    {
        "id": "claude-code/claude-sonnet-4-6",
        "object": "model",
        "created": 1700000001,
        "owned_by": "anthropic",
        "display_name": "Claude Sonnet 4.6 (via Claude Code)",
        "context_length": 200000,
    },
    {
        "id": "claude-code/claude-sonnet-4-5-20251001",
        "object": "model",
        "created": 1700000002,
        "owned_by": "anthropic",
        "display_name": "Claude Sonnet 4.5 (via Claude Code)",
        "context_length": 200000,
    },
    {
        "id": "claude-code/claude-haiku-4-5-20251001",
        "object": "model",
        "created": 1700000003,
        "owned_by": "anthropic",
        "display_name": "Claude Haiku 4.5 (via Claude Code)",
        "context_length": 200000,
    },
    {
        "id": "claude-code/claude-opus-4-5-20251101",
        "object": "model",
        "created": 1700000004,
        "owned_by": "anthropic",
        "display_name": "Claude Opus 4.5 (via Claude Code)",
        "context_length": 200000,
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    resolved = shutil.which(CLAUDE_BIN) or (CLAUDE_BIN if os.path.isfile(CLAUDE_BIN) else None)
    if not resolved:
        logger.error(
            f"Claude Code CLI not found at '{CLAUDE_BIN}'. "
            "Install: npm install -g @anthropic-ai/claude-code"
        )
        sys.exit(1)
    logger.info(
        f"Claude Code proxy ready on :{PROXY_PORT} "
        f"(binary: {CLAUDE_BIN}, timeout: {TASK_TIMEOUT}s)"
    )
    yield


app = FastAPI(title="RedAmon Claude Code Proxy", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Internal: run claude --print
# ---------------------------------------------------------------------------

async def _run_claude(prompt: str, working_directory: str = "/tmp") -> tuple[str, bool]:
    """
    Run `claude --print <prompt>` in a subprocess.
    Returns (output_text, success).
    """
    work_dir = working_directory if os.path.isdir(working_directory) else "/tmp"
    env = os.environ.copy()
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

    cmd = [CLAUDE_BIN, "--print", prompt]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=work_dir,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TASK_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return f"Claude Code timed out after {TASK_TIMEOUT}s.", False

    output = stdout.decode("utf-8", errors="replace").strip()
    error_output = stderr.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        err = error_output or f"Process exited with code {proc.returncode}"
        logger.error(f"Claude Code failed (exit {proc.returncode}): {err[:300]}")
        return f"Claude Code error (exit {proc.returncode}):\n{err}", False

    return output or "Claude Code completed with no output.", True


def _messages_to_prompt(messages: list[dict]) -> str:
    """
    Convert an OpenAI messages array into a single prompt string for
    `claude --print`. Roles: system, user, assistant, tool.
    Tools definitions and prior tool_calls are embedded as structured text.
    """
    parts: list[str] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content") or ""

        # Content may be a list of content blocks (OpenAI multi-modal format)
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        text_parts.append(
                            f"[Tool result for {block.get('tool_use_id','')}]: "
                            f"{block.get('content','')}"
                        )
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)

        if role == "system":
            parts.append(f"<system>\n{content}\n</system>")
        elif role == "user":
            parts.append(f"<user>\n{content}\n</user>")
        elif role == "assistant":
            # Include any prior tool_calls as text so Claude understands the flow
            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                tc_text = json.dumps(tool_calls, indent=2)
                parts.append(f"<assistant>\n{content}\n[tool_calls]:\n{tc_text}\n</assistant>")
            else:
                parts.append(f"<assistant>\n{content}\n</assistant>")
        elif role == "tool":
            parts.append(
                f"<tool_result name='{msg.get('name','')}' "
                f"id='{msg.get('tool_call_id','')}'>\n{content}\n</tool_result>"
            )

    return "\n\n".join(parts)


def _build_openai_response(model: str, content: str, finish_reason: str = "stop") -> dict:
    """Build an OpenAI-compatible chat completion response dict."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": finish_reason,
                "logprobs": None,
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


# ---------------------------------------------------------------------------
# RedAmon tool-use endpoint  (used by ClaudeCodeToolManager)
# ---------------------------------------------------------------------------

class ClaudeRequest(BaseModel):
    task: str
    working_directory: str = "/tmp"


@app.get("/health")
async def health():
    return {"status": "ok", "binary": CLAUDE_BIN}


@app.post("/claude")
async def run_claude_tool(req: ClaudeRequest):
    """Tool-use endpoint: run a task and return plain text output."""
    logger.info(f"[tool] Running claude --print (task: {len(req.task)} chars, dir: {req.working_directory})")
    output, success = await _run_claude(req.task, req.working_directory)
    return {"output": output, "success": success}


# ---------------------------------------------------------------------------
# OpenAI-compatible API  (used by LangChain ChatOpenAI as the orchestrator LLM)
# ---------------------------------------------------------------------------

@app.get("/v1/models")
async def list_models():
    """Return the list of Claude Code models in OpenAI format."""
    return {"object": "list", "data": CLAUDE_CODE_MODELS}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completions endpoint.
    Converts the messages array to a prompt and runs claude --print.
    Supports both streaming (SSE) and non-streaming responses.
    Tools/functions are embedded into the prompt as structured text.
    """
    body: dict[str, Any] = await request.json()

    messages: list[dict] = body.get("messages", [])
    model: str = body.get("model", "claude-code/claude-opus-4-6")
    stream: bool = body.get("stream", False)

    # Embed tool definitions into the system prompt if provided
    tools: list[dict] = body.get("tools", [])
    tool_prompt = ""
    if tools:
        tool_prompt = (
            "\n\n[Available tools — respond with a JSON object "
            "{\"tool\": \"<name>\", \"args\": {...}} when you want to call one]\n"
            + json.dumps(tools, indent=2)
        )

    prompt = _messages_to_prompt(messages)
    if tool_prompt:
        prompt = tool_prompt + "\n\n" + prompt

    logger.info(
        f"[chat] model={model}, messages={len(messages)}, "
        f"tools={len(tools)}, stream={stream}"
    )

    output, _ = await _run_claude(prompt)

    if stream:
        # SSE streaming: send a single chunk then done
        resp_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        async def sse_generator():
            chunk = {
                "id": resp_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": output},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk)}\n\n"

            done_chunk = {
                "id": resp_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(done_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    return JSONResponse(_build_openai_response(model, output))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT, log_level="info")
