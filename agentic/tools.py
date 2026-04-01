"""
RedAmon Agent Tools

MCP tools and Neo4j graph query tool definitions.
Includes phase-aware tool management.
"""

import os
import re
import asyncio
import logging
from typing import List, Optional, Dict, Callable, Awaitable, TYPE_CHECKING
from contextvars import ContextVar

import httpx
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_neo4j import Neo4jGraph

from project_settings import get_setting, is_tool_allowed_in_phase
from prompts import TEXT_TO_CYPHER_SYSTEM

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

# =============================================================================
# CONTEXT VARIABLES
# =============================================================================

# Context variables to pass user_id and project_id to tools
current_user_id: ContextVar[str] = ContextVar('current_user_id', default='')
current_project_id: ContextVar[str] = ContextVar('current_project_id', default='')
current_phase: ContextVar[str] = ContextVar('current_phase', default='informational')
current_graph_view_cypher: ContextVar[Optional[str]] = ContextVar('current_graph_view_cypher', default=None)


def set_tenant_context(user_id: str, project_id: str) -> None:
    """Set the current user and project context for tool execution."""
    current_user_id.set(user_id)
    current_project_id.set(project_id)


def set_phase_context(phase: str) -> None:
    """Set the current phase context for tool restrictions."""
    current_phase.set(phase)


def set_graph_view_context(cypher: Optional[str]) -> None:
    """Set the active graph view Cypher for scoped queries."""
    current_graph_view_cypher.set(cypher)


def get_graph_view_context() -> Optional[str]:
    """Get the active graph view Cypher template."""
    return current_graph_view_cypher.get()


def get_phase_context() -> str:
    """Get the current phase context."""
    return current_phase.get()


# =============================================================================
# MCP TOOLS MANAGER
# =============================================================================

class MCPToolsManager:
    """Manages MCP (Model Context Protocol) tool connections."""

    def __init__(
        self,
        network_recon_url: str = None,
        nmap_url: str = None,
        metasploit_url: str = None,
        nuclei_url: str = None,
        playwright_url: str = None,
    ):
        self.network_recon_url = network_recon_url or os.environ.get('MCP_NETWORK_RECON_URL', 'http://host.docker.internal:8000/sse')
        self.nmap_url = nmap_url or os.environ.get('MCP_NMAP_URL', 'http://host.docker.internal:8004/sse')
        self.metasploit_url = metasploit_url or os.environ.get('MCP_METASPLOIT_URL', 'http://host.docker.internal:8003/sse')
        self.nuclei_url = nuclei_url or os.environ.get('MCP_NUCLEI_URL', 'http://host.docker.internal:8002/sse')
        self.playwright_url = playwright_url or os.environ.get('MCP_PLAYWRIGHT_URL', 'http://host.docker.internal:8005/sse')
        self.client: Optional[MultiServerMCPClient] = None
        self._tools_cache: Dict[str, any] = {}

    async def get_tools(self, max_retries: int = 5, retry_delay: float = 10.0) -> List:
        """
        Connect to MCP servers and load tools with retry logic.

        MCP servers (kali-sandbox) may still be starting up when the agent
        initializes. Retries with exponential backoff to handle this race condition.

        Returns:
            List of MCP tools available for use
        """
        logger.info("Connecting to MCP servers...")

        mcp_servers = {}

        # Timeout settings (in seconds):
        # - timeout: HTTP connection timeout (default 5s)
        # - sse_read_timeout: How long to wait for SSE events (default 300s = 5 min)
        # Metasploit needs longer timeouts for brute force attacks (30 min for large wordlists)
        server_configs = [
            ("network_recon", self.network_recon_url, 60, 1800),  # curl+naabu+hydra+command, 30 min read (hydra needs up to 30 min)
            ("nmap", self.nmap_url, 60, 600),                     # 10 min read
            ("metasploit", self.metasploit_url, 60, 1800),        # 30 min read
            ("nuclei", self.nuclei_url, 60, 600),                 # 10 min read
            ("playwright", self.playwright_url, 60, 120),            # 2 min read
        ]

        for server_name, url, timeout, sse_read_timeout in server_configs:
            try:
                logger.info(f"Connecting to MCP {server_name} server at {url}")
                mcp_servers[server_name] = {
                    "url": url,
                    "transport": "sse",
                    "timeout": timeout,
                    "sse_read_timeout": sse_read_timeout,
                }
            except Exception as e:
                logger.warning(f"Failed to configure MCP server {server_name}: {e}")

        if not mcp_servers:
            logger.warning("No MCP servers configured")
            return []

        # Retry connection with backoff — MCP servers may still be starting
        for attempt in range(1, max_retries + 1):
            try:
                self.client = MultiServerMCPClient(mcp_servers)
                mcp_tools = await self.client.get_tools()

                all_tools = []
                # Cache tools by name for easy access
                for tool in mcp_tools:
                    tool_name = getattr(tool, 'name', str(tool))
                    self._tools_cache[tool_name] = tool
                    all_tools.append(tool)

                logger.info(f"Loaded {len(all_tools)} tools from MCP servers: {list(self._tools_cache.keys())}")
                return all_tools

            except Exception as e:
                if attempt < max_retries:
                    wait = retry_delay * attempt
                    logger.warning(
                        f"MCP connection attempt {attempt}/{max_retries} failed: {e}. "
                        f"Retrying in {wait:.0f}s..."
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Failed to connect to MCP servers after {max_retries} attempts: {e}")
                    logger.warning("Continuing without MCP tools")
                    return []

    def get_tool_by_name(self, name: str) -> Optional[any]:
        """Get a specific tool by name."""
        return self._tools_cache.get(name)

    def get_available_tools_for_phase(self, phase: str) -> List:
        """Get tools that are allowed in the current phase."""
        return [
            tool for name, tool in self._tools_cache.items()
            if is_tool_allowed_in_phase(name, phase)
        ]


# =============================================================================
# NEO4J TOOL MANAGER
# =============================================================================

class Neo4jToolManager:
    """Manages Neo4j graph query tool with tenant filtering."""

    def __init__(self, uri: str, user: str, password: str, llm: "BaseChatModel"):
        self.uri = uri
        self.user = user
        self.password = password
        self.llm = llm
        self.graph: Optional[Neo4jGraph] = None

    def _inject_tenant_filter(self, cypher: str, user_id: str, project_id: str) -> str:
        """
        Inject mandatory user_id and project_id filters into a Cypher query.

        This ensures all queries are scoped to the current user's project,
        preventing cross-tenant data access.

        Strategy: Add tenant properties directly into each node pattern as inline
        property filters. This ensures filters are always in scope regardless of
        WITH clauses or query structure.

        Example:
            MATCH (d:Domain {name: "example.com"})
        becomes:
            MATCH (d:Domain {name: "example.com", user_id: $tenant_user_id, project_id: $tenant_project_id})

        Args:
            cypher: The AI-generated Cypher query
            user_id: Current user's ID
            project_id: Current project's ID

        Returns:
            Modified Cypher query with tenant filters applied
        """
        tenant_props = "user_id: $tenant_user_id, project_id: $tenant_project_id"

        def add_tenant_to_node(match: re.Match) -> str:
            """Add tenant properties to a node pattern."""
            var_name = match.group(1)
            label = match.group(2)
            existing_props_content = match.group(3)  # Content INSIDE braces (without braces), or None

            if existing_props_content is not None:
                # Has existing properties - merge with tenant props
                existing_props_content = existing_props_content.strip()
                if existing_props_content:
                    # Append tenant props after existing ones
                    new_props = f"{{{existing_props_content}, {tenant_props}}}"
                else:
                    new_props = f"{{{tenant_props}}}"
                return f"({var_name}:{label} {new_props})"
            else:
                # No existing properties, add them
                return f"({var_name}:{label} {{{tenant_props}}})"

        # Pattern matches: (variable:Label) or (variable:Label {props})
        # Captures: 1=variable, 2=label, 3=optional content INSIDE braces (without braces)
        # Uses a non-greedy match for the props content
        node_pattern = r'\((\w+):(\w+)(?:\s*\{([^}]*)\})?\)'

        result = re.sub(node_pattern, add_tenant_to_node, cypher)

        return result

    async def _generate_cypher(
        self,
        question: str,
        previous_error: str = None,
        previous_cypher: str = None,
        view_cypher: str = None,
        for_graph_view: bool = False,
    ) -> str:
        """
        Use LLM to generate a Cypher query from natural language.

        Args:
            question: Natural language question about the data
            previous_error: Optional error message from a previous failed attempt
            previous_cypher: Optional previous Cypher query that failed

        Returns:
            Generated Cypher query string
        """
        if self.llm is None:
            raise RuntimeError(
                "Graph query LLM is not initialized. "
                "This usually means project settings have not been loaded yet. "
                "Please try again or check that the agent model is configured."
            )

        schema = self.graph.get_schema

        # Build the prompt with optional error context for retries
        error_context = ""
        if previous_error and previous_cypher:
            error_context = f"""

## Previous Attempt Failed
The previous query failed with an error. Please fix the issue.

Failed Query:
{previous_cypher}

Error Message:
{previous_error}

Common fixes:
- Check relationship direction syntax: use <-[:REL]- not [:REL]<-
- Ensure node labels and property names match the schema
- Verify relationship types exist in the schema
"""

        view_scope = ""
        if view_cypher:
            view_scope = f"""
## Active Graph View Scope
The user is working within a filtered subgraph defined by this Cypher query:
{view_cypher}
Your query MUST only return results that exist within this subgraph.
Incorporate the filter pattern into your MATCH clauses so results are scoped appropriately.
"""

        graph_view_rules = ""
        if for_graph_view:
            graph_view_rules = """
- CRITICAL: This query is for a GRAPH VISUALIZATION. You MUST return full node and relationship objects, NOT individual properties.
  Good: MATCH (s:Subdomain)-[r:RESOLVES_TO]->(i:IP) RETURN s, r, i LIMIT 300
  Bad:  MATCH (s:Subdomain)-[r:RESOLVES_TO]->(i:IP) RETURN s.name, i.address LIMIT 300
- Always include relationships in your MATCH pattern and RETURN clause so the graph displays connections between nodes.
- For aggregation/filtering queries (e.g., "subdomains with at least 4 IPs"), use WITH for filtering, then re-MATCH to return full objects:
  Example: MATCH (s:Subdomain)-[:RESOLVES_TO]->(i:IP) WITH s, count(i) AS cnt WHERE cnt >= 4 MATCH (s)-[r:RESOLVES_TO]->(i:IP) RETURN s, r, i LIMIT 300
- Never use RETURN with property accessors (e.g. n.name). Always RETURN the node/relationship variable itself."""

        prompt = f"""{TEXT_TO_CYPHER_SYSTEM}

## Current Database Schema
{schema}
{error_context}{view_scope}
## Important Rules
- Generate ONLY the Cypher query, no explanations
- Do NOT include user_id or project_id filters - they will be added automatically
- Do NOT use any parameters (like $target, $domain, etc.) - use literal values or no filters
- If the question doesn't specify a target, query ALL matching data
- Always use LIMIT to restrict results{graph_view_rules}

User Question: {question}

Cypher Query:"""

        response = await self.llm.ainvoke(prompt)
        from orchestrator_helpers.json_utils import normalize_content
        cypher = normalize_content(response.content).strip()

        # Clean up the response - remove markdown code blocks if present
        if cypher.startswith("```"):
            lines = cypher.split("\n")
            cypher = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        return cypher.strip()

    def get_tool(self) -> Optional[callable]:
        """
        Set up and return the Neo4j text-to-cypher tool.

        Returns:
            The query_graph tool function, or None if setup fails
        """
        logger.info(f"Setting up Neo4j connection to {self.uri}")

        try:
            self.graph = Neo4jGraph(
                url=self.uri,
                username=self.user,
                password=self.password
            )

            # Store reference to self for use in the tool closure
            manager = self

            @tool
            async def query_graph(question: str) -> str:
                """
                Query the Neo4j graph database using natural language.

                Use this tool to retrieve reconnaissance data such as:
                - Domains, subdomains, and their relationships
                - IP addresses and their associated ports/services
                - Technologies detected on targets
                - Vulnerabilities and CVEs found
                - Any other security reconnaissance data

                This is the PRIMARY source of truth for target information.
                Always query the graph FIRST before using other tools.

                Args:
                    question: Natural language question about the data

                Returns:
                    Query results as a string
                """
                # Get current user/project from context
                user_id = current_user_id.get()
                project_id = current_project_id.get()

                if not user_id or not project_id:
                    return "Error: Missing user_id or project_id context"

                # Check if a graph view scope is active
                view_cypher = get_graph_view_context()
                if view_cypher:
                    logger.info(f"[{user_id}/{project_id}] Using graph view scope for query")

                logger.info(f"[{user_id}/{project_id}] Generating Cypher for: {question[:50]}...")

                last_error = None
                last_cypher = None

                for attempt in range(get_setting('CYPHER_MAX_RETRIES', 3)):
                    try:
                        # Step 1: Generate Cypher from natural language (with error context on retry)
                        if attempt == 0:
                            cypher = await manager._generate_cypher(question, view_cypher=view_cypher)
                        else:
                            logger.info(f"[{user_id}/{project_id}] Retry {attempt}/{get_setting('CYPHER_MAX_RETRIES', 3) - 1}: Regenerating Cypher...")
                            cypher = await manager._generate_cypher(
                                question,
                                previous_error=last_error,
                                previous_cypher=last_cypher,
                                view_cypher=view_cypher,
                            )

                        logger.info(f"[{user_id}/{project_id}] Generated Cypher (attempt {attempt + 1}): {cypher}")

                        # Reject write operations -- query_graph is read-only
                        _upper = cypher.upper()
                        _WRITE_KW = ['CREATE', 'MERGE', 'DELETE', 'DETACH', 'SET ', 'REMOVE', 'DROP', 'CALL']
                        _found = next((kw for kw in _WRITE_KW if kw in _upper), None)
                        if _found:
                            return f"Error: Write operations are not allowed in graph queries (found: {_found.strip()})"

                        # Step 2: Inject mandatory tenant filters
                        filtered_cypher = manager._inject_tenant_filter(cypher, user_id, project_id)
                        logger.info(f"[{user_id}/{project_id}] Filtered Cypher: {filtered_cypher}")

                        # Step 3: Execute the filtered query
                        result = manager.graph.query(
                            filtered_cypher,
                            params={
                                "tenant_user_id": user_id,
                                "tenant_project_id": project_id
                            }
                        )

                        if not result:
                            return "No results found"

                        return str(result)

                    except Exception as e:
                        error_msg = str(e)
                        logger.warning(f"[{user_id}/{project_id}] Query attempt {attempt + 1} failed: {error_msg}")
                        last_error = error_msg
                        last_cypher = cypher if 'cypher' in locals() else None

                        # If this is the last attempt, return the error
                        if attempt == get_setting('CYPHER_MAX_RETRIES', 3) - 1:
                            logger.error(f"[{user_id}/{project_id}] All {get_setting('CYPHER_MAX_RETRIES', 3)} attempts failed")
                            return f"Error querying graph after {get_setting('CYPHER_MAX_RETRIES', 3)} attempts: {error_msg}"

                return "Error: Unexpected end of retry loop"

            logger.info("Neo4j graph query tool configured with tenant filtering")
            return query_graph

        except Exception as e:
            logger.error(f"Failed to set up Neo4j: {e}")
            logger.warning("Continuing without graph query tool")
            return None


# =============================================================================
# WEB SEARCH TOOL MANAGER
# =============================================================================

class WebSearchToolManager:
    """Manages Tavily web search tool for CVE research and exploit lookups."""

    def __init__(self, api_key: str = None, max_results: int = 5):
        self.api_key = api_key or ''
        self.max_results = max_results
        self.key_rotator = None  # Optional[KeyRotator]

    def get_tool(self) -> Optional[callable]:
        """
        Set up and return the Tavily web search tool.

        Returns:
            The web_search tool function, or None if Tavily API key is not configured.
        """
        if not self.api_key:
            logger.warning(
                "Tavily API key not configured - web_search tool will not be available. "
                "Set it in Global Settings (http://localhost:3000/settings)."
            )
            return None

        manager = self

        @tool
        async def web_search(query: str) -> str:
            """
            Search the web for security research information.

            Use this tool to research:
            - CVE details, severity, affected versions, and patch information
            - Exploit techniques, PoC code, and attack vectors
            - Service/technology version-specific vulnerabilities
            - Security advisories and vendor bulletins
            - Metasploit module documentation and usage

            This is a SECONDARY source - always check query_graph FIRST
            for project-specific reconnaissance data.

            Args:
                query: Search query string (e.g., "CVE-2021-41773 exploit PoC")

            Returns:
                Search results with titles, URLs, and content snippets
            """
            try:
                from langchain_tavily import TavilySearch

                api_key = manager.key_rotator.current_key if manager.key_rotator and manager.key_rotator.has_keys else manager.api_key
                tavily_tool = TavilySearch(
                    max_results=manager.max_results,
                    topic="general",
                    search_depth="advanced",
                    tavily_api_key=api_key,
                )

                results = await tavily_tool.ainvoke({"query": query})
                if manager.key_rotator:
                    manager.key_rotator.tick()

                if isinstance(results, str):
                    return results

                if isinstance(results, list):
                    formatted = []
                    for i, result in enumerate(results, 1):
                        title = result.get("title", "No title")
                        url = result.get("url", "")
                        content = result.get("content", "")
                        formatted.append(
                            f"[{i}] {title}\n    URL: {url}\n    {content}"
                        )
                    return "\n\n".join(formatted) if formatted else "No results found"

                return str(results)

            except ImportError:
                return "Error: langchain-tavily package not installed. Run: pip install langchain-tavily"
            except Exception as e:
                logger.error(f"Web search failed: {e}")
                return f"Web search error: {str(e)}"

        logger.info("Tavily web search tool configured")
        return web_search


# =============================================================================
# GOOGLE DORK TOOL MANAGER (via SerpAPI)
# =============================================================================

SERPAPI_BASE = "https://serpapi.com/search"


class GoogleDorkToolManager:
    """Manages Google dork search tool via SerpAPI for OSINT reconnaissance."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or ''
        self.key_rotator = None  # Optional[KeyRotator]

    def get_tool(self) -> Optional[callable]:
        """
        Set up and return the Google dork search tool.

        Returns:
            The google_dork tool function, or None if SerpAPI key is not configured.
        """
        if not self.api_key:
            logger.warning(
                "SerpAPI key not configured - google_dork tool will not be available. "
                "Set it in Global Settings (http://localhost:3000/settings)."
            )
            return None

        manager = self

        @tool
        async def google_dork(query: str) -> str:
            """
            Search Google using advanced dork operators for OSINT reconnaissance.

            Use this tool to find:
            - Exposed files on target domains (filetype:sql, filetype:env, filetype:bak)
            - Admin panels and login pages (inurl:admin, inurl:login)
            - Directory listings (intitle:"index of")
            - Sensitive data leaks (intext:password, intext:"sql syntax")

            This is passive OSINT — no packets are sent to the target.

            Args:
                query: Google dork query (e.g., "site:example.com filetype:pdf")

            Returns:
                Search results with titles, URLs, and snippets
            """
            try:
                api_key = manager.key_rotator.current_key if manager.key_rotator and manager.key_rotator.has_keys else manager.api_key
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(
                        SERPAPI_BASE,
                        params={
                            "engine": "google",
                            "api_key": api_key,
                            "q": query,
                            "num": 10,
                            "nfpr": 1,      # Disable auto-correct to preserve dork syntax
                            "filter": 0,    # Disable similar results filter
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if manager.key_rotator:
                        manager.key_rotator.tick()

                # Check for API-level errors
                if "error" in data:
                    return f"Google dork error: {data['error']}"

                items = data.get("organic_results", [])
                if not items:
                    return f"No results found for: {query}"

                # Get total results count
                search_info = data.get("search_information", {})
                total = search_info.get("total_results", "?")

                formatted = []
                for item in items:
                    pos = item.get("position", "?")
                    title = item.get("title", "No title")
                    link = item.get("link", "")
                    snippet = item.get("snippet", "")
                    displayed_link = item.get("displayed_link", "")

                    entry = f"[{pos}] {title}\n    URL: {link}"
                    if displayed_link:
                        entry += f"\n    Display: {displayed_link}"
                    if snippet:
                        entry += f"\n    {snippet}"
                    formatted.append(entry)

                header = f"Google dork results ({total} total, showing {len(items)}):\n"
                return header + "\n\n".join(formatted)

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 401:
                    return "SerpAPI error: Invalid API key. Check Global Settings."
                elif status == 429:
                    return "SerpAPI error: Rate limit exceeded (free: 250/month, 50/hour)."
                return f"SerpAPI error: HTTP {status}"
            except Exception as e:
                logger.error(f"Google dork search failed: {e}")
                return f"Google dork error: {str(e)}"

        logger.info("Google dork search tool configured (via SerpAPI)")
        return google_dork


# =============================================================================
# SHODAN TOOL MANAGER
# =============================================================================

SHODAN_API_BASE = "https://api.shodan.io"


class ShodanToolManager:
    """Manages unified Shodan OSINT tool for internet-wide reconnaissance."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or ''
        self.key_rotator = None  # Optional[KeyRotator]

    def get_tool(self) -> Optional[callable]:
        """
        Set up and return unified Shodan tool with 5 actions.

        Returns:
            The shodan tool, or None if Shodan API key is not configured.
        """
        if not self.api_key:
            logger.warning(
                "Shodan API key not configured - shodan tool will not be available. "
                "Set it in Global Settings (http://localhost:3000/settings)."
            )
            return None

        manager = self

        @tool
        async def shodan(action: str, query: str = "", ip: str = "", domain: str = "") -> str:
            """
            Unified Shodan OSINT tool for internet-wide reconnaissance.

            Actions:
            - search: Search Shodan for devices/services (requires paid key)
            - host: Get detailed info for a specific IP
            - dns_reverse: Reverse DNS lookup for an IP
            - dns_domain: Get DNS records and subdomains for a domain (requires paid key)
            - count: Count matching hosts without full search

            Args:
                action: One of "search", "host", "dns_reverse", "dns_domain", "count"
                query: Shodan search query (for search and count actions)
                ip: Target IP address (for host and dns_reverse actions)
                domain: Target domain (for dns_domain action)

            Returns:
                Formatted results from the Shodan API
            """
            api_key = manager.key_rotator.current_key if manager.key_rotator and manager.key_rotator.has_keys else manager.api_key
            if action == "search":
                result = await _action_search(api_key, query)
            elif action == "host":
                result = await _action_host(api_key, ip)
            elif action == "dns_reverse":
                result = await _action_dns_reverse(api_key, ip)
            elif action == "dns_domain":
                result = await _action_dns_domain(api_key, domain)
            elif action == "count":
                result = await _action_count(api_key, query)
            else:
                return (
                    f"Error: Unknown action '{action}'. "
                    "Valid actions: search, host, dns_reverse, dns_domain, count"
                )
            if manager.key_rotator:
                manager.key_rotator.tick()
            return result

        logger.info("Shodan OSINT tool configured (5 actions)")
        return shodan


async def _action_search(api_key: str, query: str) -> str:
    """Search Shodan for internet-connected devices."""
    if not query:
        return "Error: 'query' parameter is required for action='search'"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SHODAN_API_BASE}/shodan/host/search",
                params={"key": api_key, "query": query},
            )
            resp.raise_for_status()
            data = resp.json()

        total = data.get("total", 0)
        matches = data.get("matches", [])

        if not matches:
            return f"No Shodan results for query: {query} (total: {total})"

        lines = [f"Shodan search: {total} total results (showing {len(matches)})"]
        lines.append("")

        for i, match in enumerate(matches[:20], 1):
            ip = match.get("ip_str", "?")
            port = match.get("port", "?")
            org = match.get("org", "")
            product = match.get("product", "")
            version = match.get("version", "")
            hostnames = match.get("hostnames", [])
            vulns = list(match.get("vulns", {}).keys()) if match.get("vulns") else []
            transport = match.get("transport", "tcp")

            svc = f"{product} {version}".strip() if product else ""
            host_line = f"[{i}] {ip}:{port}/{transport}"
            if org:
                host_line += f"  org={org}"
            if hostnames:
                host_line += f"  hosts={','.join(hostnames[:3])}"
            if svc:
                host_line += f"  svc={svc}"
            if vulns:
                host_line += f"  vulns={','.join(vulns[:5])}"

            lines.append(host_line)

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return _handle_http_error(e, "search")
    except Exception as e:
        logger.error(f"Shodan search failed: {e}")
        return f"Shodan search error: {str(e)}"


async def _action_host(api_key: str, ip: str) -> str:
    """Get detailed Shodan information for a specific IP address."""
    if not ip:
        return "Error: 'ip' parameter is required for action='host'"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SHODAN_API_BASE}/shodan/host/{ip}",
                params={"key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        lines = [f"Shodan Host: {data.get('ip_str', ip)}"]

        hostnames = data.get("hostnames", [])
        if hostnames:
            lines.append(f"Hostnames: {', '.join(hostnames)}")

        os_info = data.get("os")
        if os_info:
            lines.append(f"OS: {os_info}")

        org = data.get("org", "")
        isp = data.get("isp", "")
        if org:
            lines.append(f"Org: {org}")
        if isp and isp != org:
            lines.append(f"ISP: {isp}")

        country = data.get("country_name", "")
        city = data.get("city", "")
        if country:
            loc = country
            if city:
                loc = f"{city}, {country}"
            lines.append(f"Location: {loc}")

        ports = data.get("ports", [])
        if ports:
            lines.append(f"Open ports: {', '.join(str(p) for p in sorted(ports))}")

        vulns = data.get("vulns", [])
        if vulns:
            lines.append(f"Vulnerabilities ({len(vulns)}): {', '.join(vulns[:15])}")
            if len(vulns) > 15:
                lines.append(f"  ... and {len(vulns) - 15} more")

        # Per-service details
        services = data.get("data", [])
        if services:
            lines.append("")
            lines.append(f"Services ({len(services)}):")
            for svc in services[:15]:
                port = svc.get("port", "?")
                transport = svc.get("transport", "tcp")
                product = svc.get("product", "")
                version = svc.get("version", "")
                svc_name = f"{product} {version}".strip() if product else ""

                svc_line = f"  {port}/{transport}"
                if svc_name:
                    svc_line += f"  {svc_name}"

                # Banner snippet (first 200 chars)
                banner = svc.get("data", "").strip()
                if banner:
                    snippet = banner[:200].replace("\n", " | ")
                    svc_line += f"  banner: {snippet}"

                lines.append(svc_line)

            if len(services) > 15:
                lines.append(f"  ... and {len(services) - 15} more services")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Shodan: No information available for IP {ip}"
        return _handle_http_error(e, "host")
    except Exception as e:
        logger.error(f"Shodan host info failed: {e}")
        return f"Shodan host info error: {str(e)}"


async def _action_dns_reverse(api_key: str, ip: str) -> str:
    """Reverse DNS lookup for an IP address."""
    if not ip:
        return "Error: 'ip' parameter is required for action='dns_reverse'"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SHODAN_API_BASE}/dns/reverse",
                params={"key": api_key, "ips": ip},
            )
            resp.raise_for_status()
            data = resp.json()

        hostnames = data.get(ip, [])
        if not hostnames:
            return f"No reverse DNS records for {ip}"

        lines = [f"Reverse DNS for {ip}:"]
        for hostname in hostnames:
            lines.append(f"  {hostname}")
        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return _handle_http_error(e, "dns_reverse")
    except Exception as e:
        logger.error(f"Shodan DNS reverse failed: {e}")
        return f"Shodan DNS reverse error: {str(e)}"


async def _action_dns_domain(api_key: str, domain: str) -> str:
    """Get DNS records and subdomains for a domain."""
    if not domain:
        return "Error: 'domain' parameter is required for action='dns_domain'"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SHODAN_API_BASE}/dns/domain/{domain}",
                params={"key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()

        lines = [f"DNS for {domain}:"]

        subdomains = data.get("subdomains", [])
        if subdomains:
            lines.append(f"Subdomains ({len(subdomains)}): {', '.join(subdomains[:30])}")
            if len(subdomains) > 30:
                lines.append(f"  ... and {len(subdomains) - 30} more")

        records = data.get("data", [])
        if records:
            lines.append("")
            lines.append(f"Records ({len(records)}):")
            for i, rec in enumerate(records[:30], 1):
                rec_type = rec.get("type", "?")
                subdomain = rec.get("subdomain", "")
                value = rec.get("value", "")
                fqdn = f"{subdomain}.{domain}" if subdomain else domain
                lines.append(f"  [{i}] {rec_type}  {fqdn} -> {value}")
            if len(records) > 30:
                lines.append(f"  ... and {len(records) - 30} more records")

        if not subdomains and not records:
            lines.append("No DNS data found")

        if data.get("more", False):
            lines.append("\nNote: Additional results available (API returned partial data)")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return _handle_http_error(e, "dns_domain")
    except Exception as e:
        logger.error(f"Shodan DNS domain failed: {e}")
        return f"Shodan DNS domain error: {str(e)}"


async def _action_count(api_key: str, query: str) -> str:
    """Count Shodan results for a query without consuming search credits."""
    if not query:
        return "Error: 'query' parameter is required for action='count'"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SHODAN_API_BASE}/shodan/host/count",
                params={
                    "key": api_key,
                    "query": query,
                    "facets": "port,country,org",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        total = data.get("total", 0)
        lines = [f"Shodan count: {total} hosts matching '{query}'"]

        facets = data.get("facets", {})
        for facet_name, facet_values in facets.items():
            if facet_values:
                lines.append(f"\n{facet_name}:")
                for fv in facet_values[:10]:
                    lines.append(f"  {fv.get('value', '?')}: {fv.get('count', 0)}")

        return "\n".join(lines)

    except httpx.HTTPStatusError as e:
        return _handle_http_error(e, "count")
    except Exception as e:
        logger.error(f"Shodan count failed: {e}")
        return f"Shodan count error: {str(e)}"


def _handle_http_error(e: 'httpx.HTTPStatusError', action: str) -> str:
    """Common HTTP error handler for all Shodan actions."""
    status = e.response.status_code
    if status == 401:
        return "Shodan API error: Invalid API key. Check Global Settings."
    elif status == 403:
        return f"Shodan API error: Action '{action}' requires a paid Shodan API key."
    elif status == 429:
        return "Shodan API error: Rate limit exceeded. Try again later."
    return f"Shodan API error: HTTP {status}"


# =============================================================================
# OSINT TOOL MANAGERS (Censys, FOFA, OTX, Netlas, VirusTotal, ZoomEye, CriminalIP)
# =============================================================================

def _osint_http_error(tool_name: str, e: 'httpx.HTTPStatusError') -> str:
    """Shared HTTP error handler for OSINT tool actions."""
    status = e.response.status_code
    if status == 401:
        return f"{tool_name} API error: Invalid API key. Check Global Settings."
    elif status == 429:
        return f"{tool_name} API error: Rate limit exceeded. Try again later."
    return f"{tool_name} API error: HTTP {status}"


class CensysToolManager:
    """Censys internet search — host/service discovery via certificate and banner data."""

    API_BASE = "https://search.censys.io/api/v2"

    def __init__(self, api_id: str = '', api_secret: str = '', api_token: str = ''):
        self.api_id = api_id
        self.api_secret = api_secret
        self.api_token = api_token

    def get_tool(self) -> Optional[callable]:
        has_token = bool(self.api_token)
        has_id_secret = bool(self.api_id and self.api_secret)
        if not has_token and not has_id_secret:
            logger.warning("Censys API credentials not configured - censys tool unavailable.")
            return None
        manager = self

        @tool
        async def censys(action: str, query: str = "", ip: str = "") -> str:
            """
            Censys internet search engine for host and service discovery.

            Actions:
            - search: Search hosts by query (e.g. "services.port=443 AND location.country=US")
            - host: Get detailed host info for a specific IP (open ports, services, TLS certs)

            Args:
                action: "search" or "host"
                query: Censys search query (for search action)
                ip: Target IP address (for host action)

            Returns:
                Formatted results from the Censys API
            """
            # Personal API Token (Bearer) takes precedence over ID + Secret (Basic auth)
            if manager.api_token:
                client_kwargs = {"timeout": 30.0, "headers": {"Authorization": f"Bearer {manager.api_token}"}}
            else:
                client_kwargs = {"timeout": 30.0, "auth": (manager.api_id, manager.api_secret)}
            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    if action == "search":
                        if not query:
                            return "Error: 'query' required for action='search'"
                        resp = await client.get(
                            f"{manager.API_BASE}/hosts/search",
                            params={"q": query, "per_page": 25},
                        )
                    elif action == "host":
                        if not ip:
                            return "Error: 'ip' required for action='host'"
                        resp = await client.get(f"{manager.API_BASE}/hosts/{ip}")
                    else:
                        return f"Error: Unknown action '{action}'. Valid: search, host"

                    resp.raise_for_status()
                    data = resp.json()

                if action == "search":
                    hits = data.get("result", {}).get("hits", [])
                    total = data.get("result", {}).get("total", 0)
                    if not hits:
                        return f"No Censys results for: {query}"
                    lines = [f"Censys search: {total} hosts (showing {len(hits)})"]
                    for i, h in enumerate(hits[:25], 1):
                        ip_addr = h.get("ip", "?")
                        services = h.get("services", [])
                        ports = sorted({s.get("port", 0) for s in services})
                        location = h.get("location", {})
                        country = location.get("country", "")
                        asn_name = h.get("autonomous_system", {}).get("name", "")
                        line = f"[{i}] {ip_addr}  ports={ports}"
                        if country:
                            line += f"  country={country}"
                        if asn_name:
                            line += f"  as={asn_name}"
                        lines.append(line)
                    return "\n".join(lines)

                # action == "host"
                result = data.get("result", {})
                ip_addr = result.get("ip", ip)
                lines = [f"Censys Host: {ip_addr}"]
                asn = result.get("autonomous_system", {})
                if asn.get("name"):
                    lines.append(f"AS: {asn.get('asn', '')} {asn['name']}")
                loc = result.get("location", {})
                if loc.get("country"):
                    city = loc.get("city", "")
                    lines.append(f"Location: {f'{city}, ' if city else ''}{loc['country']}")
                os_info = result.get("operating_system", {}).get("product")
                if os_info:
                    lines.append(f"OS: {os_info}")
                rdns = result.get("dns", {}).get("reverse_dns", {}).get("names", [])
                if rdns:
                    lines.append(f"Reverse DNS: {', '.join(rdns[:5])}")
                services = result.get("services", [])
                if services:
                    lines.append(f"\nServices ({len(services)}):")
                    for s in services[:20]:
                        port = s.get("port", "?")
                        proto = s.get("transport_protocol", "tcp")
                        name = s.get("service_name", "")
                        ext = s.get("extended_service_name", "")
                        sw = s.get("software", [])
                        sw_str = ", ".join(
                            f"{x.get('product', '')} {x.get('version', '')}".strip()
                            for x in sw[:2] if isinstance(x, dict)
                        ) if sw else ""
                        line = f"  {port}/{proto}"
                        disp_name = ext or name
                        if disp_name:
                            line += f"  {disp_name}"
                        if sw_str:
                            line += f"  ({sw_str})"
                        tls = s.get("tls", {})
                        if isinstance(tls, dict) and tls.get("certificates", {}).get("leaf_data", {}).get("subject_dn"):
                            cert = tls["certificates"]["leaf_data"]
                            cn = cert.get("subject", {}).get("common_name", [""])
                            cn_str = cn[0] if isinstance(cn, list) and cn else str(cn)
                            line += f"  [TLS: {cn_str}]"
                        lines.append(line)
                return "\n".join(lines)

            except httpx.HTTPStatusError as e:
                return _osint_http_error("Censys", e)
            except Exception as e:
                logger.error(f"Censys {action} failed: {e}")
                return f"Censys error: {str(e)}"

        logger.info("Censys OSINT tool configured (2 actions)")
        return censys


class FofaToolManager:
    """FOFA cyberspace search engine — asset discovery by banner, cert, domain."""

    API_BASE = "https://fofa.info/api/v1"

    def __init__(self, api_key: str = ''):
        self.api_key = api_key
        self.key_rotator = None

    def get_tool(self) -> Optional[callable]:
        if not self.api_key:
            logger.warning("FOFA API key not configured - fofa tool unavailable.")
            return None
        manager = self

        @tool
        async def fofa(query: str) -> str:
            """
            FOFA cyberspace search engine for asset discovery.

            Searches by banner content, certificate, domain, IP, header, protocol, etc.
            Query examples: 'domain="example.com"', 'ip="1.2.3.4"', 'header="Apache"',
                           'cert="example.com"', 'port="8443"', 'protocol="https"'

            Args:
                query: FOFA query string (will be base64-encoded automatically)

            Returns:
                Formatted host/service results
            """
            import base64
            api_key = manager.key_rotator.current_key if manager.key_rotator and manager.key_rotator.has_keys else manager.api_key
            encoded_q = base64.b64encode(query.encode()).decode()
            fields = "ip,port,host,title,server,protocol,country,city,as_organization"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(
                        f"{manager.API_BASE}/search/all",
                        params={"key": api_key, "qbase64": encoded_q,
                                "fields": fields, "size": 50},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                if manager.key_rotator:
                    manager.key_rotator.tick()
                if data.get("error"):
                    return f"FOFA error: {data.get('errmsg', 'Unknown error')}"
                results = data.get("results", [])
                total = data.get("size", 0)
                if not results:
                    return f"No FOFA results for: {query}"
                field_names = fields.split(",")
                lines = [f"FOFA search: {total} results (showing {len(results)})"]
                for i, row in enumerate(results[:50], 1):
                    parts = []
                    if isinstance(row, list):
                        for j, val in enumerate(row):
                            if val and j < len(field_names):
                                parts.append(f"{field_names[j]}={val}")
                    else:
                        parts.append(str(row))
                    lines.append(f"[{i}] {' | '.join(parts)}")
                return "\n".join(lines)
            except httpx.HTTPStatusError as e:
                return _osint_http_error("FOFA", e)
            except Exception as e:
                logger.error(f"FOFA search failed: {e}")
                return f"FOFA error: {str(e)}"

        logger.info("FOFA search tool configured")
        return fofa


class OtxToolManager:
    """AlienVault OTX — open threat exchange for IP/domain threat intelligence."""

    API_BASE = "https://otx.alienvault.com/api/v1"

    def __init__(self, api_key: str = ''):
        self.api_key = api_key
        self.key_rotator = None

    def get_tool(self) -> Optional[callable]:
        # Allow anonymous requests (OTX API v1 works without a key at reduced rate)
        manager = self

        @tool
        async def otx(action: str, ip: str = "", domain: str = "") -> str:
            """
            AlienVault OTX threat intelligence lookup.

            Actions:
            - ip_report: Threat intel for an IP (pulses, adversary, malware samples, passive DNS, reputation, geo)
            - domain_report: Threat intel for a domain (pulses, adversary, malware samples, WHOIS, historical IPs)

            Args:
                action: "ip_report" or "domain_report"
                ip: Target IP address (for ip_report)
                domain: Target domain (for domain_report)

            Returns:
                Threat intelligence summary from OTX
            """
            api_key = manager.key_rotator.current_key if manager.key_rotator and manager.key_rotator.has_keys else manager.api_key
            headers = {"X-OTX-API-KEY": api_key} if api_key else {}
            try:
                async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                    if action == "ip_report":
                        if not ip:
                            return "Error: 'ip' required for action='ip_report'"
                        gen = await client.get(f"{manager.API_BASE}/indicators/IPv4/{ip}/general")
                        gen.raise_for_status()
                        data = gen.json()
                        lines = [f"OTX IP Report: {ip}"]
                        pulses = data.get("pulse_info", {}).get("count", 0)
                        lines.append(f"Threat Pulses: {pulses}")
                        rep = data.get("reputation", None)
                        if rep is not None:
                            lines.append(f"Reputation: {rep}")
                        geo = data.get("geo", {}) or {}
                        if geo.get("country_name"):
                            city = geo.get("city", "")
                            loc_str = f"{city}, {geo['country_name']}" if city else geo["country_name"]
                            lines.append(f"Location: {loc_str}")
                        if geo.get("asn"):
                            lines.append(f"ASN: {geo['asn']}")
                        # Pulse details: adversaries, malware families, attack IDs
                        pulse_refs = data.get("pulse_info", {}).get("pulses", [])
                        if pulse_refs:
                            adversaries = sorted({p.get("adversary", "").strip() for p in pulse_refs if p.get("adversary", "").strip()})
                            if adversaries:
                                lines.append(f"Adversaries: {', '.join(adversaries[:5])}")
                            mf_set: set[str] = set()
                            for p in pulse_refs:
                                for mf in p.get("malware_families") or []:
                                    name = (mf.get("display_name") or mf.get("id") or "") if isinstance(mf, dict) else str(mf)
                                    if name:
                                        mf_set.add(name.strip())
                            if mf_set:
                                lines.append(f"Malware Families: {', '.join(sorted(mf_set)[:5])}")
                            tlp_vals = {(p.get("TLP") or p.get("tlp") or "").lower().strip() for p in pulse_refs if p.get("TLP") or p.get("tlp")}
                            if tlp_vals:
                                lines.append(f"TLP values seen: {', '.join(sorted(tlp_vals))}")
                            lines.append(f"\nTop Pulses ({min(len(pulse_refs), 5)}):")
                            for p in pulse_refs[:5]:
                                name = p.get("name", "")
                                adv = p.get("adversary", "")
                                tags = ", ".join(p.get("tags", [])[:4])
                                detail = f"  - {name}"
                                if adv:
                                    detail += f"  [adversary: {adv}]"
                                if tags:
                                    detail += f"  tags=[{tags}]"
                                lines.append(detail)
                        # Malware samples
                        try:
                            ml_resp = await client.get(f"{manager.API_BASE}/indicators/IPv4/{ip}/malware")
                            if ml_resp.status_code == 200:
                                ml_data = ml_resp.json().get("data") or []
                                if ml_data:
                                    lines.append(f"\nMalware Samples ({len(ml_data)} total, showing top 5):")
                                    for s in ml_data[:5]:
                                        h = s.get("hash") or s.get("sha256") or s.get("md5") or "?"
                                        ft = s.get("type") or s.get("file_class") or ""
                                        fn = s.get("file_name") or ""
                                        lines.append(f"  - {h[:20]}...  type={ft}  name={fn}")
                        except Exception:
                            pass

                    elif action == "domain_report":
                        if not domain:
                            return "Error: 'domain' required for action='domain_report'"
                        gen = await client.get(f"{manager.API_BASE}/indicators/domain/{domain}/general")
                        gen.raise_for_status()
                        data = gen.json()
                        lines = [f"OTX Domain Report: {domain}"]
                        pulses = data.get("pulse_info", {}).get("count", 0)
                        lines.append(f"Threat Pulses: {pulses}")
                        whois = data.get("whois", {}) or {}
                        if whois.get("registrant"):
                            lines.append(f"Registrant: {whois['registrant']}")
                        # Pulse details
                        pulse_refs = data.get("pulse_info", {}).get("pulses", [])
                        if pulse_refs:
                            adversaries = sorted({p.get("adversary", "").strip() for p in pulse_refs if p.get("adversary", "").strip()})
                            if adversaries:
                                lines.append(f"Adversaries: {', '.join(adversaries[:5])}")
                            mf_set_d: set[str] = set()
                            for p in pulse_refs:
                                for mf in p.get("malware_families") or []:
                                    name = (mf.get("display_name") or mf.get("id") or "") if isinstance(mf, dict) else str(mf)
                                    if name:
                                        mf_set_d.add(name.strip())
                            if mf_set_d:
                                lines.append(f"Malware Families: {', '.join(sorted(mf_set_d)[:5])}")
                            lines.append(f"\nTop Pulses ({min(len(pulse_refs), 5)}):")
                            for p in pulse_refs[:5]:
                                name = p.get("name", "")
                                adv = p.get("adversary", "")
                                tags = ", ".join(p.get("tags", [])[:4])
                                detail = f"  - {name}"
                                if adv:
                                    detail += f"  [adversary: {adv}]"
                                if tags:
                                    detail += f"  tags=[{tags}]"
                                lines.append(detail)
                        # Malware samples
                        try:
                            ml_resp = await client.get(f"{manager.API_BASE}/indicators/domain/{domain}/malware")
                            if ml_resp.status_code == 200:
                                ml_data = ml_resp.json().get("data") or []
                                if ml_data:
                                    lines.append(f"\nMalware Samples ({len(ml_data)} total, showing top 5):")
                                    for s in ml_data[:5]:
                                        h = s.get("hash") or s.get("sha256") or s.get("md5") or "?"
                                        ft = s.get("type") or s.get("file_class") or ""
                                        fn = s.get("file_name") or ""
                                        lines.append(f"  - {h[:20]}...  type={ft}  name={fn}")
                        except Exception:
                            pass
                        # Historical IPs (domain passive_dns)
                        try:
                            dpd_resp = await client.get(f"{manager.API_BASE}/indicators/domain/{domain}/passive_dns")
                            if dpd_resp.status_code == 200:
                                hist_records = dpd_resp.json().get("passive_dns") or []
                                if hist_records:
                                    lines.append(f"\nHistorical IPs ({len(hist_records)} records, showing top 5):")
                                    for r in hist_records[:5]:
                                        addr = r.get("address") or r.get("hostname") or "?"
                                        last = r.get("last") or ""
                                        lines.append(f"  - {addr}  last={last[:10] if last else '?'}")
                        except Exception:
                            pass
                    else:
                        return f"Error: Unknown action '{action}'. Valid: ip_report, domain_report"
                if manager.key_rotator:
                    manager.key_rotator.tick()
                return "\n".join(lines)
            except httpx.HTTPStatusError as e:
                return _osint_http_error("OTX", e)
            except Exception as e:
                logger.error(f"OTX {action} failed: {e}")
                return f"OTX error: {str(e)}"

        key_mode = "authenticated" if (self.api_key or (self.key_rotator and getattr(self.key_rotator, "has_keys", False))) else "anonymous"
        logger.info(f"OTX threat intelligence tool configured (2 actions, {key_mode})")
        return otx


class NetlasToolManager:
    """Netlas.io — internet-wide scan data with banner, certificate, and WHOIS info."""

    API_BASE = "https://app.netlas.io/api"

    def __init__(self, api_key: str = ''):
        self.api_key = api_key
        self.key_rotator = None

    def get_tool(self) -> Optional[callable]:
        if not self.api_key:
            logger.warning("Netlas API key not configured - netlas tool unavailable.")
            return None
        manager = self

        @tool
        async def netlas(action: str, query: str = "", ip: str = "") -> str:
            """
            Netlas.io internet intelligence search.

            Actions:
            - search: Search responses index (e.g. 'host:example.com', 'port:443 AND certificate.issuer:Let')
            - host: Get aggregated host info for an IP

            Args:
                action: "search" or "host"
                query: Netlas query string (for search)
                ip: Target IP address (for host)

            Returns:
                Service banners, certificates, and host details
            """
            api_key = manager.key_rotator.current_key if manager.key_rotator and manager.key_rotator.has_keys else manager.api_key
            headers = {"X-API-Key": api_key}
            try:
                async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                    if action == "search":
                        if not query:
                            return "Error: 'query' required for action='search'"
                        resp = await client.get(
                            f"{manager.API_BASE}/responses/",
                            params={"q": query, "start": 0, "indices": ""},
                        )
                    elif action == "host":
                        if not ip:
                            return "Error: 'ip' required for action='host'"
                        resp = await client.get(f"{manager.API_BASE}/host/{ip}/")
                    else:
                        return f"Error: Unknown action '{action}'. Valid: search, host"
                    resp.raise_for_status()
                    data = resp.json()
                if manager.key_rotator:
                    manager.key_rotator.tick()

                if action == "search":
                    items = data.get("items", [])
                    total = data.get("count", 0)
                    if not items:
                        return f"No Netlas results for: {query}"
                    lines = [f"Netlas search: {total} results (showing {len(items)})"]
                    for i, item in enumerate(items[:25], 1):
                        d = item.get("data", {})
                        host = d.get("host", d.get("ip", "?"))
                        port = d.get("port", "?")
                        proto = d.get("protocol", "")
                        title = d.get("http", {}).get("title", "") if isinstance(d.get("http"), dict) else ""
                        geo_country = d.get("geo", {}).get("country", "") if isinstance(d.get("geo"), dict) else ""
                        line = f"[{i}] {host}:{port}"
                        if proto:
                            line += f" ({proto})"
                        if title:
                            line += f"  title={title[:60]}"
                        if geo_country:
                            line += f"  country={geo_country}"
                        lines.append(line)
                    return "\n".join(lines)

                # action == "host"
                lines = [f"Netlas Host: {ip}"]
                if isinstance(data, dict):
                    for key in ("country", "isp", "whois"):
                        if data.get(key):
                            lines.append(f"{key}: {data[key]}")
                return "\n".join(lines)

            except httpx.HTTPStatusError as e:
                return _osint_http_error("Netlas", e)
            except Exception as e:
                logger.error(f"Netlas {action} failed: {e}")
                return f"Netlas error: {str(e)}"

        logger.info("Netlas search tool configured (2 actions)")
        return netlas


class VirusTotalToolManager:
    """VirusTotal — multi-engine malware/URL reputation for domains and IPs."""

    API_BASE = "https://www.virustotal.com/api/v3"

    def __init__(self, api_key: str = ''):
        self.api_key = api_key
        self.key_rotator = None

    def get_tool(self) -> Optional[callable]:
        if not self.api_key:
            logger.warning("VirusTotal API key not configured - virustotal tool unavailable.")
            return None
        manager = self

        @tool
        async def virustotal(action: str, ip: str = "", domain: str = "") -> str:
            """
            VirusTotal reputation lookup for IPs and domains.

            Free-tier limits: 4 lookups/min, 500/day.

            Actions:
            - ip_report: Reputation and detections for an IP
            - domain_report: Reputation, subdomains, and detections for a domain

            Args:
                action: "ip_report" or "domain_report"
                ip: Target IP address
                domain: Target domain

            Returns:
                Reputation scores and detection summary
            """
            api_key = manager.key_rotator.current_key if manager.key_rotator and manager.key_rotator.has_keys else manager.api_key
            headers = {"x-apikey": api_key}
            try:
                async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                    if action == "ip_report":
                        if not ip:
                            return "Error: 'ip' required for action='ip_report'"
                        resp = await client.get(f"{manager.API_BASE}/ip_addresses/{ip}")
                    elif action == "domain_report":
                        if not domain:
                            return "Error: 'domain' required for action='domain_report'"
                        resp = await client.get(f"{manager.API_BASE}/domains/{domain}")
                    else:
                        return f"Error: Unknown action '{action}'. Valid: ip_report, domain_report"
                    resp.raise_for_status()
                    data = resp.json()
                if manager.key_rotator:
                    manager.key_rotator.tick()

                attrs = data.get("data", {}).get("attributes", {})
                target = ip if action == "ip_report" else domain
                lines = [f"VirusTotal {'IP' if action == 'ip_report' else 'Domain'} Report: {target}"]

                rep = attrs.get("reputation", "N/A")
                lines.append(f"Reputation score: {rep}")

                stats = attrs.get("last_analysis_stats", {})
                if stats:
                    mal = stats.get("malicious", 0)
                    sus = stats.get("suspicious", 0)
                    clean = stats.get("harmless", 0)
                    undetected = stats.get("undetected", 0)
                    lines.append(f"Detections: malicious={mal}, suspicious={sus}, clean={clean}, undetected={undetected}")

                if action == "ip_report":
                    asn = attrs.get("asn", "")
                    as_owner = attrs.get("as_owner", "")
                    country = attrs.get("country", "")
                    if asn:
                        lines.append(f"ASN: {asn} ({as_owner})")
                    if country:
                        lines.append(f"Country: {country}")
                else:
                    cats = attrs.get("categories", {})
                    if cats:
                        lines.append(f"Categories: {', '.join(set(cats.values()))}")
                    pop = attrs.get("popularity_ranks", {})
                    if pop:
                        ranks = [f"{k}: #{v.get('rank', '?')}" for k, v in list(pop.items())[:5]]
                        lines.append(f"Popularity: {', '.join(ranks)}")
                    registrar = attrs.get("registrar", "")
                    if registrar:
                        lines.append(f"Registrar: {registrar}")

                return "\n".join(lines)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    return "VirusTotal error: Rate limit exceeded (free tier: 4 req/min, 500/day). Wait and retry."
                return _osint_http_error("VirusTotal", e)
            except Exception as e:
                logger.error(f"VirusTotal {action} failed: {e}")
                return f"VirusTotal error: {str(e)}"

        logger.info("VirusTotal reputation tool configured (2 actions)")
        return virustotal


class ZoomEyeToolManager:
    """ZoomEye — cyberspace search engine for host/service/device discovery."""

    API_BASE = "https://api.zoomeye.ai"

    def __init__(self, api_key: str = ''):
        self.api_key = api_key
        self.key_rotator = None

    def get_tool(self) -> Optional[callable]:
        if not self.api_key:
            logger.warning("ZoomEye API key not configured - zoomeye tool unavailable.")
            return None
        manager = self

        @tool
        async def zoomeye(query: str) -> str:
            """
            ZoomEye cyberspace search engine for host/device discovery.

            Query examples: 'ip:"1.2.3.4"', 'hostname:"example.com"', 'port:8080',
                           'app:"Apache"', 'os:"Linux"', 'country:"US"'

            Args:
                query: ZoomEye search query (dork)

            Returns:
                Host/service results with ports, banners, and geo info
            """
            api_key = manager.key_rotator.current_key if manager.key_rotator and manager.key_rotator.has_keys else manager.api_key
            headers = {"API-KEY": api_key}
            try:
                async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                    resp = await client.get(
                        f"{manager.API_BASE}/host/search",
                        params={"query": query, "page": 1},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                if manager.key_rotator:
                    manager.key_rotator.tick()

                total = data.get("total", 0)
                matches = data.get("matches", [])
                if not matches:
                    return f"No ZoomEye results for: {query}"
                lines = [f"ZoomEye search: {total} hosts (showing {len(matches)})"]
                for i, m in enumerate(matches[:25], 1):
                    ip_addr = m.get("ip", "?")
                    port_info = m.get("portinfo", {})
                    port = port_info.get("port", "?") if isinstance(port_info, dict) else "?"
                    app = port_info.get("app", "") if isinstance(port_info, dict) else ""
                    banner = (port_info.get("banner", "") if isinstance(port_info, dict) else "")[:100]
                    geo = m.get("geoinfo", {})
                    country = geo.get("country", {}).get("names", {}).get("en", "") if isinstance(geo.get("country"), dict) else ""
                    os_info = port_info.get("os", "") if isinstance(port_info, dict) else ""
                    line = f"[{i}] {ip_addr}:{port}"
                    if app:
                        line += f"  app={app}"
                    if os_info:
                        line += f"  os={os_info}"
                    if country:
                        line += f"  country={country}"
                    if banner:
                        line += f"  banner={banner.replace(chr(10), ' ')}"
                    lines.append(line)
                return "\n".join(lines)

            except httpx.HTTPStatusError as e:
                return _osint_http_error("ZoomEye", e)
            except Exception as e:
                logger.error(f"ZoomEye search failed: {e}")
                return f"ZoomEye error: {str(e)}"

        logger.info("ZoomEye search tool configured")
        return zoomeye


class CriminalIpToolManager:
    """Criminal IP — AI-powered cyber threat intelligence for IP/domain risk scoring."""

    API_BASE = "https://api.criminalip.io/v1"

    def __init__(self, api_key: str = ''):
        self.api_key = api_key
        self.key_rotator = None

    def get_tool(self) -> Optional[callable]:
        if not self.api_key:
            logger.warning("Criminal IP API key not configured - criminalip tool unavailable.")
            return None
        manager = self

        @tool
        async def criminalip(action: str, ip: str = "", domain: str = "") -> str:
            """
            Criminal IP threat intelligence lookup for IPs and domains.

            Actions:
            - ip_report: Risk score, open ports, issues (VPN/proxy/tor), vulnerabilities for an IP
            - domain_report: Risk assessment and technology detection for a domain

            Args:
                action: "ip_report" or "domain_report"
                ip: Target IP address
                domain: Target domain

            Returns:
                Risk scores, detected issues, and vulnerability summary
            """
            api_key = manager.key_rotator.current_key if manager.key_rotator and manager.key_rotator.has_keys else manager.api_key
            headers = {"x-api-key": api_key}
            try:
                async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                    if action == "ip_report":
                        if not ip:
                            return "Error: 'ip' required for action='ip_report'"
                        resp = await client.get(f"{manager.API_BASE}/ip/data", params={"ip": ip})
                    elif action == "domain_report":
                        if not domain:
                            return "Error: 'domain' required for action='domain_report'"
                        resp = await client.get(f"{manager.API_BASE}/domain/report", params={"query": domain})
                    else:
                        return f"Error: Unknown action '{action}'. Valid: ip_report, domain_report"
                    resp.raise_for_status()
                    data = resp.json()
                if manager.key_rotator:
                    manager.key_rotator.tick()

                if action == "ip_report":
                    lines = [f"Criminal IP Report: {ip}"]
                    score = data.get("score", {})
                    if isinstance(score, dict):
                        inbound = score.get("inbound", "N/A")
                        outbound = score.get("outbound", "N/A")
                        lines.append(f"Risk Score: inbound={inbound}, outbound={outbound}")
                    issues = data.get("issues", {})
                    if isinstance(issues, dict):
                        flags = [k for k, v in issues.items() if v]
                        if flags:
                            lines.append(f"Issues: {', '.join(flags)}")
                    whois = data.get("whois", {})
                    if isinstance(whois, dict):
                        org = whois.get("org_name", "")
                        country = whois.get("org_country_code", "")
                        if org:
                            lines.append(f"Organization: {org}")
                        if country:
                            lines.append(f"Country: {country}")
                    ports = data.get("port", [])
                    if isinstance(ports, list) and ports:
                        open_ports = [str(p.get("open_port_no", "?")) for p in ports[:20] if isinstance(p, dict)]
                        lines.append(f"Open ports ({len(ports)}): {', '.join(open_ports)}")
                    return "\n".join(lines)

                # domain_report
                lines = [f"Criminal IP Domain Report: {domain}"]
                if isinstance(data, dict):
                    main_info = data.get("data", data)
                    if isinstance(main_info, dict):
                        for key in ("risk_score", "is_malicious", "technologies"):
                            val = main_info.get(key)
                            if val is not None:
                                lines.append(f"{key}: {val}")
                return "\n".join(lines)

            except httpx.HTTPStatusError as e:
                return _osint_http_error("Criminal IP", e)
            except Exception as e:
                logger.error(f"Criminal IP {action} failed: {e}")
                return f"Criminal IP error: {str(e)}"

        logger.info("Criminal IP threat intelligence tool configured (2 actions)")
        return criminalip


# =============================================================================
# CLAUDE CODE TOOL MANAGER
# =============================================================================

class ClaudeCodeToolManager:
    """
    Manages Claude Code integration via a lightweight host proxy.

    The agent container calls the RedAmon Claude Code Proxy
    (claude_proxy/server.py) running on the host at host.docker.internal:8099.
    The proxy invokes the host's `claude --print` binary which is already
    authenticated via the user's existing Claude Code session (macOS Keychain
    OAuth). No API key or in-container login is required.
    """

    def __init__(self, proxy_url: str = None):
        default = os.environ.get(
            'CLAUDE_PROXY_URL',
            'http://host.docker.internal:8099'
        )
        self.proxy_url = (proxy_url or default).rstrip('/')

    def _proxy_reachable(self) -> bool:
        """Quick synchronous check that the proxy health endpoint responds."""
        try:
            import urllib.request
            with urllib.request.urlopen(f"{self.proxy_url}/health", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    def get_tool(self) -> Optional[callable]:
        """
        Return the claude_code LangChain tool.

        Returns None if the Claude Code proxy is not reachable, logging a
        clear startup hint so operators can fix it easily.
        """
        if not self._proxy_reachable():
            logger.warning(
                f"Claude Code proxy not reachable at '{self.proxy_url}/health'. "
                "Start it with: ./redamon.sh start-claude-proxy  "
                "(or: python3 claude_proxy/server.py)"
            )
            return None

        manager = self

        @tool
        async def claude_code(task: str, working_directory: str = '/tmp') -> str:
            """
            Execute a code analysis or security review task using Claude Code.

            This tool delegates to the Claude Code CLI running on the host via
            the RedAmon Claude Code Proxy. It uses the host's existing Claude
            Code login session — no API key configuration in RedAmon is needed.

            Use this tool to:
            - Analyze source code files for security vulnerabilities (SQLi, XSS, SSRF, RCE, etc.)
            - Hunt for hardcoded credentials, API keys, and tokens inside discovered repositories
            - Review configuration files and IaC templates for misconfigurations
            - Examine JavaScript/TypeScript bundles for exposed secrets or internal API endpoints
            - Generate a security-focused summary of an application's attack surface from its code
            - Investigate post-exploitation artifacts (scripts, configs) left on compromised hosts

            Args:
                task: Clear description of the analysis or review task to perform.
                working_directory: Absolute path to the directory containing code to analyze.
                                   Defaults to /tmp. Must already exist on the filesystem.

            Returns:
                Claude Code's full analysis output, findings, and recommendations.
            """
            import httpx

            payload = {"task": task, "working_directory": working_directory}
            logger.info(
                f"Forwarding claude_code task to proxy at {manager.proxy_url} "
                f"(dir: {working_directory}, task length: {len(task)} chars)"
            )

            try:
                async with httpx.AsyncClient(timeout=320) as client:
                    resp = await client.post(f"{manager.proxy_url}/claude", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("output", "Claude Code returned no output.")

            except httpx.ConnectError:
                return (
                    f"Error: Claude Code proxy is not running at '{manager.proxy_url}'. "
                    "Start it with: ./redamon.sh start-claude-proxy"
                )
            except httpx.TimeoutException:
                return "Error: Claude Code proxy timed out after 320 seconds."
            except Exception as e:
                logger.error(f"Claude Code proxy call failed: {e}")
                return f"Error calling Claude Code proxy: {e}"

        return claude_code


# =============================================================================
# PHASE-AWARE TOOL EXECUTOR
# =============================================================================

class PhaseAwareToolExecutor:
    """
    Executes tools with phase-awareness.
    Validates that tools are allowed in the current phase before execution.
    """

    def __init__(
        self,
        mcp_manager: MCPToolsManager,
        graph_tool: Optional[callable],
        web_search_tool: Optional[callable] = None,
        shodan_tool: Optional[callable] = None,
        google_dork_tool: Optional[callable] = None,
        osint_tools: Optional[Dict[str, callable]] = None,
        claude_code_tool: Optional[callable] = None,
    ):
        self.mcp_manager = mcp_manager
        self.graph_tool = graph_tool
        self.web_search_tool = web_search_tool
        self._all_tools: Dict[str, callable] = {}

        # Register graph tool
        if graph_tool:
            self._all_tools["query_graph"] = graph_tool

        # Register web search tool
        if web_search_tool:
            self._all_tools["web_search"] = web_search_tool

        # Register Shodan tool
        if shodan_tool:
            self._all_tools["shodan"] = shodan_tool

        # Register Google dork tool
        if google_dork_tool:
            self._all_tools["google_dork"] = google_dork_tool

        # Register additional OSINT tools (censys, fofa, otx, netlas, virustotal, zoomeye, criminalip)
        if osint_tools:
            for name, t in osint_tools.items():
                if t is not None:
                    self._all_tools[name] = t

        # Register Claude Code tool
        if claude_code_tool:
            self._all_tools["claude_code"] = claude_code_tool

    def register_mcp_tools(self, tools: List) -> None:
        """Register MCP tools after they're loaded."""
        for tool in tools:
            tool_name = getattr(tool, 'name', None)
            if tool_name:
                self._all_tools[tool_name] = tool

    def update_web_search_tool(self, tool: callable) -> None:
        """Replace the web search tool (e.g. when Tavily key changes)."""
        self.web_search_tool = tool
        self._all_tools["web_search"] = tool

    def update_shodan_tool(self, tool: Optional[callable]) -> None:
        """Replace or remove the Shodan tool (e.g. when API key changes)."""
        if tool:
            self._all_tools["shodan"] = tool
        else:
            self._all_tools.pop("shodan", None)

    def update_google_dork_tool(self, tool: Optional[callable]) -> None:
        """Replace or remove the Google dork tool (e.g. when SerpAPI key changes)."""
        if tool:
            self._all_tools["google_dork"] = tool
        else:
            self._all_tools.pop("google_dork", None)

    def update_osint_tool(self, name: str, tool: Optional[callable]) -> None:
        """Replace or remove an OSINT tool by name."""
        if tool:
            self._all_tools[name] = tool
        else:
            self._all_tools.pop(name, None)

    def update_claude_code_tool(self, tool: Optional[callable]) -> None:
        """Replace or remove the Claude Code tool (e.g. when enabled/disabled in project settings)."""
        if tool:
            self._all_tools["claude_code"] = tool
        else:
            self._all_tools.pop("claude_code", None)

    def _extract_text_from_output(self, output) -> str:
        """
        Extract clean text from MCP tool output.

        MCP tools return responses in various formats:
        - List of content blocks: [{'type': 'text', 'text': '...', 'id': '...'}]
        - Plain string
        - Other formats

        This method normalizes all formats to clean text.
        """
        if output is None:
            return ""

        # If it's already a string, return it
        if isinstance(output, str):
            return output

        # If it's a list (MCP content blocks format)
        if isinstance(output, list):
            text_parts = []
            for item in output:
                if isinstance(item, dict):
                    # Extract 'text' field from content block
                    if 'text' in item:
                        text_parts.append(item['text'])
                    elif 'content' in item:
                        text_parts.append(str(item['content']))
                elif isinstance(item, str):
                    text_parts.append(item)
            return '\n'.join(text_parts) if text_parts else str(output)

        # If it's a dict with 'text' or 'content'
        if isinstance(output, dict):
            if 'text' in output:
                return output['text']
            if 'content' in output:
                return str(output['content'])
            if 'output' in output:
                return str(output['output'])

        # Fallback: convert to string
        return str(output)

    async def execute(
        self,
        tool_name: str,
        tool_args: dict,
        phase: str,
        skip_phase_check: bool = False
    ) -> dict:
        """
        Execute a tool if allowed in the current phase.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool
            phase: Current agent phase
            skip_phase_check: If True, bypass phase restriction (for internal use like prewarm)

        Returns:
            dict with 'success', 'output', and optionally 'error'
        """
        # Check phase restriction
        if not skip_phase_check and not is_tool_allowed_in_phase(tool_name, phase):
            return {
                "success": False,
                "output": None,
                "error": f"Tool '{tool_name}' is not allowed in '{phase}' phase. "
                         f"This tool requires: {get_phase_for_tool(tool_name)}"
            }

        # Get the tool
        tool = self._all_tools.get(tool_name)
        if not tool:
            return {
                "success": False,
                "output": None,
                "error": f"Tool '{tool_name}' not found"
            }

        try:
            # Execute the tool
            if tool_name == "query_graph":
                # Graph tool expects 'question' argument
                question = tool_args.get("question", "")
                output = await tool.ainvoke(question)
            elif tool_name == "web_search":
                # Web search tool expects 'query' argument
                query = tool_args.get("query", "")
                output = await tool.ainvoke(query)
            elif tool_name == "shodan":
                # Shodan tool handles routing internally via action param
                output = await tool.ainvoke(tool_args)
            elif tool_name == "google_dork":
                # Google dork tool expects 'query' argument
                query = tool_args.get("query", "")
                output = await tool.ainvoke(query)
            else:
                # MCP tools - invoke with the appropriate argument
                output = await tool.ainvoke(tool_args)

            # Extract clean text from MCP response
            # MCP returns list of content blocks: [{'type': 'text', 'text': '...', 'id': '...'}]
            clean_output = self._extract_text_from_output(output)

            return {
                "success": True,
                "output": clean_output,
                "error": None
            }

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return {
                "success": False,
                "output": None,
                "error": str(e)
            }

    async def execute_with_progress(
        self,
        tool_name: str,
        tool_args: dict,
        phase: str,
        progress_callback: Callable[[str, str, bool], Awaitable[None]],
        poll_interval: float = 5.0,
        progress_url: str | None = None
    ) -> dict:
        """
        Execute a long-running tool with integrated progress streaming.

        Polls the HTTP progress endpoint during execution and sends updates
        via the progress_callback. Works with any tool that exposes a
        /progress HTTP endpoint (Metasploit on 8013, Hydra on 8014).

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool
            phase: Current agent phase
            progress_callback: Async callback(tool_name, chunk, is_final)
            poll_interval: How often to poll for progress (seconds)
            progress_url: HTTP URL for progress endpoint. Defaults to Metasploit's.

        Returns:
            dict with 'success', 'output', and optionally 'error'
        """
        # Start the main tool execution as a background task
        execution_task = asyncio.create_task(
            self.execute(tool_name, tool_args, phase)
        )

        last_line_count = 0
        last_output = ""

        url = progress_url or os.environ.get(
            'MCP_METASPLOIT_PROGRESS_URL',
            'http://host.docker.internal:8013/progress'
        )

        async with httpx.AsyncClient(timeout=2.0) as client:
            while not execution_task.done():
                await asyncio.sleep(poll_interval)

                if execution_task.done():
                    break

                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        progress = resp.json()

                        if progress.get("active"):
                            current_output = progress.get("output", "")
                            line_count = progress.get("line_count", 0)
                            elapsed = progress.get("elapsed_seconds", 0)

                            # Only send if new content
                            if line_count > last_line_count and current_output != last_output:
                                # Calculate the new portion
                                if last_output and current_output.startswith(last_output):
                                    new_content = current_output[len(last_output):]
                                else:
                                    new_content = current_output

                                if new_content.strip():
                                    # Format progress update with context
                                    progress_msg = f"[Progress: {line_count} lines, {elapsed}s]\n{new_content[-1000:]}"
                                    await progress_callback(
                                        tool_name,
                                        progress_msg,
                                        False  # not final
                                    )

                                last_output = current_output
                                last_line_count = line_count

                except httpx.TimeoutException:
                    # Progress polling timeout is fine, continue
                    pass
                except httpx.HTTPError as e:
                    # Connection errors during polling are best-effort, log and continue
                    logger.debug(f"Progress polling error (non-fatal): {e}")
                except Exception as e:
                    # Unexpected errors, log but don't fail the execution
                    logger.warning(f"Progress polling unexpected error: {e}")

        # Wait for the execution to complete and return result
        return await execution_task

    def get_all_tools(self) -> List:
        """Get all registered tools."""
        return list(self._all_tools.values())

    def get_tools_for_phase(self, phase: str) -> List:
        """Get tools allowed in the given phase."""
        return [
            tool for name, tool in self._all_tools.items()
            if is_tool_allowed_in_phase(name, phase)
        ]


def get_phase_for_tool(tool_name: str) -> str:
    """Get the minimum phase required for a tool."""
    allowed_phases = get_setting('TOOL_PHASE_MAP', {}).get(tool_name, [])
    if "informational" in allowed_phases:
        return "informational"
    elif "exploitation" in allowed_phases:
        return "exploitation"
    elif "post_exploitation" in allowed_phases:
        return "post_exploitation"
    return "unknown"
