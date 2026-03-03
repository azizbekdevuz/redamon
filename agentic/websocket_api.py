"""
WebSocket API for RedAmon Agent

Provides WebSocket endpoint for real-time bidirectional communication with the agent.
Supports streaming of LLM thoughts, tool executions, and interactive approval/question flows.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Any, Callable
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from orchestrator_helpers import create_config
from chat_persistence import save_chat_message, update_conversation


def serialize_for_json(obj):
    """Convert objects to JSON-serializable format, handling datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    return obj

logger = logging.getLogger(__name__)


# =============================================================================
# MESSAGE TYPE DEFINITIONS
# =============================================================================

class MessageType(str, Enum):
    """WebSocket message types"""
    # Client → Server
    INIT = "init"
    QUERY = "query"
    APPROVAL = "approval"
    ANSWER = "answer"
    PING = "ping"
    GUIDANCE = "guidance"
    STOP = "stop"
    RESUME = "resume"

    # Server → Client
    CONNECTED = "connected"
    THINKING = "thinking"
    THINKING_CHUNK = "thinking_chunk"
    TOOL_START = "tool_start"
    TOOL_OUTPUT_CHUNK = "tool_output_chunk"
    TOOL_COMPLETE = "tool_complete"
    PHASE_UPDATE = "phase_update"
    TODO_UPDATE = "todo_update"
    APPROVAL_REQUEST = "approval_request"
    QUESTION_REQUEST = "question_request"
    RESPONSE = "response"
    EXECUTION_STEP = "execution_step"
    ERROR = "error"
    PONG = "pong"
    TASK_COMPLETE = "task_complete"
    GUIDANCE_ACK = "guidance_ack"
    STOPPED = "stopped"
    FILE_READY = "file_ready"


# =============================================================================
# CLIENT MESSAGE MODELS
# =============================================================================

class InitMessage(BaseModel):
    """Initialize WebSocket session"""
    user_id: str
    project_id: str
    session_id: str


class QueryMessage(BaseModel):
    """Send query to agent"""
    question: str


class ApprovalMessage(BaseModel):
    """Respond to phase transition approval request"""
    decision: str  # 'approve' | 'modify' | 'abort'
    modification: Optional[str] = None


class AnswerMessage(BaseModel):
    """Answer agent's question"""
    answer: str


class GuidanceMessage(BaseModel):
    """Send guidance to steer agent while it's working"""
    message: str


# =============================================================================
# WEBSOCKET CONNECTION MANAGER
# =============================================================================

class WebSocketConnection:
    """Manages individual WebSocket connection state"""

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.user_id: Optional[str] = None
        self.project_id: Optional[str] = None
        self.session_id: Optional[str] = None
        self.authenticated = False
        self.connected_at = datetime.utcnow()
        self.last_ping = datetime.utcnow()
        self.guidance_queue: asyncio.Queue = asyncio.Queue()
        self._active_task: Optional[Any] = None
        self._is_stopped: bool = False

    async def send_message(self, message_type: MessageType, payload: Any):
        """Send JSON message to client. Gracefully handles closed connections."""
        try:
            # Serialize payload to handle datetime objects
            serialized_payload = serialize_for_json(payload)
            message = {
                "type": message_type.value,
                "payload": serialized_payload,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self.websocket.send_json(message)
            logger.debug(f"Sent {message_type.value} message to {self.session_id}")
        except Exception as e:
            # Gracefully handle closed WebSocket (e.g. user switched conversation)
            # Messages are still persisted via chat_persistence
            logger.debug(f"WebSocket send failed for {self.session_id} (client may have switched): {e}")

    def drain_guidance(self) -> list:
        """Drain all pending guidance messages from the queue (non-blocking)."""
        messages = []
        while not self.guidance_queue.empty():
            try:
                messages.append(self.guidance_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    def get_key(self) -> Optional[str]:
        """Get unique key for this connection"""
        if self.authenticated:
            return f"{self.user_id}:{self.project_id}:{self.session_id}"
        return None


class WebSocketManager:
    """Manages active WebSocket connections"""

    def __init__(self):
        # Map of session_key → WebSocketConnection
        self.active_connections: Dict[str, WebSocketConnection] = {}
        # Separate task registry keyed by session_key — survives connection replacement
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> WebSocketConnection:
        """Accept new WebSocket connection"""
        await websocket.accept()
        connection = WebSocketConnection(websocket)
        logger.info(f"WebSocket connection accepted from {websocket.client}")
        return connection

    async def authenticate(
        self,
        connection: WebSocketConnection,
        user_id: str,
        project_id: str,
        session_id: str
    ):
        """Authenticate and register connection"""
        async with self.lock:
            connection.user_id = user_id
            connection.project_id = project_id
            connection.session_id = session_id
            connection.authenticated = True

            session_key = connection.get_key()

            # Transfer running task from old connection if reconnecting
            if session_key in self.active_connections:
                old_conn = self.active_connections[session_key]
                # Transfer active task and state to the new connection
                if old_conn._active_task and not old_conn._active_task.done():
                    connection._active_task = old_conn._active_task
                    connection._is_stopped = old_conn._is_stopped
                    connection.guidance_queue = old_conn.guidance_queue
                    logger.info(f"Transferred running task to new connection for {session_key}")
                try:
                    await old_conn.websocket.close(code=1000, reason="New connection established")
                except Exception as e:
                    logger.warning(f"Error closing old connection: {e}")

            self.active_connections[session_key] = connection
            logger.info(f"Authenticated session: {session_key}")

    async def disconnect(self, connection: WebSocketConnection):
        """Remove connection from active connections (only if it's the SAME object)"""
        async with self.lock:
            session_key = connection.get_key()
            if session_key and session_key in self.active_connections:
                # Identity check: don't remove a newer connection that replaced us
                if self.active_connections[session_key] is connection:
                    del self.active_connections[session_key]
                    logger.info(f"Disconnected session: {session_key}")
                else:
                    logger.debug(f"Skipped disconnect for {session_key} — connection already replaced")

    def register_task(self, session_key: str, task: asyncio.Task):
        """Register an active task for a session (survives connection replacement)"""
        self._active_tasks[session_key] = task

    def get_task(self, session_key: str) -> Optional[asyncio.Task]:
        """Get active (non-done) task for a session"""
        task = self._active_tasks.get(session_key)
        if task and task.done():
            del self._active_tasks[session_key]
            return None
        return task

    def clear_task(self, session_key: str):
        """Remove task from registry"""
        self._active_tasks.pop(session_key, None)

    def get_connection(self, user_id: str, project_id: str, session_id: str) -> Optional[WebSocketConnection]:
        """Get active connection by session identifiers"""
        session_key = f"{user_id}:{project_id}:{session_id}"
        return self.active_connections.get(session_key)

    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)


# =============================================================================
# STREAMING CALLBACK INTERFACE
# =============================================================================

class StreamingCallback:
    """Callback interface for streaming events from orchestrator.

    Also persists messages to the webapp database via chat_persistence.
    Uses dynamic connection resolution so reconnecting users see live updates.

    Persistence uses an ordered asyncio.Queue so messages are saved
    sequentially in the exact order they were emitted — preventing the
    race condition where concurrent HTTP POSTs arrive out-of-order and
    get wrong sequenceNum values.
    """

    def __init__(self, connection: WebSocketConnection, ws_manager: Optional['WebSocketManager'] = None):
        self._original_connection = connection
        self._session_key = connection.get_key()
        self._ws_manager = ws_manager
        self._session_id = connection.session_id
        self._project_id = connection.project_id
        self._user_id = connection.user_id
        # Response and task_complete are truly once-per-session events
        self._task_complete_sent = False
        self._response_sent = False
        # Accumulate tool output per tool_name so tool_complete includes raw output
        self._tool_context: dict = {}  # tool_name -> {"args": dict, "chunks": list[str]}
        # Ordered persistence queue — messages are saved one-at-a-time in FIFO order
        self._persist_queue: asyncio.Queue = asyncio.Queue()
        self._persist_worker_task: Optional[asyncio.Task] = None

    def _ensure_persist_worker(self):
        """Lazily start the background persist worker."""
        if self._persist_worker_task is None or self._persist_worker_task.done():
            self._persist_worker_task = asyncio.create_task(self._persist_worker())

    async def _persist_worker(self):
        """Process persist messages sequentially to guarantee ordering."""
        while True:
            msg_type, data = await self._persist_queue.get()
            try:
                await save_chat_message(
                    session_id=self._session_id,
                    msg_type=msg_type,
                    data=data,
                    project_id=self._project_id,
                    user_id=self._user_id,
                )
            except Exception as e:
                logger.warning(f"Persist worker error: {e}")
            finally:
                self._persist_queue.task_done()

    async def drain_persist_queue(self):
        """Wait for all pending persist messages to be saved, then stop the worker."""
        if self._persist_queue.qsize() > 0:
            await self._persist_queue.join()
        if self._persist_worker_task and not self._persist_worker_task.done():
            self._persist_worker_task.cancel()

    @property
    def connection(self) -> WebSocketConnection:
        """Always resolve to the current connection (may have been replaced by reconnect)."""
        if self._ws_manager and self._session_key:
            conn = self._ws_manager.active_connections.get(self._session_key)
            if conn:
                return conn
        return self._original_connection

    def _persist(self, msg_type: str, data: dict):
        """Enqueue message for ordered persistence to DB."""
        self._ensure_persist_worker()
        self._persist_queue.put_nowait((msg_type, data))

    async def on_thinking(self, iteration: int, phase: str, thought: str, reasoning: str):
        """Called when agent starts thinking"""
        payload = {
            "iteration": iteration,
            "phase": phase,
            "thought": thought,
            "reasoning": reasoning
        }
        await self.connection.send_message(MessageType.THINKING, payload)
        self._persist("thinking", payload)

    async def on_thinking_chunk(self, chunk: str):
        """Called during LLM generation for streaming thoughts"""
        await self.connection.send_message(MessageType.THINKING_CHUNK, {
            "chunk": chunk
        })
        # Don't persist chunks — they are partial data; the full thinking is persisted via on_thinking

    async def on_tool_start(self, tool_name: str, tool_args: dict):
        """Called when tool execution starts"""
        payload = {
            "tool_name": tool_name,
            "tool_args": tool_args
        }
        await self.connection.send_message(MessageType.TOOL_START, payload)
        self._persist("tool_start", payload)
        # Initialize accumulator for this tool's output chunks
        self._tool_context[tool_name] = {"args": tool_args, "chunks": []}

    async def on_tool_output_chunk(self, tool_name: str, chunk: str, is_final: bool = False):
        """Called when tool outputs data chunk"""
        await self.connection.send_message(MessageType.TOOL_OUTPUT_CHUNK, {
            "tool_name": tool_name,
            "chunk": chunk,
            "is_final": is_final
        })
        # Accumulate chunks — they'll be joined and included in tool_complete
        if tool_name in self._tool_context:
            self._tool_context[tool_name]["chunks"].append(chunk)

    async def on_tool_complete(
        self,
        tool_name: str,
        success: bool,
        output_summary: str,
        actionable_findings: list = None,
        recommended_next_steps: list = None,
    ):
        """Called when tool execution completes"""
        payload = {
            "tool_name": tool_name,
            "success": success,
            "output_summary": output_summary,
            "actionable_findings": actionable_findings or [],
            "recommended_next_steps": recommended_next_steps or [],
        }
        await self.connection.send_message(MessageType.TOOL_COMPLETE, payload)
        # Include accumulated raw output and tool_args in persisted payload
        ctx = self._tool_context.pop(tool_name, {})
        persist_payload = {
            **payload,
            "tool_args": ctx.get("args", {}),
            "raw_output": "".join(ctx.get("chunks", [])),
        }
        self._persist("tool_complete", persist_payload)

    async def on_phase_update(self, current_phase: str, iteration_count: int, attack_path_type: str = "cve_exploit"):
        """Called when phase changes"""
        payload = {
            "current_phase": current_phase,
            "iteration_count": iteration_count,
            "attack_path_type": attack_path_type
        }
        await self.connection.send_message(MessageType.PHASE_UPDATE, payload)
        # Persist phase update as message + update conversation metadata
        self._persist("phase_update", payload)
        asyncio.create_task(update_conversation(
            self._session_id,
            {"currentPhase": current_phase, "iterationCount": iteration_count},
        ))

    async def on_todo_update(self, todo_list: list):
        """Called when todo list is updated"""
        await self.connection.send_message(MessageType.TODO_UPDATE, {
            "todo_list": todo_list
        })
        self._persist("todo_update", {"todo_list": todo_list})

    async def on_approval_request(self, approval_request: dict):
        """Called when agent requests phase transition approval"""
        # Deduplication is handled by orchestrator using _emitted_approval marker in state
        await self.connection.send_message(MessageType.APPROVAL_REQUEST, approval_request)
        self._persist("approval_request", approval_request)
        logger.info(f"Approval request sent to session {self.connection.session_id}")

    async def on_question_request(self, question_request: dict):
        """Called when agent asks user a question"""
        # Deduplication is handled by orchestrator using _emitted_question marker in state
        await self.connection.send_message(MessageType.QUESTION_REQUEST, question_request)
        self._persist("question_request", question_request)
        logger.info(f"Question request sent to session {self.connection.session_id}")

    async def on_response(self, answer: str, iteration_count: int, phase: str, task_complete: bool, response_tier: str = "full_report"):
        """Called when agent provides final response"""
        if not self._response_sent:
            payload = {
                "answer": answer,
                "iteration_count": iteration_count,
                "phase": phase,
                "task_complete": task_complete,
                "response_tier": response_tier,
            }
            await self.connection.send_message(MessageType.RESPONSE, payload)
            self._response_sent = True
            self._persist("assistant_message", {"content": answer, "phase": phase, "task_complete": task_complete, "response_tier": response_tier})
            logger.info(f"Response sent to session {self.connection.session_id} (tier: {response_tier})")
        else:
            logger.debug(f"Duplicate response blocked for session {self.connection.session_id}")

    async def on_execution_step(self, step: dict):
        """Called after each execution step"""
        await self.connection.send_message(MessageType.EXECUTION_STEP, step)

    async def on_error(self, error_message: str, recoverable: bool = True):
        """Called when error occurs"""
        payload = {"message": error_message, "recoverable": recoverable}
        await self.connection.send_message(MessageType.ERROR, payload)
        self._persist("error", payload)

    async def on_task_complete(self, message: str, final_phase: str, total_iterations: int):
        """Called when task is complete"""
        if not self._task_complete_sent:
            payload = {
                "message": message,
                "final_phase": final_phase,
                "total_iterations": total_iterations
            }
            await self.connection.send_message(MessageType.TASK_COMPLETE, payload)
            self._task_complete_sent = True
            self._persist("task_complete", payload)
            logger.info(f"Task complete sent to session {self.connection.session_id}")
        else:
            logger.debug(f"Duplicate task_complete blocked for session {self.connection.session_id}")

    async def on_file_ready(self, file_info: dict):
        """Called when agent has created a downloadable file."""
        await self.connection.send_message(MessageType.FILE_READY, file_info)
        self._persist("file_ready", file_info)
        logger.info(f"File ready notification sent: {file_info.get('filename')}")


# =============================================================================
# MESSAGE HANDLERS
# =============================================================================

class WebSocketHandler:
    """Handles WebSocket messages and routes to orchestrator"""

    def __init__(self, orchestrator, ws_manager: WebSocketManager):
        self.orchestrator = orchestrator
        self.ws_manager = ws_manager

    async def handle_init(self, connection: WebSocketConnection, payload: dict):
        """Handle session initialization"""
        try:
            init_msg = InitMessage(**payload)

            # Authenticate connection
            await self.ws_manager.authenticate(
                connection,
                init_msg.user_id,
                init_msg.project_id,
                init_msg.session_id
            )

            # Send connected confirmation
            await connection.send_message(MessageType.CONNECTED, {
                "session_id": init_msg.session_id,
                "message": "WebSocket connection established",
                "timestamp": datetime.utcnow().isoformat()
            })

            logger.info(f"Session initialized: {init_msg.session_id}")

        except ValidationError as e:
            logger.error(f"Invalid init message: {e}")
            await connection.send_message(MessageType.ERROR, {
                "message": "Invalid initialization message",
                "recoverable": False
            })

    async def handle_query(self, connection: WebSocketConnection, payload: dict):
        """Handle user query — launches orchestrator as background task"""
        try:
            query_msg = QueryMessage(**payload)

            if not connection.authenticated:
                await connection.send_message(MessageType.ERROR, {
                    "message": "Not authenticated. Send init message first.",
                    "recoverable": False
                })
                return

            # Create streaming callback with ws_manager for dynamic connection resolution
            callback = StreamingCallback(connection, self.ws_manager)
            connection._is_stopped = False
            # Drain stale guidance from previous runs
            connection.drain_guidance()

            logger.info(f"Processing query for session {connection.session_id}: {query_msg.question[:50]}...")

            # Mark agent as running in DB
            asyncio.create_task(update_conversation(connection.session_id, {"agentRunning": True}))

            # Persist the user message via the callback's ordered queue so it
            # gets a sequenceNum *before* any thinking/tool messages
            callback._persist("user_message", {"content": query_msg.question})

            # Run orchestrator as background task so receive loop stays free
            task = asyncio.create_task(
                self._run_orchestrator_query(connection, query_msg.question, callback)
            )
            connection._active_task = task
            self.ws_manager.register_task(connection.get_key(), task)

        except ValidationError as e:
            logger.error(f"Invalid query message: {e}")
            await connection.send_message(MessageType.ERROR, {
                "message": "Invalid query format",
                "recoverable": True
            })

    async def _run_orchestrator_query(self, connection: WebSocketConnection, question: str, callback):
        """Background coroutine that runs the orchestrator invocation."""
        try:
            result = await self.orchestrator.invoke_with_streaming(
                question=question,
                user_id=connection.user_id,
                project_id=connection.project_id,
                session_id=connection.session_id,
                streaming_callback=callback,
                guidance_queue=connection.guidance_queue,
            )
            logger.info(f"Query completed for session {connection.session_id}")
        except asyncio.CancelledError:
            logger.info(f"Query task cancelled for session {connection.session_id}")
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            try:
                await callback.connection.send_message(MessageType.ERROR, {
                    "message": f"Error processing query: {str(e)}",
                    "recoverable": True
                })
            except Exception:
                pass
        finally:
            # Drain the persist queue so all messages are saved before marking agent as done
            await callback.drain_persist_queue()
            connection._active_task = None
            self.ws_manager.clear_task(connection.get_key())
            asyncio.create_task(update_conversation(connection.session_id, {"agentRunning": False}))

    async def handle_approval(self, connection: WebSocketConnection, payload: dict):
        """Handle approval response — launches as background task"""
        try:
            approval_msg = ApprovalMessage(**payload)

            if not connection.authenticated:
                await connection.send_message(MessageType.ERROR, {
                    "message": "Not authenticated",
                    "recoverable": False
                })
                return

            callback = StreamingCallback(connection, self.ws_manager)
            connection._is_stopped = False

            logger.info(f"Processing approval for session {connection.session_id}: {approval_msg.decision}")

            asyncio.create_task(update_conversation(connection.session_id, {"agentRunning": True}))

            task = asyncio.create_task(
                self._run_orchestrator_approval(connection, approval_msg, callback)
            )
            connection._active_task = task
            self.ws_manager.register_task(connection.get_key(), task)

        except ValidationError as e:
            logger.error(f"Invalid approval message: {e}")
            await connection.send_message(MessageType.ERROR, {
                "message": "Invalid approval format",
                "recoverable": True
            })

    async def _run_orchestrator_approval(self, connection: WebSocketConnection, approval_msg: ApprovalMessage, callback):
        """Background coroutine that runs approval resumption."""
        try:
            result = await self.orchestrator.resume_after_approval_with_streaming(
                session_id=connection.session_id,
                user_id=connection.user_id,
                project_id=connection.project_id,
                decision=approval_msg.decision,
                modification=approval_msg.modification,
                streaming_callback=callback,
                guidance_queue=connection.guidance_queue,
            )
            logger.info(f"Approval processed for session {connection.session_id}")
        except asyncio.CancelledError:
            logger.info(f"Approval task cancelled for session {connection.session_id}")
        except Exception as e:
            logger.error(f"Error processing approval: {e}")
            try:
                await callback.connection.send_message(MessageType.ERROR, {
                    "message": f"Error processing approval: {str(e)}",
                    "recoverable": True
                })
            except Exception:
                pass
        finally:
            await callback.drain_persist_queue()
            connection._active_task = None
            self.ws_manager.clear_task(connection.get_key())
            asyncio.create_task(update_conversation(connection.session_id, {"agentRunning": False}))

    async def handle_answer(self, connection: WebSocketConnection, payload: dict):
        """Handle answer to agent question — launches as background task"""
        try:
            answer_msg = AnswerMessage(**payload)

            if not connection.authenticated:
                await connection.send_message(MessageType.ERROR, {
                    "message": "Not authenticated",
                    "recoverable": False
                })
                return

            callback = StreamingCallback(connection, self.ws_manager)
            connection._is_stopped = False

            logger.info(f"Processing answer for session {connection.session_id}")

            asyncio.create_task(update_conversation(connection.session_id, {"agentRunning": True}))

            task = asyncio.create_task(
                self._run_orchestrator_answer(connection, answer_msg.answer, callback)
            )
            connection._active_task = task
            self.ws_manager.register_task(connection.get_key(), task)

        except ValidationError as e:
            logger.error(f"Invalid answer message: {e}")
            await connection.send_message(MessageType.ERROR, {
                "message": "Invalid answer format",
                "recoverable": True
            })

    async def _run_orchestrator_answer(self, connection: WebSocketConnection, answer: str, callback):
        """Background coroutine that runs answer resumption."""
        try:
            result = await self.orchestrator.resume_after_answer_with_streaming(
                session_id=connection.session_id,
                user_id=connection.user_id,
                project_id=connection.project_id,
                answer=answer,
                streaming_callback=callback,
                guidance_queue=connection.guidance_queue,
            )
            logger.info(f"Answer processed for session {connection.session_id}")
        except asyncio.CancelledError:
            logger.info(f"Answer task cancelled for session {connection.session_id}")
        except Exception as e:
            logger.error(f"Error processing answer: {e}")
            try:
                await callback.connection.send_message(MessageType.ERROR, {
                    "message": f"Error processing answer: {str(e)}",
                    "recoverable": True
                })
            except Exception:
                pass
        finally:
            await callback.drain_persist_queue()
            connection._active_task = None
            self.ws_manager.clear_task(connection.get_key())
            asyncio.create_task(update_conversation(connection.session_id, {"agentRunning": False}))

    async def handle_guidance(self, connection: WebSocketConnection, payload: dict):
        """Handle guidance message while agent is executing."""
        try:
            guidance_msg = GuidanceMessage(**payload)

            if not connection.authenticated:
                await connection.send_message(MessageType.ERROR, {
                    "message": "Not authenticated",
                    "recoverable": False
                })
                return

            await connection.guidance_queue.put(guidance_msg.message)
            queue_size = connection.guidance_queue.qsize()

            await connection.send_message(MessageType.GUIDANCE_ACK, {
                "message": guidance_msg.message,
                "queue_position": queue_size,
            })

            logger.info(f"Guidance queued for session {connection.session_id}: {guidance_msg.message[:100]}...")

        except ValidationError as e:
            logger.error(f"Invalid guidance message: {e}")
            await connection.send_message(MessageType.ERROR, {
                "message": "Invalid guidance format",
                "recoverable": True
            })

    async def handle_stop(self, connection: WebSocketConnection, payload: dict):
        """Handle stop request — cancels active agent execution.

        Looks up the task from both the connection AND the central task registry,
        so it works even if a WebSocket reconnection replaced the connection object.
        """
        if not connection.authenticated:
            await connection.send_message(MessageType.ERROR, {
                "message": "Not authenticated",
                "recoverable": False
            })
            return

        session_key = connection.get_key()

        # Find the task: prefer connection-local, fall back to central registry
        task = connection._active_task if (connection._active_task and not connection._active_task.done()) else None
        if not task:
            task = self.ws_manager.get_task(session_key)

        if task and not task.done():
            task.cancel()
            connection._is_stopped = True
            self.ws_manager.clear_task(session_key)

            # Get current state for the STOPPED message
            try:
                config = create_config(connection.user_id, connection.project_id, connection.session_id)
                current_state = await self.orchestrator.graph.aget_state(config)
                iteration = current_state.values.get("current_iteration", 0) if current_state and current_state.values else 0
                phase = current_state.values.get("current_phase", "informational") if current_state and current_state.values else "informational"
            except Exception:
                iteration = 0
                phase = "informational"

            await connection.send_message(MessageType.STOPPED, {
                "message": "Agent execution stopped",
                "iteration": iteration,
                "phase": phase,
            })
            logger.info(f"Execution stopped for session {connection.session_id}")
        else:
            # No active task anywhere — confirm stopped state (e.g. restored
            # conversation where agentRunning was stale in DB).
            connection._is_stopped = True
            await connection.send_message(MessageType.STOPPED, {
                "message": "Agent execution stopped",
                "iteration": 0,
                "phase": "informational",
            })
            asyncio.create_task(update_conversation(connection.session_id, {"agentRunning": False}))

    async def handle_resume(self, connection: WebSocketConnection, payload: dict):
        """Handle resume request — restarts agent from last checkpoint."""
        if not connection.authenticated:
            await connection.send_message(MessageType.ERROR, {
                "message": "Not authenticated",
                "recoverable": False
            })
            return

        if not connection._is_stopped:
            await connection.send_message(MessageType.ERROR, {
                "message": "No stopped execution to resume",
                "recoverable": True,
            })
            return

        connection._is_stopped = False
        callback = StreamingCallback(connection, self.ws_manager)

        asyncio.create_task(update_conversation(connection.session_id, {"agentRunning": True}))

        task = asyncio.create_task(
            self._run_orchestrator_resume(connection, callback)
        )
        connection._active_task = task
        self.ws_manager.register_task(connection.get_key(), task)
        logger.info(f"Resuming execution for session {connection.session_id}")

    async def _run_orchestrator_resume(self, connection: WebSocketConnection, callback):
        """Background coroutine that resumes orchestrator from checkpoint."""
        try:
            result = await self.orchestrator.resume_execution_with_streaming(
                user_id=connection.user_id,
                project_id=connection.project_id,
                session_id=connection.session_id,
                streaming_callback=callback,
                guidance_queue=connection.guidance_queue,
            )
            logger.info(f"Resumed execution completed for session {connection.session_id}")
        except asyncio.CancelledError:
            logger.info(f"Resumed task cancelled for session {connection.session_id}")
        except Exception as e:
            logger.error(f"Error resuming execution: {e}")
            try:
                await callback.connection.send_message(MessageType.ERROR, {
                    "message": f"Error resuming execution: {str(e)}",
                    "recoverable": True
                })
            except Exception:
                pass
        finally:
            await callback.drain_persist_queue()
            connection._active_task = None
            self.ws_manager.clear_task(connection.get_key())
            asyncio.create_task(update_conversation(connection.session_id, {"agentRunning": False}))

    async def handle_ping(self, connection: WebSocketConnection, payload: dict):
        """Handle ping for keep-alive"""
        connection.last_ping = datetime.utcnow()
        await connection.send_message(MessageType.PONG, {})
        logger.debug(f"Pong sent to session {connection.session_id}")

    async def handle_message(self, connection: WebSocketConnection, raw_message: str):
        """Route incoming message to appropriate handler"""
        try:
            message = json.loads(raw_message)
            msg_type = message.get("type")
            payload = message.get("payload", {})

            if msg_type == MessageType.INIT:
                await self.handle_init(connection, payload)
            elif msg_type == MessageType.QUERY:
                await self.handle_query(connection, payload)
            elif msg_type == MessageType.APPROVAL:
                await self.handle_approval(connection, payload)
            elif msg_type == MessageType.ANSWER:
                await self.handle_answer(connection, payload)
            elif msg_type == MessageType.PING:
                await self.handle_ping(connection, payload)
            elif msg_type == MessageType.GUIDANCE:
                await self.handle_guidance(connection, payload)
            elif msg_type == MessageType.STOP:
                await self.handle_stop(connection, payload)
            elif msg_type == MessageType.RESUME:
                await self.handle_resume(connection, payload)
            else:
                logger.warning(f"Unknown message type: {msg_type}")
                await connection.send_message(MessageType.ERROR, {
                    "message": f"Unknown message type: {msg_type}",
                    "recoverable": True
                })

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON message: {e}")
            await connection.send_message(MessageType.ERROR, {
                "message": "Invalid JSON format",
                "recoverable": True
            })
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await connection.send_message(MessageType.ERROR, {
                "message": f"Internal error: {str(e)}",
                "recoverable": True
            })


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

async def websocket_endpoint(
    websocket: WebSocket,
    orchestrator,
    ws_manager: WebSocketManager
):
    """
    Main WebSocket endpoint for agent communication.

    Handles connection lifecycle, message routing, and error handling.
    """
    connection = await ws_manager.connect(websocket)
    handler = WebSocketHandler(orchestrator, ws_manager)

    try:
        while True:
            # Receive message from client
            message_data = await websocket.receive()

            # Check for disconnect event
            if message_data.get("type") == "websocket.disconnect":
                logger.info(f"WebSocket disconnect received: {connection.get_key() or 'unauthenticated'}")
                break

            # Handle different message types
            if "text" in message_data:
                raw_message = message_data["text"]
            elif "bytes" in message_data:
                # Convert bytes to string if sent as binary
                raw_message = message_data["bytes"].decode("utf-8")
            else:
                logger.warning(f"Received unexpected message type: {message_data}")
                continue

            # Handle message
            await handler.handle_message(connection, raw_message)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {connection.get_key() or 'unauthenticated'}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await connection.send_message(MessageType.ERROR, {
                "message": f"Fatal error: {str(e)}",
                "recoverable": False
            })
        except:
            pass
    finally:
        # Don't cancel active tasks — let background agents keep running
        # and persisting messages to DB even when the user disconnects.
        # Tasks will clean up via their own finally blocks.
        if not (connection._active_task and not connection._active_task.done()):
            # Only disconnect if no task is running
            await ws_manager.disconnect(connection)
        else:
            logger.info(f"WebSocket closed but agent task still running for {connection.get_key()}")
