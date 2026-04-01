"""
RedAmon Agent Orchestrator

ReAct-style agent orchestrator with iterative Thought-Tool-Output pattern.
Supports phase tracking, LLM-managed todo lists, and checkpoint-based approval.
"""

import asyncio
import os
import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from state import (
    AgentState,
    InvokeResponse,
    summarize_trace_for_response,
)
from project_settings import get_setting
from key_rotation import KeyRotator
from tools import (
    MCPToolsManager,
    Neo4jToolManager,
    WebSearchToolManager,
    ShodanToolManager,
    GoogleDorkToolManager,
    CensysToolManager,
    FofaToolManager,
    OtxToolManager,
    NetlasToolManager,
    VirusTotalToolManager,
    ZoomEyeToolManager,
    CriminalIpToolManager,
    ClaudeCodeToolManager,
    PhaseAwareToolExecutor,
)
from orchestrator_helpers import (
    set_checkpointer,
    create_config,
    get_config_values,
)
from orchestrator_helpers.llm_setup import setup_llm, apply_project_settings
from orchestrator_helpers.streaming import emit_streaming_events
from orchestrator_helpers.nodes import (
    initialize_node,
    think_node,
    execute_tool_node,
    execute_plan_node,
    generate_response_node,
    await_approval_node,
    process_approval_node,
    await_question_node,
    process_answer_node,
    await_tool_confirmation_node,
    process_tool_confirmation_node,
)

checkpointer = MemorySaver()
set_checkpointer(checkpointer)

logger = logging.getLogger(__name__)

# Base URL for session manager (kali-sandbox HTTP server on port 8013)
_SESSION_MANAGER_BASE = os.environ.get(
    "MCP_METASPLOIT_PROGRESS_URL", "http://kali-sandbox:8013/progress"
).rsplit("/progress", 1)[0]


class AgentOrchestrator:
    """
    ReAct-style agent orchestrator for penetration testing.

    Implements the Thought-Tool-Output pattern with:
    - Phase tracking (Informational → Exploitation → Post-Exploitation)
    - LLM-managed todo lists
    - Checkpoint-based approval for phase transitions
    - Full execution trace in memory
    """

    def __init__(self):
        """Initialize the orchestrator with configuration."""
        # Infrastructure-only env vars (stay in docker-compose)
        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD")

        self.model_name: Optional[str] = None
        self.llm: Optional[BaseChatModel] = None
        self.tool_executor: Optional[PhaseAwareToolExecutor] = None
        self.neo4j_manager: Optional[Neo4jToolManager] = None
        self.graph = None

        self._initialized = False
        # Per-session maps — keyed by session_id so concurrent sessions
        # don't overwrite each other's callback / guidance queue.
        self._streaming_callbacks: dict[str, object] = {}
        self._guidance_queues: dict[str, asyncio.Queue] = {}
        self._graph_view_cyphers: dict[str, str | None] = {}

        # Metasploit prewarm: background restart tasks keyed by session_key
        self._prewarm_tasks: dict[str, asyncio.Task] = {}

    async def initialize(self) -> None:
        """Initialize tools and graph (LLM setup deferred until project_id is known)."""
        if self._initialized:
            logger.warning("Orchestrator already initialized")
            return

        logger.info("Initializing AgentOrchestrator...")

        await self._setup_tools()
        self._build_graph()
        self._initialized = True

        logger.info("AgentOrchestrator initialized (LLM deferred until project settings loaded)")

    # =========================================================================
    # METASPLOIT PREWARM
    # =========================================================================

    def start_msf_prewarm(self, session_key: str) -> None:
        """
        Start a background Metasploit restart so msfconsole is ready
        by the time the agent needs it.

        Called on WebSocket init (drawer open). Fire-and-forget.
        If a prewarm is already running for this session, skip.
        """
        if not self._initialized or not self.tool_executor:
            logger.debug("Orchestrator not initialized yet, skipping prewarm")
            return

        # Skip if already running for this session
        existing = self._prewarm_tasks.get(session_key)
        if existing and not existing.done():
            logger.debug(f"Prewarm already running for {session_key}, skipping")
            return

        logger.info(f"[{session_key}] Starting Metasploit prewarm (background)")
        task = asyncio.create_task(self._do_msf_prewarm(session_key))
        self._prewarm_tasks[session_key] = task

    async def _do_msf_prewarm(self, session_key: str) -> None:
        """Background task: restart msfconsole for a clean state."""
        try:
            result = await self.tool_executor.execute(
                "msf_restart", {}, "exploitation", skip_phase_check=True
            )
            if result and result.get("success"):
                logger.info(f"[{session_key}] Metasploit prewarm complete")
            else:
                logger.warning(f"[{session_key}] Metasploit prewarm failed: {result}")
        except asyncio.CancelledError:
            logger.info(f"[{session_key}] Metasploit prewarm cancelled")
        except Exception as e:
            logger.warning(f"[{session_key}] Metasploit prewarm error: {e}")
        finally:
            # Clean up the task reference
            self._prewarm_tasks.pop(session_key, None)

    # =========================================================================
    # LLM & PROJECT SETTINGS
    # =========================================================================

    def _apply_project_settings(self, project_id: str) -> None:
        """Load project settings and reconfigure LLM if model changed."""
        apply_project_settings(self, project_id)

        # Update tool API keys and rotation from user settings
        user_settings = getattr(self, '_user_settings', {})
        rotation_configs = user_settings.get('rotationConfigs', {})

        def _build_rotator(main_key: str, tool_name: str) -> KeyRotator:
            cfg = rotation_configs.get(tool_name, {})
            extra = cfg.get('extraKeys', [])
            rotate_n = cfg.get('rotateEveryN', 10)
            return KeyRotator([main_key] + extra, rotate_n)

        # Tavily (web_search)
        tavily_key = user_settings.get('tavilyApiKey', '')
        if tavily_key and self._web_search_manager and self._web_search_manager.api_key != tavily_key:
            self._web_search_manager.api_key = tavily_key
            new_tool = self._web_search_manager.get_tool()
            if new_tool and self.tool_executor:
                self.tool_executor.update_web_search_tool(new_tool)
                logger.info("Updated Tavily web search tool with user settings key")
        if tavily_key and self._web_search_manager:
            self._web_search_manager.key_rotator = _build_rotator(tavily_key, 'tavily')

        # Shodan
        shodan_key = user_settings.get('shodanApiKey', '')
        if self._shodan_manager and self.tool_executor:
            shodan_enabled = get_setting('SHODAN_ENABLED', True)
            if shodan_key and shodan_enabled and self._shodan_manager.api_key != shodan_key:
                self._shodan_manager.api_key = shodan_key
                shodan_tool = self._shodan_manager.get_tool()
                self.tool_executor.update_shodan_tool(shodan_tool)
                logger.info("Updated Shodan OSINT tool with user settings key")
            elif not shodan_enabled:
                self.tool_executor.update_shodan_tool(None)
                logger.info("Shodan tool disabled via project settings")
        if shodan_key and self._shodan_manager:
            self._shodan_manager.key_rotator = _build_rotator(shodan_key, 'shodan')

        # Google dork (SerpAPI)
        serp_api_key = user_settings.get('serpApiKey', '')
        if self._google_dork_manager and self.tool_executor:
            if serp_api_key and self._google_dork_manager.api_key != serp_api_key:
                self._google_dork_manager.api_key = serp_api_key
                google_dork_tool = self._google_dork_manager.get_tool()
                self.tool_executor.update_google_dork_tool(google_dork_tool)
                logger.info("Updated Google dork tool with SerpAPI key")
        if serp_api_key and self._google_dork_manager:
            self._google_dork_manager.key_rotator = _build_rotator(serp_api_key, 'serp')

        # OSINT tools — Censys, FOFA, OTX, Netlas, VirusTotal, ZoomEye, CriminalIP
        if hasattr(self, '_osint_managers') and self.tool_executor:
            _osint_key_map = {
                'censys': {'token_field': 'censysApiToken', 'org_id_field': 'censysOrgId'},
                'fofa': {'key_field': 'fofaApiKey', 'rotation_name': 'fofa'},
                'otx': {'key_field': 'otxApiKey', 'rotation_name': 'otx'},
                'netlas': {'key_field': 'netlasApiKey', 'rotation_name': 'netlas'},
                'virustotal': {'key_field': 'virusTotalApiKey', 'rotation_name': 'virustotal'},
                'zoomeye': {'key_field': 'zoomEyeApiKey', 'rotation_name': 'zoomeye'},
                'criminalip': {'key_field': 'criminalIpApiKey', 'rotation_name': 'criminalip'},
            }
            for tool_name, key_cfg in _osint_key_map.items():
                mgr = self._osint_managers.get(tool_name)
                if not mgr:
                    continue
                enabled = get_setting(f'{tool_name.upper()}_ENABLED', True)
                if not enabled:
                    self.tool_executor.update_osint_tool(tool_name, None)
                    continue
                if tool_name == 'censys':
                    api_token = user_settings.get('censysApiToken', '')
                    org_id = user_settings.get('censysOrgId', '')
                    creds_changed = (
                        mgr.api_token != api_token
                        or mgr.org_id != org_id
                    )
                    has_creds = bool(api_token) and bool(org_id)
                    if has_creds and creds_changed:
                        mgr.api_token = api_token
                        mgr.org_id = org_id
                        self.tool_executor.update_osint_tool(tool_name, mgr.get_tool())
                        logger.info(f"Updated {tool_name} tool with API credentials")
                else:
                    key_val = user_settings.get(key_cfg['key_field'], '')
                    if key_val and mgr.api_key != key_val:
                        mgr.api_key = key_val
                        self.tool_executor.update_osint_tool(tool_name, mgr.get_tool())
                        logger.info(f"Updated {tool_name} tool with API key")
                    if key_val and hasattr(mgr, 'key_rotator'):
                        mgr.key_rotator = _build_rotator(key_val, key_cfg.get('rotation_name', tool_name))

        # Claude Code — routes through the host proxy (claude_proxy/server.py).
        # No API key or in-container login needed; the proxy uses the host's
        # existing Claude Code session.
        if hasattr(self, '_claude_code_manager') and self.tool_executor:
            claude_code_enabled = get_setting('CLAUDE_CODE_ENABLED', False)

            if claude_code_enabled:
                claude_code_tool = self._claude_code_manager.get_tool()
                self.tool_executor.update_claude_code_tool(claude_code_tool)
                if claude_code_tool:
                    logger.info(f"Claude Code tool enabled (proxy: {self._claude_code_manager.proxy_url})")
            else:
                self.tool_executor.update_claude_code_tool(None)
                logger.debug("Claude Code tool disabled via project settings")

    def _setup_llm(self) -> None:
        """Initialize the LLM based on current model_name.

        Resolves keys from the cached project settings (if loaded)
        or from whatever user providers are available.
        """
        from project_settings import get_settings
        from orchestrator_helpers.llm_setup import _resolve_provider_key

        settings = get_settings()
        user_providers = settings.get('USER_LLM_PROVIDERS', [])
        custom_config = settings.get('CUSTOM_LLM_CONFIG')

        openai_p = _resolve_provider_key(user_providers, "openai")
        anthropic_p = _resolve_provider_key(user_providers, "anthropic")
        openrouter_p = _resolve_provider_key(user_providers, "openrouter")
        bedrock_p = _resolve_provider_key(user_providers, "bedrock")

        self.llm = setup_llm(
            self.model_name,
            openai_api_key=(openai_p or {}).get("apiKey"),
            anthropic_api_key=(anthropic_p or {}).get("apiKey"),
            openrouter_api_key=(openrouter_p or {}).get("apiKey"),
            aws_access_key_id=(bedrock_p or {}).get("awsAccessKeyId"),
            aws_secret_access_key=(bedrock_p or {}).get("awsSecretKey"),
            aws_region=(bedrock_p or {}).get("awsRegion") or "us-east-1",
            custom_llm_config=custom_config,
        )

    # =========================================================================
    # TOOLS & GRAPH SETUP
    # =========================================================================

    async def _setup_tools(self) -> None:
        """Set up all tools (MCP and Neo4j)."""
        # Setup MCP tools
        mcp_manager = MCPToolsManager()
        mcp_tools = await mcp_manager.get_tools()

        # Setup Neo4j graph query tool (LLM is None until project settings are loaded)
        self.neo4j_manager = Neo4jToolManager(
            uri=self.neo4j_uri,
            user=self.neo4j_user,
            password=self.neo4j_password,
            llm=self.llm
        )
        graph_tool = self.neo4j_manager.get_tool()

        # Setup Tavily web search tool (key resolved later via update_tavily_key)
        self._web_search_manager = WebSearchToolManager()
        web_search_tool = self._web_search_manager.get_tool()

        # Setup Shodan OSINT tool (key resolved later via _apply_project_settings)
        self._shodan_manager = ShodanToolManager()
        shodan_tool = self._shodan_manager.get_tool()

        # Setup Google dork tool (key resolved later via _apply_project_settings)
        self._google_dork_manager = GoogleDorkToolManager()
        google_dork_tool = self._google_dork_manager.get_tool()

        # Setup additional OSINT tool managers (keys resolved via _apply_project_settings)
        self._osint_managers = {
            'censys': CensysToolManager(),
            'fofa': FofaToolManager(),
            'otx': OtxToolManager(),
            'netlas': NetlasToolManager(),
            'virustotal': VirusTotalToolManager(),
            'zoomeye': ZoomEyeToolManager(),
            'criminalip': CriminalIpToolManager(),
        }
        osint_tools = {
            name: mgr.get_tool()
            for name, mgr in self._osint_managers.items()
        }

        # Setup Claude Code tool (enabled/disabled per project settings later)
        self._claude_code_manager = ClaudeCodeToolManager()
        claude_code_tool = self._claude_code_manager.get_tool()

        # Create phase-aware tool executor
        self.tool_executor = PhaseAwareToolExecutor(
            mcp_manager, graph_tool, web_search_tool,
            shodan_tool, google_dork_tool,
            osint_tools=osint_tools,
            claude_code_tool=claude_code_tool,
        )
        self.tool_executor.register_mcp_tools(mcp_tools)

        logger.info(f"Tools initialized: {len(self.tool_executor.get_all_tools())} available")

    def _build_graph(self) -> None:
        """Build the ReAct LangGraph with phase tracking."""
        logger.info("Building ReAct LangGraph...")

        neo4j_creds = (self.neo4j_uri, self.neo4j_user, self.neo4j_password)
        builder = StateGraph(AgentState)

        # Add nodes — async wrappers that pass instance state to extracted functions
        async def _initialize(state, config=None):
            return await initialize_node(state, config, llm=self.llm, neo4j_creds=neo4j_creds)

        async def _think(state, config=None):
            return await think_node(state, config, llm=self.llm, guidance_queues=self._guidance_queues, neo4j_creds=neo4j_creds, streaming_callbacks=self._streaming_callbacks, graph_view_cyphers=self._graph_view_cyphers)

        async def _execute_tool(state, config=None):
            return await execute_tool_node(state, config, tool_executor=self.tool_executor, streaming_callbacks=self._streaming_callbacks, session_manager_base=_SESSION_MANAGER_BASE, graph_view_cyphers=self._graph_view_cyphers)

        async def _execute_plan(state, config=None):
            return await execute_plan_node(state, config, tool_executor=self.tool_executor, streaming_callbacks=self._streaming_callbacks, session_manager_base=_SESSION_MANAGER_BASE, graph_view_cyphers=self._graph_view_cyphers)

        async def _await_approval(state, config=None):
            return await await_approval_node(state, config)

        async def _process_approval(state, config=None):
            return await process_approval_node(state, config, neo4j_creds=neo4j_creds)

        async def _await_question(state, config=None):
            return await await_question_node(state, config)

        async def _process_answer(state, config=None):
            return await process_answer_node(state, config)

        async def _generate_response(state, config=None):
            return await generate_response_node(state, config, llm=self.llm, streaming_callbacks=self._streaming_callbacks, neo4j_creds=neo4j_creds)

        async def _await_tool_confirmation(state, config=None):
            return await await_tool_confirmation_node(state, config)

        async def _process_tool_confirmation(state, config=None):
            return await process_tool_confirmation_node(state, config)

        builder.add_node("initialize", _initialize)
        builder.add_node("think", _think)
        builder.add_node("execute_tool", _execute_tool)
        builder.add_node("execute_plan", _execute_plan)
        builder.add_node("await_approval", _await_approval)
        builder.add_node("process_approval", _process_approval)
        builder.add_node("await_question", _await_question)
        builder.add_node("process_answer", _process_answer)
        builder.add_node("generate_response", _generate_response)
        builder.add_node("await_tool_confirmation", _await_tool_confirmation)
        builder.add_node("process_tool_confirmation", _process_tool_confirmation)

        # Entry point
        builder.add_edge(START, "initialize")

        # Route after initialize - process approval, process answer, process tool confirmation, or think
        builder.add_conditional_edges(
            "initialize",
            self._route_after_initialize,
            {
                "process_approval": "process_approval",
                "process_answer": "process_answer",
                "process_tool_confirmation": "process_tool_confirmation",
                "think": "think",
                "generate_response": "generate_response",
            }
        )

        # Main routing from think node
        builder.add_conditional_edges(
            "think",
            self._route_after_think,
            {
                "execute_tool": "execute_tool",
                "execute_plan": "execute_plan",
                "await_approval": "await_approval",
                "await_question": "await_question",
                "await_tool_confirmation": "await_tool_confirmation",
                "generate_response": "generate_response",
                "think": "think",
            }
        )

        # Tool execution flow — goes directly back to think (analysis merged into think node)
        builder.add_edge("execute_tool", "think")
        builder.add_edge("execute_plan", "think")

        # Approval flow - pause for user input
        builder.add_edge("await_approval", END)

        # Process approval routes back to think or ends
        builder.add_conditional_edges(
            "process_approval",
            self._route_after_approval,
            {
                "think": "think",
                "generate_response": "generate_response",
            }
        )

        # Q&A flow - pause for user input
        builder.add_edge("await_question", END)

        # Process answer routes back to think or ends
        builder.add_conditional_edges(
            "process_answer",
            self._route_after_answer,
            {
                "think": "think",
                "generate_response": "generate_response",
            }
        )

        # Tool confirmation flow - pause for user input
        builder.add_edge("await_tool_confirmation", END)

        # Process tool confirmation routes to execute, think, or ends
        builder.add_conditional_edges(
            "process_tool_confirmation",
            self._route_after_tool_confirmation,
            {
                "execute_tool": "execute_tool",
                "execute_plan": "execute_plan",
                "think": "think",
                "generate_response": "generate_response",
            }
        )

        # Final response always ends
        builder.add_edge("generate_response", END)

        self.graph = builder.compile(checkpointer=checkpointer)
        logger.info("ReAct LangGraph compiled with checkpointer")

    # =========================================================================
    # ROUTING FUNCTIONS
    # =========================================================================

    def _route_after_initialize(self, state: AgentState) -> str:
        """Route after initialization - process approval, process answer, tool confirmation, guardrail block, or think."""
        if state.get("tool_confirmation_response") and state.get("tool_confirmation_pending"):
            logger.info("Routing to process_tool_confirmation - tool confirmation response pending")
            return "process_tool_confirmation"

        if state.get("user_approval_response") and state.get("phase_transition_pending"):
            logger.info("Routing to process_approval - approval response pending")
            return "process_approval"

        if state.get("user_question_answer") and state.get("pending_question"):
            logger.info("Routing to process_answer - question answer pending")
            return "process_answer"

        # If guardrail blocked the target, skip straight to response
        if state.get("_guardrail_blocked"):
            logger.warning("Routing to generate_response - target blocked by guardrail")
            return "generate_response"

        return "think"

    def _route_after_think(self, state: AgentState) -> str:
        """Route based on think node decision."""
        if state.get("current_iteration", 0) >= state.get("max_iterations", get_setting('MAX_ITERATIONS', 100)):
            logger.info("Max iterations reached, generating response")
            return "generate_response"

        if state.get("task_complete"):
            return "generate_response"

        if state.get("awaiting_tool_confirmation"):
            return "await_tool_confirmation"

        if state.get("awaiting_user_approval"):
            return "await_approval"

        if state.get("awaiting_user_question"):
            return "await_question"

        decision = state.get("_decision", {})
        action = decision.get("action", "use_tool")
        tool_name = decision.get("tool_name")

        if action == "complete":
            return "generate_response"
        elif action == "ask_user":
            if state.get("pending_question"):
                return "await_question"
            else:
                logger.warning("ask_user action but no pending_question, continuing to think")
                return "generate_response"
        elif action == "transition_phase":
            if state.get("phase_transition_pending"):
                return "await_approval"
            if state.get("_just_transitioned_to"):
                logger.info(f"Phase auto-approved to {state.get('_just_transitioned_to')}, continuing to think")
                return "think"
            if tool_name:
                logger.info(f"Transition ignored, executing tool: {tool_name}")
                return "execute_tool"
            else:
                logger.info("Transition ignored and no tool, generating response")
                return "generate_response"
        elif action == "plan_tools":
            if decision.get("tool_plan"):
                return "execute_plan"
            else:
                logger.warning(f"action=plan_tools but no tool_plan in decision, falling back to generate_response")
                return "generate_response"
        elif action == "use_tool" and tool_name:
            return "execute_tool"
        else:
            logger.warning(f"No valid action in decision: {action}, tool: {tool_name}")
            return "generate_response"

    def _route_after_approval(self, state: AgentState) -> str:
        """Route after processing approval."""
        if state.get("task_complete"):
            return "generate_response"
        if state.get("_abort_transition"):
            return "generate_response"
        return "think"

    def _route_after_answer(self, state: AgentState) -> str:
        """Route after processing user's answer to a question."""
        if state.get("task_complete"):
            return "generate_response"
        return "think"

    def _route_after_tool_confirmation(self, state: AgentState) -> str:
        """Route after processing tool confirmation response."""
        if state.get("task_complete"):
            return "generate_response"
        if state.get("_reject_tool"):
            return "think"
        if state.get("_tool_confirmation_mode") == "plan":
            return "execute_plan"
        return "execute_tool"

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def invoke(
        self,
        question: str,
        user_id: str,
        project_id: str,
        session_id: str
    ) -> InvokeResponse:
        """Main entry point for agent invocation."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")

        self._apply_project_settings(project_id)

        # Fail fast: if no LLM could be configured, return an error immediately
        if self.llm is None:
            msg = "LLM not configured. Please add an API key in Global Settings."
            logger.error(f"[{user_id}/{project_id}/{session_id}] {msg}")
            return InvokeResponse(error=msg)

        logger.info(f"[{user_id}/{project_id}/{session_id}] Invoking with: {question[:10000]}")

        try:
            config = create_config(user_id, project_id, session_id)
            input_data = {
                "messages": [HumanMessage(content=question)]
            }

            final_state = await self.graph.ainvoke(input_data, config)

            return self._build_response(final_state)

        except Exception as e:
            logger.error(f"[{user_id}/{project_id}/{session_id}] Error: {e}")
            return InvokeResponse(error=str(e))

    async def resume_after_approval(
        self,
        session_id: str,
        user_id: str,
        project_id: str,
        decision: str,
        modification: Optional[str] = None
    ) -> InvokeResponse:
        """Resume execution after user provides approval response."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")

        self._apply_project_settings(project_id)

        if self.llm is None:
            msg = "LLM not configured. Please add an API key in Global Settings."
            logger.error(f"[{user_id}/{project_id}/{session_id}] {msg}")
            return InvokeResponse(error=msg)

        logger.info(f"[{user_id}/{project_id}/{session_id}] Resuming with approval: {decision}")

        try:
            config = create_config(user_id, project_id, session_id)

            current_state = await self.graph.aget_state(config)

            if not current_state or not current_state.values:
                return InvokeResponse(error="No pending session found")

            update_data = {
                "user_approval_response": decision,
                "user_modification": modification,
            }

            final_state = await self.graph.ainvoke(
                update_data,
                config,
            )

            return self._build_response(final_state)

        except Exception as e:
            logger.error(f"[{user_id}/{project_id}/{session_id}] Resume error: {e}")
            return InvokeResponse(error=str(e))

    async def resume_after_answer(
        self,
        session_id: str,
        user_id: str,
        project_id: str,
        answer: str
    ) -> InvokeResponse:
        """Resume execution after user provides answer to a question."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")

        self._apply_project_settings(project_id)

        if self.llm is None:
            msg = "LLM not configured. Please add an API key in Global Settings."
            logger.error(f"[{user_id}/{project_id}/{session_id}] {msg}")
            return InvokeResponse(error=msg)

        logger.info(f"[{user_id}/{project_id}/{session_id}] Resuming with answer: {answer[:10000]}")

        try:
            config = create_config(user_id, project_id, session_id)

            current_state = await self.graph.aget_state(config)

            if not current_state or not current_state.values:
                return InvokeResponse(error="No pending session found")

            update_data = {
                "user_question_answer": answer,
            }

            final_state = await self.graph.ainvoke(
                update_data,
                config,
            )

            return self._build_response(final_state)

        except Exception as e:
            logger.error(f"[{user_id}/{project_id}/{session_id}] Resume error: {e}")
            return InvokeResponse(error=str(e))

    def _build_response(self, state: dict) -> InvokeResponse:
        """Build InvokeResponse from final state."""
        final_answer = ""
        tool_used = None
        tool_output = None

        messages = state.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                final_answer = msg.content
                break

        step = state.get("_current_step", {})
        if step:
            tool_used = step.get("tool_name")
            tool_output = step.get("tool_output")

        # Check plan state if no single tool was found
        plan = state.get("_current_plan")
        if plan and not tool_used:
            for s in reversed(plan.get("steps", [])):
                if s.get("tool_name"):
                    tool_used = s["tool_name"]
                    tool_output = s.get("tool_output")
                    break

        return InvokeResponse(
            answer=final_answer,
            tool_used=tool_used,
            tool_output=tool_output,
            current_phase=state.get("current_phase", "informational"),
            iteration_count=state.get("current_iteration", 0),
            task_complete=state.get("task_complete", False),
            todo_list=state.get("todo_list", []),
            execution_trace_summary=summarize_trace_for_response(
                state.get("execution_trace", [])
            ),
            awaiting_approval=state.get("awaiting_user_approval", False),
            approval_request=state.get("phase_transition_pending"),
            awaiting_question=state.get("awaiting_user_question", False),
            question_request=state.get("pending_question"),
            awaiting_tool_confirmation=state.get("awaiting_tool_confirmation", False),
            tool_confirmation_request=state.get("tool_confirmation_pending"),
        )

    # =========================================================================
    # STREAMING PUBLIC API
    # =========================================================================

    async def invoke_with_streaming(
        self,
        question: str,
        user_id: str,
        project_id: str,
        session_id: str,
        streaming_callback,
        guidance_queue=None,
        graph_view_cypher=None,
    ) -> InvokeResponse:
        """
        Invoke agent with streaming callbacks for real-time updates.

        The streaming_callback should have methods:
        - on_thinking(iteration, phase, thought, reasoning)
        - on_tool_start(tool_name, tool_args)
        - on_tool_output_chunk(tool_name, chunk, is_final)
        - on_tool_complete(tool_name, success, output_summary)
        - on_phase_update(current_phase, iteration_count)
        - on_todo_update(todo_list)
        - on_approval_request(approval_request)
        - on_question_request(question_request)
        - on_response(answer, iteration_count, phase, task_complete)
        - on_execution_step(step)
        - on_error(error_message, recoverable)
        - on_task_complete(message, final_phase, total_iterations)
        """
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")

        self._apply_project_settings(project_id)

        # Fail fast: if no LLM could be configured, return an error immediately
        # instead of letting the guardrail's fail-closed mask it as "Target Blocked".
        if self.llm is None:
            msg = "LLM not configured. Please add an API key in Global Settings."
            logger.error(f"[{user_id}/{project_id}/{session_id}] {msg}")
            await streaming_callback.on_error(msg, recoverable=False)
            return InvokeResponse(error=msg)

        logger.info(f"[{user_id}/{project_id}/{session_id}] Invoking with streaming: {question[:10000]}")

        # Store streaming callback, guidance queue, and graph view scope per-session
        self._streaming_callbacks[session_id] = streaming_callback
        self._guidance_queues[session_id] = guidance_queue
        self._graph_view_cyphers[session_id] = graph_view_cypher

        try:
            config = create_config(user_id, project_id, session_id)
            input_data = {
                "messages": [HumanMessage(content=question)]
            }

            # Stream graph execution
            final_state = None
            async for event in self.graph.astream(input_data, config, stream_mode="values"):
                final_state = event
                await emit_streaming_events(event, streaming_callback)

            if final_state:
                response = self._build_response(final_state)
                # Don't send response when graph paused for user interaction
                is_paused = (
                    final_state.get("awaiting_tool_confirmation")
                    or final_state.get("awaiting_user_approval")
                    or final_state.get("awaiting_user_question")
                )
                if not is_paused:
                    await streaming_callback.on_response(
                        response.answer,
                        response.iteration_count,
                        response.current_phase,
                        response.task_complete,
                        response_tier=final_state.get("_response_tier", "full_report"),
                    )
                return response
            else:
                raise RuntimeError("No final state returned from graph execution")

        except Exception as e:
            logger.error(f"[{user_id}/{project_id}/{session_id}] Streaming error: {e}")
            await streaming_callback.on_error(str(e), recoverable=False)
            return InvokeResponse(error=str(e))
        finally:
            self._streaming_callbacks.pop(session_id, None)
            self._guidance_queues.pop(session_id, None)
            self._graph_view_cyphers.pop(session_id, None)

    async def resume_after_approval_with_streaming(
        self,
        session_id: str,
        user_id: str,
        project_id: str,
        decision: str,
        modification: Optional[str],
        streaming_callback,
        guidance_queue=None
    ) -> InvokeResponse:
        """Resume after approval with streaming callbacks."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")

        self._apply_project_settings(project_id)

        if self.llm is None:
            msg = "LLM not configured. Please add an API key in Global Settings."
            logger.error(f"[{user_id}/{project_id}/{session_id}] {msg}")
            await streaming_callback.on_error(msg, recoverable=False)
            return InvokeResponse(error=msg)

        logger.info(f"[{user_id}/{project_id}/{session_id}] Resuming with streaming approval: {decision}")

        self._streaming_callbacks[session_id] = streaming_callback
        self._guidance_queues[session_id] = guidance_queue

        try:
            config = create_config(user_id, project_id, session_id)

            current_state = await self.graph.aget_state(config)
            if not current_state or not current_state.values:
                await streaming_callback.on_error("No pending session found", recoverable=False)
                return InvokeResponse(error="No pending session found")

            update_data = {
                "user_approval_response": decision,
                "user_modification": modification,
                # Clear stale fields to prevent duplicate emissions from
                # fresh StreamingCallback (same pattern as tool confirmation).
                "_decision": None,
                "_completed_step": None,
            }

            final_state = None
            async for event in self.graph.astream(update_data, config, stream_mode="values"):
                final_state = event
                await emit_streaming_events(event, streaming_callback)

            if final_state:
                response = self._build_response(final_state)
                is_paused = (
                    final_state.get("awaiting_tool_confirmation")
                    or final_state.get("awaiting_user_approval")
                    or final_state.get("awaiting_user_question")
                )
                if not is_paused:
                    await streaming_callback.on_response(
                        response.answer,
                        response.iteration_count,
                        response.current_phase,
                        response.task_complete,
                        response_tier=final_state.get("_response_tier", "full_report"),
                    )
                return response
            else:
                raise RuntimeError("No final state returned")

        except Exception as e:
            logger.error(f"[{user_id}/{project_id}/{session_id}] Resume streaming error: {e}")
            await streaming_callback.on_error(str(e), recoverable=False)
            return InvokeResponse(error=str(e))
        finally:
            self._streaming_callbacks.pop(session_id, None)
            self._guidance_queues.pop(session_id, None)
            self._graph_view_cyphers.pop(session_id, None)

    async def resume_after_answer_with_streaming(
        self,
        session_id: str,
        user_id: str,
        project_id: str,
        answer: str,
        streaming_callback,
        guidance_queue=None
    ) -> InvokeResponse:
        """Resume after answer with streaming callbacks."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")

        self._apply_project_settings(project_id)

        if self.llm is None:
            msg = "LLM not configured. Please add an API key in Global Settings."
            logger.error(f"[{user_id}/{project_id}/{session_id}] {msg}")
            await streaming_callback.on_error(msg, recoverable=False)
            return InvokeResponse(error=msg)

        logger.info(f"[{user_id}/{project_id}/{session_id}] Resuming with streaming answer: {answer[:10000]}")

        self._streaming_callbacks[session_id] = streaming_callback
        self._guidance_queues[session_id] = guidance_queue

        try:
            config = create_config(user_id, project_id, session_id)

            current_state = await self.graph.aget_state(config)
            if not current_state or not current_state.values:
                await streaming_callback.on_error("No pending session found", recoverable=False)
                return InvokeResponse(error="No pending session found")

            update_data = {
                "user_question_answer": answer,
                # Clear stale fields to prevent duplicate emissions from
                # fresh StreamingCallback (same pattern as tool confirmation).
                "_decision": None,
                "_completed_step": None,
            }

            final_state = None
            async for event in self.graph.astream(update_data, config, stream_mode="values"):
                final_state = event
                await emit_streaming_events(event, streaming_callback)

            if final_state:
                response = self._build_response(final_state)
                is_paused = (
                    final_state.get("awaiting_tool_confirmation")
                    or final_state.get("awaiting_user_approval")
                    or final_state.get("awaiting_user_question")
                )
                if not is_paused:
                    await streaming_callback.on_response(
                        response.answer,
                        response.iteration_count,
                        response.current_phase,
                        response.task_complete,
                        response_tier=final_state.get("_response_tier", "full_report"),
                    )
                return response
            else:
                raise RuntimeError("No final state returned")

        except Exception as e:
            logger.error(f"[{user_id}/{project_id}/{session_id}] Resume streaming error: {e}")
            await streaming_callback.on_error(str(e), recoverable=False)
            return InvokeResponse(error=str(e))
        finally:
            self._streaming_callbacks.pop(session_id, None)
            self._guidance_queues.pop(session_id, None)
            self._graph_view_cyphers.pop(session_id, None)

    async def resume_after_tool_confirmation(
        self,
        session_id: str,
        user_id: str,
        project_id: str,
        decision: str,
        modifications: Optional[dict] = None
    ) -> InvokeResponse:
        """Resume execution after user provides tool confirmation response."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")

        self._apply_project_settings(project_id)

        if self.llm is None:
            msg = "LLM not configured. Please add an API key in Global Settings."
            logger.error(f"[{user_id}/{project_id}/{session_id}] {msg}")
            return InvokeResponse(error=msg)

        logger.info(f"[{user_id}/{project_id}/{session_id}] Resuming with tool confirmation: {decision}")

        try:
            config = create_config(user_id, project_id, session_id)

            current_state = await self.graph.aget_state(config)

            if not current_state or not current_state.values:
                return InvokeResponse(error="No pending session found")

            update_data = {
                "tool_confirmation_response": decision,
                "tool_confirmation_modification": modifications,
            }

            final_state = await self.graph.ainvoke(
                update_data,
                config,
            )

            return self._build_response(final_state)

        except Exception as e:
            logger.error(f"[{user_id}/{project_id}/{session_id}] Resume error: {e}")
            return InvokeResponse(error=str(e))

    async def resume_after_tool_confirmation_with_streaming(
        self,
        session_id: str,
        user_id: str,
        project_id: str,
        decision: str,
        modifications: Optional[dict],
        streaming_callback,
        guidance_queue=None
    ) -> InvokeResponse:
        """Resume after tool confirmation with streaming callbacks."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")

        self._apply_project_settings(project_id)

        if self.llm is None:
            msg = "LLM not configured. Please add an API key in Global Settings."
            logger.error(f"[{user_id}/{project_id}/{session_id}] {msg}")
            await streaming_callback.on_error(msg, recoverable=False)
            return InvokeResponse(error=msg)

        logger.info(f"[{user_id}/{project_id}/{session_id}] Resuming with streaming tool confirmation: {decision}")

        self._streaming_callbacks[session_id] = streaming_callback
        self._guidance_queues[session_id] = guidance_queue

        try:
            config = create_config(user_id, project_id, session_id)

            current_state = await self.graph.aget_state(config)
            if not current_state or not current_state.values:
                await streaming_callback.on_error("No pending session found", recoverable=False)
                return InvokeResponse(error="No pending session found")

            update_data = {
                "tool_confirmation_response": decision,
                "tool_confirmation_modification": modifications,
                # Clear stale fields BEFORE astream starts — the first state
                # yield is the checkpoint state (before process_tool_confirmation
                # runs), and a new StreamingCallback has empty dedup sets, so
                # stale _decision / _completed_step would be re-emitted as
                # duplicate THINKING / TOOL_COMPLETE events.
                "_decision": None,
                "_completed_step": None,
            }

            final_state = None
            async for event in self.graph.astream(update_data, config, stream_mode="values"):
                final_state = event
                await emit_streaming_events(event, streaming_callback)

            if final_state:
                response = self._build_response(final_state)
                is_paused = (
                    final_state.get("awaiting_tool_confirmation")
                    or final_state.get("awaiting_user_approval")
                    or final_state.get("awaiting_user_question")
                )
                if not is_paused:
                    await streaming_callback.on_response(
                        response.answer,
                        response.iteration_count,
                        response.current_phase,
                        response.task_complete,
                        response_tier=final_state.get("_response_tier", "full_report"),
                    )
                return response
            else:
                raise RuntimeError("No final state returned")

        except Exception as e:
            logger.error(f"[{user_id}/{project_id}/{session_id}] Resume streaming error: {e}")
            await streaming_callback.on_error(str(e), recoverable=False)
            return InvokeResponse(error=str(e))
        finally:
            self._streaming_callbacks.pop(session_id, None)
            self._guidance_queues.pop(session_id, None)
            self._graph_view_cyphers.pop(session_id, None)

    async def resume_execution_with_streaming(
        self,
        user_id: str,
        project_id: str,
        session_id: str,
        streaming_callback,
        guidance_queue=None
    ) -> InvokeResponse:
        """Resume execution from last checkpoint (after stop)."""
        if not self._initialized:
            raise RuntimeError("Orchestrator not initialized. Call initialize() first.")

        self._apply_project_settings(project_id)

        if self.llm is None:
            msg = "LLM not configured. Please add an API key in Global Settings."
            logger.error(f"[{user_id}/{project_id}/{session_id}] {msg}")
            await streaming_callback.on_error(msg, recoverable=False)
            return InvokeResponse(error=msg)

        logger.info(f"[{user_id}/{project_id}/{session_id}] Resuming execution from checkpoint")

        self._streaming_callbacks[session_id] = streaming_callback
        self._guidance_queues[session_id] = guidance_queue

        try:
            config = create_config(user_id, project_id, session_id)

            current_state = await self.graph.aget_state(config)
            if not current_state or not current_state.values:
                await streaming_callback.on_error("No session state to resume", recoverable=False)
                return InvokeResponse(error="No session state to resume")

            # Re-invoke graph from last checkpoint with empty input
            final_state = None
            async for event in self.graph.astream({}, config, stream_mode="values"):
                final_state = event
                await emit_streaming_events(event, streaming_callback)

            if final_state:
                response = self._build_response(final_state)
                is_paused = (
                    final_state.get("awaiting_tool_confirmation")
                    or final_state.get("awaiting_user_approval")
                    or final_state.get("awaiting_user_question")
                )
                if not is_paused:
                    await streaming_callback.on_response(
                        response.answer,
                        response.iteration_count,
                        response.current_phase,
                        response.task_complete,
                        response_tier=final_state.get("_response_tier", "full_report"),
                    )
                return response
            else:
                raise RuntimeError("No final state returned")

        except Exception as e:
            logger.error(f"[{user_id}/{project_id}/{session_id}] Resume execution error: {e}")
            await streaming_callback.on_error(str(e), recoverable=False)
            return InvokeResponse(error=str(e))
        finally:
            self._streaming_callbacks.pop(session_id, None)
            self._guidance_queues.pop(session_id, None)
            self._graph_view_cyphers.pop(session_id, None)

    async def close(self) -> None:
        """Clean up resources."""
        self._initialized = False
        logger.info("AgentOrchestrator closed")
