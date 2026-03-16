# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.0.0] - 2026-03-15

### Added

- **Zero-config setup — `.env` file completely removed** — all user-configurable settings (NVD API key, ngrok auth token, chisel server URL/auth) are now managed from the Global Settings UI page and stored in PostgreSQL. No `.env` or `.env.example` file is needed.
  - **Global Settings → Tool API Keys**: NVD API key added alongside Tavily, Shodan, SerpAPI
  - **Global Settings → Tunneling**: new section for ngrok and chisel tunnel configuration with live push to kali-sandbox (no container restart needed)
  - **Tunnel Manager API**: lightweight HTTP server on port 8015 inside kali-sandbox that receives tunnel config pushes from the webapp and manages ngrok/chisel processes
  - **Boot-time config fetch**: kali-sandbox fetches tunnel credentials from webapp DB on startup
  - **NVD API key fallback**: project-level `nvdApiKey` falls back to user-level global setting from UserSettings
  - **Bug fix**: NVD API key was never actually passed to CVE lookup function — now correctly wired through

- **Denial of Service (DoS) Attack Skill** — new built-in attack skill for disrupting service availability. Includes LLM prompt templates for DoS vector selection, resource exhaustion, flooding, and crash exploits. Full integration across the stack:
  - **Backend**: `denial_of_service_prompts.py` with DoS-specific workflow guidance, vector classification, and impact assessment prompts
  - **Orchestrator**: DoS attack path type (`denial_of_service`) integrated into classification, phase transitions, and tool registry
  - **Database**: Prisma schema updated with DoS configuration fields and project-level toggle
  - **Frontend**: `DosSection.tsx` configuration component in the project form for enabling/disabling and tuning DoS parameters
  - **API**: attack skills endpoint updated to expose DoS as a built-in skill

- **Expanded Finding Types** — 8 new goal/outcome `finding_type` values for ChainFinding nodes, covering real-world pentesting outcomes beyond the original 10 types:
  - `data_exfiltration` — data successfully stolen/exfiltrated
  - `lateral_movement` — pivot to another system in the network
  - `persistence_established` — backdoor, cron job, or persistent access installed
  - `denial_of_service_success` — service confirmed down after DoS attack
  - `social_engineering_success` — phishing or social engineering succeeded
  - `remote_code_execution` — arbitrary code execution achieved
  - `session_hijacked` — existing user session taken over
  - `information_disclosure` — sensitive info leaked (source code, API keys, error messages)
  - LLM prompts updated to guide the agent in emitting the correct goal type
  - Analytics and report queries expanded to include all goal types

- **Goal Finding Visualization** — ChainFinding diamond nodes on the attack surface graph now visually distinguish goal/outcome findings from informational ones:
  - **Active chain**: goal diamonds are bright green (`#4ade80`), non-goal diamonds remain amber
  - **Inactive chain**: goal diamonds are dark green (`#276d43`), non-goal diamonds are dark yellow (`#3d3107`), other chain nodes remain dark grey
  - Inactive chain edges and particles darkened for better contrast
  - Active chain particles brighter (`#9ca3af`) for clear visual distinction
  - Applied consistently to both 2D and 3D graph renderers

- **Inline Model Picker** — the model badge in the AI assistant drawer is now clickable, opening a searchable modal to switch LLM model on the fly. Models are grouped by provider with context-length badges and descriptions. Includes a manual-input fallback when the models API is unreachable. Shared model utilities (`ModelOption` type, `formatContextLength`, `getDisplayName`) extracted into `modelUtils.ts` and reused across the drawer and project form.

- **Animated Loading Indicator** — replaced static "Processing..." text in the AI assistant chat with a dynamic loading experience:
  - **RedAmon eye logo** with randomized heartbeat animation (2–6s random intervals)
  - **Color-shifting pupil** cycling through 13 bright colors (yellow, cyan, orange, purple, green, pink, etc.)
  - **60 rotating hacker-themed phrases** displayed in random order every 5 seconds with fade-in animation (e.g., "Unmasking the hidden...", "Piercing the veil...", "Becoming root...")

- **URLScan.io OSINT Integration** — new passive enrichment module that queries URLScan.io's Search API to discover subdomains, IPs, TLS metadata, server technologies, domain age, and screenshots from historical scans. Runs in the recon pipeline after domain discovery, before port scanning. Full integration across the stack:
  - **New module**: `recon/urlscan_enrich.py` — fetches historical scan data from URLScan.io for each discovered domain. Works without API key (public results) or with API key (higher rate limits and access to private scans)
  - **Passive OSINT data**: discovers in-scope subdomains, IP addresses, URL paths for endpoint creation, TLS validity, ASN information, and external domains from historical scans
  - **GAU provider deduplication**: when URLScan enrichment has already run, the `urlscan` provider is automatically removed from GAU's data sources to avoid redundant API calls to the same underlying data
  - **Pipeline placement**: runs after domain discovery and before port scanning, alongside Shodan enrichment
  - **Project settings**: `urlscanEnabled` toggle and `urlscanMaxResults` (default: 500) configurable per project. Optional API key in Global Settings → Tool API Keys
  - **Frontend**: new `UrlscanSection.tsx` in the Discovery & OSINT tab with passive badge, API key status indicator, and max results configuration

- **ExternalDomain Node** — new graph node type for tracking out-of-scope domains encountered during reconnaissance. Provides situational awareness about the target's external dependencies without scanning them:
  - **Schema**: `(:ExternalDomain { domain, sources[], redirect_from_urls[], redirect_to_urls[], status_codes_seen[], titles_seen[], servers_seen[], ips_seen[], countries_seen[], times_seen, first_seen_at, updated_at })`
  - **Relationship**: `(d:Domain)-[:HAS_EXTERNAL_DOMAIN]->(ed:ExternalDomain)`
  - **Multi-source aggregation**: external domains are collected from HTTP probe redirects, URLScan historical data, GAU passive archives, Katana crawling, and certificate transparency — then merged and deduplicated
  - **Neo4j constraints**: unique constraint on `(domain, user_id, project_id)` with tenant-scoped index
  - **Neo4j client**: new `update_graph_from_external_domains()` method for creating ExternalDomain nodes and HAS_EXTERNAL_DOMAIN relationships
  - **Graph schema docs**: `GRAPH.SCHEMA.md` updated with full ExternalDomain documentation

- **Discovery & OSINT Tab** — new unified tab in the project form replacing the previous scattered tool placement. Groups all passive and active discovery tools in a single section:
  - **Subdomain Discovery** — passive sources (crt.sh, HackerTarget, Knockpy Recon) and active brute-forcing (Knockpy Bruteforce), plus DNS settings (WHOIS/DNS retries)
  - **Shodan OSINT Enrichment** — moved from the Integrations tab into Discovery & OSINT, reflecting its role as a core discovery tool rather than an external integration. All four toggles (Host Lookup, Reverse DNS, Domain DNS, Passive CVEs) remain unchanged
  - **URLScan.io Enrichment** — new section with passive badge, max results config, and API key status
  - **Node Info Tooltips** — each section header now has a waypoints icon that shows which graph node types the tool creates (via `NodeInfoTooltip` component and `nodeMapping.ts`)
  - Recon toggle switches moved to section headers for cleaner layout

- **Agent Guardrail Toggle** — the scope guardrail (LLM-based target verification) can now be enabled or disabled per project:
  - **New setting**: `agentGuardrailEnabled` (default: `true`) — when disabled, the agent skips the scope verification check on session start
  - **Initialize node**: guardrail check is now conditional, skipped when setting is false or on retries to avoid redundant LLM calls
  - **Think node**: scope guardrail reminder in the system prompt only injected when enabled
  - **Guardrail LLM bootstrapping**: the guardrail API endpoint now fetches the user's configured LLM providers from the database to properly initialize the LLM with the correct API keys (OpenAI, Anthropic, or OpenRouter)
  - **Frontend**: checkbox in Agent Behaviour section
  - **Fail-closed**: if the guardrail check itself fails (API error, LLM error), the agent is blocked by default (security-first)

- **Multi-source CVE Attribution** — CVE nodes created from Shodan data now track their source (`source` property) instead of hardcoding "shodan", enabling future enrichment from multiple CVE databases (NVD, Vulners, etc.)

### Fixed

- **Banner grabbing data loss** — fixed falsy value filtering in `neo4j_client.py` banner property handling. Changed `if v` to `if v is not None` to preserve empty strings and zero values that are valid banner data

### Changed

- Kali sandbox Dockerfile updated
- Shodan OSINT Enrichment moved from the Integrations tab to the new Discovery & OSINT tab in the project form
- Integrations tab now contains only GitHub Secret Hunting (Shodan removed)
- Recon pipeline toggle switches moved from section bodies to section headers for a cleaner UI
- Documentation and wiki updates

---

## [2.3.0] - 2026-03-14

### Added

- **Global Settings Page** — new `/settings` page (gear icon in header) for managing all user-level configuration through the UI. AI provider keys and Tavily API key are configured exclusively here — no `.env` file needed. Two sections:
  - **LLM Providers** — add, edit, delete, and test LLM provider configurations stored per-user in the database. Supports five provider types:
    - **OpenAI, Anthropic, OpenRouter** — enter API key, all models auto-discovered
    - **AWS Bedrock** — enter AWS credentials + region, foundation models auto-discovered
    - **OpenAI-Compatible** — single endpoint+model configuration with presets for Ollama, vLLM, LM Studio, Groq, Together AI, Fireworks AI, Mistral AI, and Deepinfra. Supports custom base URL, headers, timeout, temperature, and max tokens
  - **Tool API Keys** — Tavily API key (web search), Shodan API key (internet-wide OSINT), and SerpAPI key (Google dorking)
- **Test Connection** — each LLM provider can be tested before saving with a "Test Connection" button that sends a simple message and shows the response
- **DB-only settings** — AI provider keys and Tavily API key are stored exclusively in the database (per-user). No env-var fallback — `.env` is reserved for infrastructure variables only (NVD, tunneling, database credentials, ports)
- **Prisma schema** — added `UserLlmProvider` and `UserSettings` models with relations to `User`
- **Centralized LLM setup** — CypherFix triage and codefix orchestrators now use the shared `setup_llm()` function instead of duplicating provider routing logic

- **Pentest Report Generation** — generate professional, client-ready penetration testing reports as self-contained HTML files from the `/reports` page. Reports compile all reconnaissance data, vulnerability findings, CVE intelligence, attack chain results, and remediation recommendations into an 11-section document (Cover, Executive Summary, Scope & Methodology, Risk Summary, Findings, Other Vulnerability Details, Attack Surface, CVE Intelligence, GitHub Secrets, Attack Chains, Recommendations, Appendix). Features include:
  - **LLM-generated narratives** — when an AI model is configured, six report sections receive detailed prose: executive summary (8–12 paragraphs), scope, risk analysis, findings context, attack surface analysis, and exhaustive prioritized remediation triage. Falls back gracefully to data-only reports when no LLM is available
  - **Security Posture Radar** — inline SVG 6-axis radar chart in the Risk Summary section showing Attack Surface, Vulnerability Density, Exploitability, Certificate Health, Injectable Parameters, and Security Header coverage using logarithmic normalization
  - **Security Headers Gap Analysis** — per-header weighted coverage bars (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy) with color-coded thresholds
  - **CISA KEV Callout** — prominent alert box highlighting Known Exploited Vulnerabilities when present
  - **Injectable Parameters Breakdown** — summary and per-position injection risk analysis with visual bars
  - **Attack Flow Chains** — Technology → CVE → CWE → CAPEC flow table showing complete attack paths
  - **CDN Coverage visualization** — ratio of CDN-fronted vs directly exposed IPs in the Attack Surface section
  - **Project-specific generation** — dedicated project selector dropdown on the reports page (independent of the top bar selection)
  - **Download and Open** — separate buttons to save the HTML file locally or open in a new browser tab
  - **Print/PDF optimized** — page breaks, print-friendly CSS, and clean SVG/CSS bar rendering for `Ctrl+P` export
  - **Export/Import support** — reports (metadata + HTML files) are included in project export ZIP archives and fully restored on import
  - **Wiki documentation** — new [Pentest Reports](redamon.wiki/20.-Pentest-Reports) wiki page with example report download

- **Target Guardrail** — LLM-based safety check that prevents targeting unauthorized domains and IPs. Blocks government sites (`.gov`, `.mil`), major tech companies, financial institutions, social media platforms, and other well-known public services. Two layers: project creation (fail-open) and agent initialization (fail-closed). For IP mode, public IPs are resolved via reverse DNS before evaluation; private/RFC1918 IPs are auto-allowed. Blocked targets show a centered modal with the reason.

- **Expanded CPE Technology Mappings** — CPE_MAPPINGS table in `recon/helpers/cve_helpers.py` expanded from 82 to 133 entries, significantly improving CVE lookup accuracy for Wappalyzer-detected technologies. New coverage includes:
  - **CMS**: Magento, Ghost, TYPO3, Concrete CMS, Craft CMS, Strapi, Umbraco, Adobe Experience Manager, Sitecore, DNN, Kentico
  - **Web Frameworks**: CodeIgniter, Symfony, CakePHP, Yii, Nuxt.js, Apache Struts, Adobe ColdFusion
  - **JavaScript Libraries**: Moment.js, Lodash, Handlebars, Ember.js, Backbone.js, Dojo, CKEditor, TinyMCE, Prototype
  - **E-commerce**: PrestaShop, OpenCart, osCommerce, Zen Cart, WooCommerce
  - **Message Boards / Community**: Discourse, phpBB, vBulletin, MyBB, Flarum, NodeBB, Mastodon, Mattermost
  - **Wikis**: MediaWiki, Atlassian Confluence, DokuWiki, XWiki
  - **Issue Trackers / DevOps**: Atlassian Jira, Atlassian Bitbucket, Bugzilla, Redmine, Gitea, TeamCity, Artifactory
  - **Hosting Panels**: cPanel, Plesk, DirectAdmin
  - **Web Servers**: OpenResty, Deno, Tengine
  - **Databases**: SQLite, Apache Solr, Adminer
  - **Security / Network**: Kong, F5 BIG-IP, Pulse Secure
  - **Webmail**: Zimbra, SquirrelMail
  - 29 new `normalize_product_name()` aliases for Wappalyzer output variations (e.g., "Atlassian Jira" → "jira", "Moment" → "moment.js", "Concrete5" → "concrete cms")
  - 6 new `skip_list` entries (Cloudflare, Google Analytics, Google Tag Manager, Facebook Pixel, Hotjar, Google Font API) to avoid wasting NVD API calls on SaaS/CDN technologies

- **Insights Dashboard** — Real-time analytics page (`/insights`) with interactive charts and tables covering attack chains, exploit successes, finding severity, targets attacked, strategic decisions, vulnerability distributions, attack surface composition, and agent activity. All data is pulled directly from the Neo4j graph and organized into sections: Attack Chains & Exploits, Attack Surface, Vulnerabilities & CVE Intelligence, Graph Overview, and Activity & Timeline.

- **Rules of Engagement (RoE)** — upload a RoE document (PDF, TXT, MD, DOCX) at project creation and an LLM auto-parses it into structured settings enforced across the entire platform:
  - **Document upload & parsing** — file upload area in the RoE tab of the project form (create mode only). The agent extracts client info, scope, exclusions, time windows, testing permissions, rate limits, data handling policies, compliance frameworks, and more into 30+ structured fields
  - **Three enforcement layers** — (1) agent prompt injection: structured `RULES OF ENGAGEMENT (MANDATORY)` section injected into every reasoning step with excluded hosts, permissions, and constraints; (2) hard gate in `execute_tool_node`: deterministic code blocks forbidden tools, forbidden categories, permission flags, and phase cap violations regardless of LLM output; (3) recon pipeline: excluded hosts filtered from target lists, rate limits capped via `min(tool_rate, global_max)`, time window blocks scan starts outside allowed hours
  - **30+ RoE project fields** — client & engagement info, excluded hosts with reasons, time windows (days/hours/timezone), 6 testing permission toggles (DoS, social engineering, physical access, data exfiltration, account lockout, production testing), forbidden tool/category lists, max severity phase cap, global rate limit, sensitive data handling policy, data retention, encryption requirements, status update frequency, critical finding notification, incident procedure, compliance frameworks, third-party providers, and free-text notes
  - **RoE Viewer tab** on the graph dashboard — formatted read-only view with cards for engagement, scope, exclusions, time window (live ACTIVE/OUTSIDE WINDOW status), testing permissions (green/red badge grid), constraints, data handling, communication, compliance, and notes. Download button for the original uploaded document
  - **RoE toolbar badge** — blue "RoE" badge on the graph toolbar when engagement guardrails are active
  - **Smart tool restriction parsing** — only explicitly banned tools (e.g., "do not use Hydra") are disabled; "discouraged" or "use with caution" language is noted in the prompt but does not disable tools. Phase restrictions use `roeMaxSeverityPhase` instead of stripping phases from individual tools
  - **Export/import support** — RoE document binary is base64-encoded in project exports and restored on import. All RoE fields are included in the export ZIP
  - **Cascade deletion** — all RoE data (fields + document binary) deleted with the project via Prisma cascade
  - One-way at creation only — RoE settings become read-only after project creation to prevent mid-engagement modification
  - Based on industry standards: PTES, SANS, NIST SP 800-115, Microsoft RoE, HackerOne, Red Team Guide

- **Emergency PAUSE ALL button** — red/yellow danger-styled button on the Graph toolbar that instantly freezes every running pipeline (Recon, GVM, GitHub Hunt) and stops all AI agent conversations in one click. Shows "PAUSING..." with spinner during operation. Always visible on the toolbar, disabled when nothing is running. New `POST /emergency-stop-all` endpoint on the agent service cancels all active agent tasks via the WebSocket manager

- **Wave Runner (Parallel Tool Plans)** — when the LLM identifies two or more independent tools that don't depend on each other's outputs, it groups them into a **wave** and executes them concurrently via `asyncio.gather()` instead of sequentially. Key components:
  - **New LLM action**: `plan_tools` alongside `use_tool` — the LLM emits a `ToolPlan` with multiple `ToolPlanStep` entries and a plan rationale
  - **New LangGraph node**: `execute_plan` runs all steps in parallel, each with its own RoE gate check, tool_start/tool_complete streaming, and progress updates
  - **Combined wave analysis**: after all tools finish, the think node analyzes all outputs together in a single LLM call, producing consolidated findings and next steps
  - **Three new WebSocket events**: `plan_start` (wave begins with tool list), `plan_complete` (success/failure counts), `plan_analysis` (LLM interpretation). Existing `tool_start`, `tool_output_chunk`, and `tool_complete` events carry an optional `wave_id` to group tools within a wave
  - **Frontend PlanWaveCard**: grouped card in AgentTimeline showing all wave tools nested together with status badge (Running/Success/Partial/Error), plan rationale, combined analysis, actionable findings, and recommended next steps
  - **State management**: new `ToolPlan` and `ToolPlanStep` Pydantic models, `_current_plan` field in `AgentState`
  - **Graceful fallback**: empty `tool_plan` objects or plans with no steps are automatically downgraded to sequential `use_tool` execution

- **Attack Skills System** — modular attack path management with built-in and user-uploaded skills:
  - **Built-in Attack Skills** — four core skills (CVE (MSF), Brute Force, Phishing / Social Engineering, Denial of Service) can now be individually enabled or disabled per project via toggles in the new Attack Skills section of Project Settings. Disabling a skill prevents the agent from classifying requests into that attack type and removes its prompts from the system prompt. Sub-settings (Hydra config, SMTP config, DoS parameters) are shown inline when the corresponding skill is enabled
  - **User Attack Skills** — upload custom `.md` files defining attack workflows from Global Settings. Each skill file contains a full workflow description that the agent follows across all three phases (informational, exploitation, post-exploitation). User skills are stored per-user in the database (`UserAttackSkill` model) and become available as toggles in all project settings
  - **Skill Management in Global Settings** — dedicated "Attack Skills" section with upload button (accepts `.md` files, max 50KB), skill list with download and delete actions, and a name-entry modal on upload
  - **Per-project skill toggles** — `attackSkillConfig` JSON field in the project stores `{ builtIn: { skill_id: bool }, user: { skill_id: bool } }` controlling which skills are active. Built-in skills default to enabled; user skills default to enabled when present
  - **Agent integration** — LLM classifier routes requests to user skills via `user_skill:<id>` attack path type. Skill `.md` content is injected into the system prompt for all three phases with phase-appropriate guidance. Falls back to unclassified workflow if skill content is missing
  - **API endpoints** — `GET/POST /api/users/[id]/attack-skills` (list/create), `GET/DELETE /api/users/[id]/attack-skills/[skillId]` (read/delete), `GET /api/users/[id]/attack-skills/available` (with content for agent consumption)
  - Max 20 skills per user, 50KB per skill file

- **Kali Shell — Library Installation Control** — new prompt-based setting in Agent Behaviour to control whether the agent can install packages via `pip install` or `apt install` in `kali_shell` during a pentest:
  - **Toggle**: "Allow Library Installation" — when disabled (default), the system prompt instructs the agent to only use pre-installed tools and libraries. When enabled, the agent may install packages as needed for specific attacks
  - **Authorized Packages (whitelist)** — comma-separated list. When non-empty, only these packages may be installed; the agent is instructed not to install anything outside the list
  - **Forbidden Packages (blacklist)** — comma-separated list. These packages must never be installed, regardless of the whitelist
  - Installed packages are ephemeral — lost on container restart. Prompt-based control only (no server-side enforcement)
  - Conditional UI: whitelist and blacklist textareas only appear when the toggle is enabled
  - `build_kali_install_prompt()` dynamically generates the installation rules section, injected into the system prompt whenever `kali_shell` is in the allowed tools for the current phase

- **Shodan OSINT Integration** — full Shodan integration at two levels: automated recon pipeline and interactive AI agent tool:
  - **Pipeline enrichment** — new `recon/shodan_enrich.py` module runs after domain/IP discovery, before port scanning. Four independently toggled features: Host Lookup (IP geolocation, OS, ISP, open ports, services, banners), Reverse DNS (hostname discovery), Domain DNS (subdomain enumeration + DNS records, paid plan), and Passive CVEs (extract known CVEs from host data)
  - **InternetDB fallback** — when the Shodan API returns 403 (free key), host lookup and reverse DNS automatically fall back to Shodan's free InternetDB API (`internetdb.shodan.io`) which provides ports, hostnames, CPEs, CVEs, and tags without requiring a paid plan
  - **Graph database ingestion** — `update_graph_from_shodan()` in `neo4j_client.py` creates/updates IP nodes (os, isp, org, country, city), Port + Service nodes, Subdomain nodes from reverse DNS, DNSRecord nodes from domain DNS, and Vulnerability + CVE nodes from passive CVEs — all using MERGE for deduplication with existing pipeline data
  - **Agent tool** — unified `shodan` tool with 5 actions: `search` (device search, paid key), `host` (detailed IP info), `dns_reverse` (reverse DNS), `dns_domain` (DNS records + subdomains, paid key), and `count` (host count without search credits). Available in all agent phases
  - **Project settings** — 4 pipeline toggles in the Integrations tab (`ShodanSection.tsx`): Host Lookup, Reverse DNS, Domain DNS, Passive CVEs. Toggles are disabled with a warning banner when no Shodan API key is configured in Global Settings
  - **Graceful error handling** — `ShodanApiKeyError` exception for immediate abort on invalid keys (401); per-function 403 handling with InternetDB fallback; pipeline continues even if Shodan enrichment fails entirely

- **Google Dork Tool (SerpAPI)** — new `google_dork` agent tool for passive OSINT via Google advanced search operators. Uses the SerpAPI Google engine to find exposed files (`filetype:sql`, `filetype:env`), admin panels (`inurl:admin`), directory listings (`intitle:"index of"`), and sensitive data leaks (`intext:password`). Returns up to 10 results with titles, URLs, snippets, and total result count. SerpAPI key configured in Global Settings. No packets are sent to the target — purely passive reconnaissance

- **Deep Think (Strategic Reasoning)** — automatic strategic analysis at key decision points during agent operation. Triggers on: first iteration (initial strategy), phase transitions (re-evaluation), failure loops (3+ consecutive failures trigger pivot), and agent self-request (when stuck or going in circles). Produces structured JSON analysis with situation assessment, identified attack vectors, recommended approach with rationale, priority-ordered action steps, and risk mitigations. The analysis is injected into subsequent reasoning steps to guide the agent's strategy:
  - **Toggle**: `DEEP_THINK_ENABLED` in Agent Behaviour settings (default: off)
  - **Self-request**: agent can set `"need_deep_think": true` in its output to trigger a strategic re-evaluation on the next iteration
  - **Frontend card**: `DeepThinkCard` in the Agent Timeline displays the analysis with trigger reason, situation assessment, attack vectors, recommended approach, priority steps, and risks — collapsible with a lightbulb icon
  - **WebSocket event**: `deep_think` event streams the analysis result to the frontend in real-time

- **Inline Agent Settings** — Agent Behaviour, Tool Matrix, and Attack Skills sections are now accessible directly from the AI Assistant drawer via a gear icon in the toolbar. Opens a modal overlay for quick configuration changes without navigating away from the graph page. Changes are saved to the project and take effect on the next agent iteration

- **Inline API Key Configuration** — when an agent tool is unavailable due to a missing API key (web_search, shodan, google_dork), the AI Assistant drawer shows a warning badge with a one-click modal to enter the key directly. No need to navigate to Global Settings

- **Tool Registry Overhaul** — compressed and restructured the agent's tool registry descriptions for all tools (query_graph, web_search, shodan, google_dork, curl, nmap, kali_shell, hydra, metasploit_command). Descriptions are more concise with inline argument formats and usage examples, reducing prompt token usage while maintaining clarity

### Fixed

- **Project export/import missing Remediations** — The `Remediation` table (CypherFix vulnerability remediations, code fixes, GitHub PR integrations, file changes) was not included in project export/import. Exports now include `remediations/remediations.json` in the ZIP archive, and imports restore all remediation records under the new project. Backward-compatible with older exports that lack the remediations file.

### Changed

- **Docker CLI upgrade in recon container** — Replaced Debian's `docker.io` package with `docker-ce-cli` from Docker's official APT repository. Fixes compatibility issues with newer host Docker daemons (closes #30, based on #35). Only the CLI is installed — no full engine, containerd, or compose plugins.

---

## [2.2.0] - 2026-03-05

### Added

- **Pipeline Pause / Resume / Stop Controls** — full lifecycle management for all three pipelines (Recon, GVM Scan, GitHub Secret Hunt):
  - **Pause** — freezes the running container via Docker cgroups (`container.pause()`). Zero changes to scan scripts; processes resume exactly where they left off
  - **Resume** — unfreezes the container (`container.unpause()`), logs resume streaming instantly
  - **Stop** — kills the container permanently. Paused containers are unpaused before stopping to avoid cgroup issues. Sub-containers (naabu, httpx, nuclei, etc.) are also cleaned up
  - **Toolbar UI** — when running: spinner + Pause button + Stop button. When paused: Resume button + Stop button. When stopping: "Stopping..." with disabled controls
  - **Logs drawer controls** — pause/resume and stop buttons in the status bar, with `Paused` status indicator and spinner during stopping
  - **Optimistic UI** — stop button immediately shows "Stopping..." before the API responds
  - **SSE stays alive** during pause and stopping states so logs resume/complete without reconnection
  - 6 new backend endpoints (`POST /{recon,gvm,github-hunt}/{projectId}/{pause,resume}`) and 9 new webapp API proxy routes (pause/resume/stop × 3 pipelines)
  - Removed the auto-scroll play/pause toggle from logs drawer (redundant with "Scroll to bottom" button)
- **IP/CIDR Targeting Mode** — start reconnaissance from IP addresses or CIDR ranges instead of a domain:
  - **"Start from IP" toggle** in the Target & Modules tab — switches the project from domain-based to IP-based targeting. Locked after creation (cannot switch modes on existing projects)
  - **Target IPs / CIDRs textarea** — accepts individual IPs (`192.168.1.1`), IPv6 (`2001:db8::1`), and CIDR ranges (`10.0.0.0/24`, `192.168.1.0/28`) with a max /24 (256 hosts) limit per CIDR
  - **Reverse DNS (PTR) resolution** — each IP is resolved to its hostname via PTR records. When no PTR exists, a mock hostname is generated from the IP (e.g., `192-168-1-1`)
  - **CIDR expansion** — CIDR ranges are automatically expanded into individual host IPs (network and broadcast addresses excluded). Original CIDRs are passed to naabu for efficient native scanning
  - **Full pipeline support** — IP-mode projects run the complete 6-phase pipeline: reverse DNS + IP WHOIS → port scan → HTTP probe → resource enumeration (Katana, Kiterunner) → vulnerability scan (Nuclei) → CVE/MITRE enrichment
  - **Neo4j graph integration** — mock Domain node (`ip-targets.{project_id}`) with `ip_mode: true`, Subdomain nodes (real PTR hostnames or IP-based mocks), IP nodes with WHOIS data, and all downstream relationships
  - **Tenant-scoped Neo4j constraints** — IP, Subdomain, BaseURL, Port, Service, and Technology uniqueness constraints are now scoped to `(key, user_id, project_id)`, allowing the same IP/subdomain to exist in different projects without conflicts
  - **Input validation** — new `webapp/src/lib/validation.ts` module with regex validators for IPs, CIDRs, domains, ports, status codes, HTTP headers, GitHub tokens, and more. Validation runs on form submit
  - `ipMode` and `targetIps` fields added to Prisma schema with database migration
- **Chisel TCP Tunnel Integration** — multi-port reverse tunnel alternative to ngrok for full attack path support:
  - chisel (v1.11.4) installed alongside ngrok in kali-sandbox Dockerfile — single binary, supports amd64 and arm64
  - Reverse tunnels both port 4444 (handler) and port 8080 (web delivery/HTA) through a single connection to a VPS
  - Enables **Web Delivery** (Method C) and **HTA Delivery** (Method D) phishing attacks that require two ports — previously blocked with ngrok's single-port limitation
  - **Stageless** Meterpreter payloads required through chisel (staged payloads fail through tunnels — same as ngrok)
  - Deterministic endpoint discovery — LHOST derived from `CHISEL_SERVER_URL` hostname (no API polling needed)
  - Auto-reconnect with exponential backoff if VPS connection drops
  - `CHISEL_SERVER_URL` and `CHISEL_AUTH` env vars added to `.env.example` and `docker-compose.yml`
  - `_query_chisel_tunnel()` utility in `agentic/utils.py` with `get_session_config_prompt()` integration
  - `agentChiselTunnelEnabled` Prisma field with database migration
- **Phishing / Social Engineering Attack Path** (`phishing_social_engineering`) — third classified attack path with a mandatory 6-step workflow: target platform selection, handler setup, payload generation, verification, delivery, and session callback:
  - **Standalone Payloads** (Method A): msfvenom-based payload generation for Windows (exe, psh, psh-reflection, vba, hta-psh), Linux (elf, bash, python), macOS (macho), Android (apk), Java (war), and cross-platform (python) — with optional AV evasion via shikata_ga_nai encoding
  - **Malicious Documents** (Method B): Metasploit fileformat modules for weaponized Word macro (.docm), Excel macro (.xlsm), PDF (Adobe Reader exploit), RTF (CVE-2017-0199 HTA handler), and LNK shortcut files
  - **Web Delivery** (Method C): fileless one-liner delivery via `exploit/multi/script/web_delivery` supporting Python, PHP, PowerShell, Regsvr32 (AppLocker bypass), pubprn, SyncAppvPublishingServer, and PSH Binary targets
  - **HTA Delivery** (Method D): HTML Application server via `exploit/windows/misc/hta_server` for browser-based payload delivery
  - **Email Delivery**: Python smtplib-based email sending via `execute_code` with per-project SMTP configuration (host, port, user, password, sender, TLS) — agent asks at runtime if no SMTP settings are configured
  - **Chat Download**: default delivery via `docker cp` command reported in chat
  - New prompt module `phishing_social_engineering_prompts.py` with `PHISHING_SOCIAL_ENGINEERING_TOOLS` (full workflow) and `PHISHING_PAYLOAD_FORMAT_GUIDANCE` (OS-specific format decision tree and msfvenom quick reference)
  - LLM classifier updated with phishing keywords and 10 example requests for accurate routing
  - `phishing_social_engineering` added to `KNOWN_ATTACK_PATHS` set and `AttackPathClassification` validator
- **ngrok TCP Tunnel Integration** — automatic reverse shell tunneling through ngrok for NAT/cloud environments:
  - ngrok installed in kali-sandbox Dockerfile and auto-started in `entrypoint.sh` when `NGROK_AUTHTOKEN` env var is set
  - TCP tunnel on port 4444 with ngrok API exposed on port 4040
  - `_query_ngrok_tunnel()` utility in `agentic/utils.py` that queries ngrok API, discovers the public TCP endpoint, and resolves the hostname to an IP for targets with limited DNS
  - `get_session_config_prompt()` auto-detects LHOST/LPORT from ngrok when enabled — injects a status banner, dual LHOST/LPORT table (handler vs payload), and enforces REVERSE-only payloads through ngrok
  - `is_session_config_complete()` short-circuits to complete when ngrok tunnel is active
  - `NGROK_AUTHTOKEN` added to `.env.example` and `docker-compose.yml` (kali-sandbox env + port 4040 exposed)
- **Phishing Section in Project Settings** — new `PhishingSection` component with SMTP configuration textarea for per-project email delivery settings
- **Tunnel Provider Dropdown** — replaced the single "Enable ngrok TCP Tunnel" toggle in Agent Behaviour settings with a **Tunnel Provider** dropdown (None / ngrok / chisel). Mutually exclusive — selecting one automatically disables the other
- **Social Engineering Suggestion Templates** — 15 new suggestion buttons in AI Assistant drawer under a pink "Social Engineering" template group (Mail icon), covering payload generation, malicious documents, web delivery, HTA, email phishing, AV evasion, and more
- **Phishing Attack Path Badge** — pink "PHISH" badge with `#ec4899` accent color for phishing sessions in the AI Assistant drawer
- **Prisma Migrations** — `20260228120000_add_ngrok_tunnel` (agentNgrokTunnelEnabled), `20260228130000_add_phishing_smtp_config` (phishingSmtpConfig), and `20260305145750_add_ip_mode` (ipMode, targetIps) database migrations
- **Remote Shells Tab** — new "Remote Shells" tab on the graph dashboard for real-time session management:
  - Unified view of all active Metasploit sessions (meterpreter, shell), background handlers/jobs, and non-MSF listeners (netcat, socat)
  - Sessions auto-detected from the Kali sandbox with 3-second polling and background cache refresh
  - Built-in interactive terminal with command history (arrow keys), session-aware prompts, and auto-scroll
  - Session actions: kill, upgrade shell to meterpreter, stop background jobs
  - Agent busy detection with lock-timeout strategy — session listing always works from cache, interaction retries when lock is available
  - Session-to-chat mapping — each session card shows which AI agent chat session created it
  - Non-MSF session registration when agent creates netcat/socat listeners via `kali_shell`
- **Command Whisperer** — AI-powered NLP-to-command translator in the Remote Shells terminal:
  - Natural language input bar (purple accent) above the terminal command line
  - Describe what you want in plain English → LLM generates the correct command for the current session type (meterpreter vs shell)
  - Uses the project's configured LLM (same model as the AI agent) via a new `/command-whisperer` API endpoint
  - Generated commands auto-fill the terminal input for review — no auto-execution
- **Metasploit Session Persistence** — removed automatic Metasploit restart on new conversations:
  - Removed `start_msf_prewarm` call from WebSocket initialization
  - Removed `sessions -K` soft-reset on first `metasploit_console` use
  - `msf_restart` tool now visible to the AI agent for manual use when a clean state is needed

### Changed

- **Model selector** — now passes `userId` to `/api/models` to fetch models from user-specific DB-stored providers
- **Agent orchestrator** — removed all env-var reads for AI provider keys; keys come exclusively from DB-stored user providers
- **`.env.example`** — stripped of all AI provider keys; now contains only infrastructure variables (NVD, tunneling, database)
- **Conflict detection** — IP-mode projects skip domain conflict checks entirely (tenant-scoped Neo4j constraints make IP overlap safe across projects). Domain-mode conflict detection unchanged
- **HTTP probe scope filtering** — `is_host_in_scope()` reordered to check `allowed_hosts` before `root_domain` scope, fixing IP-mode where the fake root domain caused all real hostnames to be filtered out. Added `input` URL fallback for redirect chains
- **GAU disabled in IP mode** — passive URL archives index by domain, not IP; GAU is automatically skipped when `ip_mode` is active
- **Domain ownership verification** skipped in IP mode — not applicable to IP-based targets
- **Session Config Prompt** — refactored to inject pre-configured payload settings (LHOST/LPORT/ngrok) BEFORE the attack chain workflow, so all attack paths (not just CVE exploit) see payload direction — previously injected only after CVE fallback
- **Agent prompts updated** — phishing, CVE exploit, and post-exploitation prompts now conditionally guide the agent based on which tunnel provider is active (ngrok limitations vs chisel capabilities)
- **Recon: HTTP Probe DNS Fallback** — now probes common non-standard HTTP ports (8080, 8000, 8888, 3000, 5000, 9000) and HTTPS ports (8443, 4443, 9443) when falling back to DNS-only target building, improving coverage when naabu port scan results are empty
- **Recon: Port Scanner SYN→CONNECT Retry** — when SYN scan completes but finds 0 open ports (firewall silently dropping SYN probes), automatically retries with CONNECT scan (full TCP handshake) which works through most firewalls
- **Wiki and documentation** — updated AI Agent Guide, Project Settings Reference, Attack Paths guide, and README with dual tunnel provider documentation

### Fixed

- **Duplicate port in https_ports set** — removed duplicate `443` and stale `8080` from `https_ports` in `build_targets_from_naabu()`

---

## [2.1.0] - 2026-02-27

### Added

- **CypherFix — Automated Vulnerability Remediation Pipeline** — end-to-end system that takes offensive findings from the Neo4j graph and turns them into merged code fixes:
  - **Triage Agent** (`cypherfix_triage/`): AI agent that queries the Neo4j knowledge graph, correlates hundreds of reconnaissance and exploitation findings, deduplicates them, ranks by exploitability and severity, and produces a prioritized remediation plan
  - **CodeFix Agent** (`cypherfix_codefix/`): autonomous code-repair agent that clones the target repository, navigates the codebase with 11 code-aware tools, implements targeted fixes for each triaged vulnerability, and opens a GitHub pull request ready for review and merge
  - Real-time WebSocket streaming for both Triage and CodeFix agents with dedicated hooks (`useCypherFixTriageWS`, `useCypherFixCodeFixWS`)
  - Remediations API (`/api/remediations/`) and hook (`useRemediations`) for persisting and retrieving remediation results
  - CypherFix API routes (`/api/cypherfix/`) for triggering and managing triage and codefix sessions
  - Agent-side API endpoints and orchestrator integration in `api.py` and `orchestrator.py`
- **CypherFix Tab on Graph Page** — new tab (`CypherFixTab/`) in the Graph dashboard providing a dedicated interface to launch triage, review prioritized findings, trigger code fixes, and monitor remediation progress
- **CypherFix Settings Section** — new `CypherFixSettingsSection` in Project Settings for configuring CypherFix parameters (GitHub repo, branch, AI model, triage/codefix behavior)
- **CypherFix Type System** (`cypherfix-types.ts`) — shared TypeScript types for triage results, codefix sessions, remediation records, and WebSocket message protocols
- **Agentic README Documentation** (`readmes/`) — internal documentation for the agentic module

### Changed

- **Global Header** — updated navigation to include CypherFix access point
- **View Tabs** — styling updates to accommodate the new CypherFix tab
- **Project Form** — expanded with CypherFix settings section and updated section exports
- **Hooks barrel export** — updated `hooks/index.ts` with new CypherFix and remediation hooks
- **Prisma Schema** — new fields for CypherFix configuration in the project model
- **Agent Requirements** — new Python dependencies for CypherFix agents
- **Docker Compose** — updated service configuration for CypherFix support
- **README** — version bump to v2.1.0, CypherFix badge added, pipeline description updated

---

## [2.0.0] - 2026-02-22

### Added

- **Project Export & Import** — full project portability via ZIP archives:
  - Export (`GET /api/projects/{id}/export`): streams a ZIP containing project settings, conversation history, Neo4j graph data (nodes + relationships with stable `_exportId` UUIDs), and recon/GVM/GitHub Hunt artifact files
  - Import (`POST /api/projects/import`): restores a project from ZIP under a specified user with domain/subdomain conflict validation, constraint-aware Neo4j import (MERGE for unique-constrained labels, CREATE for unconstrained via APOC), and conversation session ID deduplication
  - Import modal with drag-to-select file picker on the Projects page; Export button on Project Settings page
- **EvoGraph — Dynamic Attack Chain Visualization** — real-time evolutionary graph that updates as agent sessions progress with attack chains:
  - New `chain_graph_writer.py` module replacing the legacy `exploit_writer.py`
  - Five new Neo4j node types: `AttackChain` (session root), `ChainStep` (tool execution), `ChainFinding` (discovered vulnerability/credential/info), `ChainDecision` (phase transition), `ChainFailure` (error/dead-end)
  - Rich relationship model: `CHAIN_TARGETS`, `HAS_STEP`, `NEXT_STEP`, `LED_TO`, `DECISION_PRECEDED`, `PRODUCED`, `FAILED_WITH`, plus bridge relationships to the recon graph (`STEP_TARGETED`, `STEP_EXPLOITED`, `STEP_IDENTIFIED`, `FOUND_ON`, `FINDING_RELATES_CVE`)
  - Visual differentiation on the graph canvas: inactive session chains render grey (orange when selected), active session ring pulses yellow, chain flow particles are static grey
  - Cross-session awareness via `query_prior_chains()`: the agent knows what has already been tried in previous sessions
  - All graph writes are async fire-and-forget (never block the orchestrator loop)
- **Multi-Session System** — parallel attack sessions with full concurrency support:
  - Multiple independent agent sessions per project, each with its own WebSocket connection keyed by `user_id:project_id:session_id`
  - Per-session guidance queues and streaming callbacks (dicts keyed by `session_id`) preventing cross-session interference
  - Central task registry (`_active_tasks`) that survives WebSocket reconnection — agents keep running in the background when users disconnect or switch conversations
  - Connection replacement on reconnect: transfers running task, stop state, and guidance queue seamlessly
  - Metasploit prewarm per session key
- **Chat Persistence & Conversation History** — full message durability and session management:
  - Ordered `asyncio.Queue` + single background worker replacing fire-and-forget `asyncio.create_task()`, ensuring messages are saved with correct `sequenceNum`
  - All message types persisted: thinking, tool_start/complete (with raw output), phase updates, approval/question requests, responses, errors, todos
  - Conversation CRUD API routes: list, get with messages, lookup by session, update, delete
  - ConversationHistory panel in AI Assistant drawer with session title, status badge, phase indicator, iteration count, relative timestamps, and live "agent running" pulsing dot
  - Full state restoration when loading a conversation: chat items, todo lists, pending approval/question state, phase, iteration count
- **Per-Session Graph Controls** — granular visibility management for attack chains on the graph:
  - "Show only this session in graph" toggle button in AI drawer header
  - Sessions popup in the bottom bar with per-chain ON/OFF toggles, plus "All" / "None" bulk controls
  - Session badge showing `visible/total` count
  - Session title display (user's initial message truncated to 30 chars) instead of session ID codes
- **Data Table View** — alternative tabular visualization of the attack surface graph:
  - Graph Map / Data Table view tabs with Lucide icons
  - `@tanstack/react-table` powered table with columns: Type (color-coded), Name, Properties count, In/Out connections, L2/L3 hop counts
  - Global text filter, client-side sorting on all columns, row expansion with full property display
  - Pagination (10/25/50/100 per page) and XLSX Excel export
- **User Selector in Global Header** — switch between users directly from the top bar without navigating away, with two-letter avatar initials, dropdown user list, and "Manage Users" link
- **OpenAI-Compatible Provider** — fifth AI provider supporting any OpenAI API-compatible endpoint (Ollama, LM Studio, vLLM, local proxies) via `OPENAI_COMPAT_BASE_URL` and `OPENAI_COMPAT_API_KEY` env vars, with `openai_compat/` prefix convention for model detection
- **Hydra Brute Force Attack Path** — dedicated brute force attack path powered by THC Hydra, replacing Metasploit for credential-guessing operations with significantly higher performance. Supports 50+ protocols (SSH, FTP, RDP, SMB, MySQL, HTTP forms, and more) with configurable threads, timeouts, extra checks, and wordlist strategies. After credentials are discovered, the agent establishes access via `sshpass`, database clients, or protocol-specific tools
- **Unclassified Attack Paths** — agent orchestrator now supports attack paths that don't fit the CVE (MSF) or Hydra Brute Force categories, with dedicated prompts in `unclassified_prompts.py`
- **GitHub Wiki** — 13-page documentation wiki covering getting started, user management, project creation, graph dashboard, reconnaissance, GVM scanning, GitHub secret hunting, AI agent guide, project settings reference, AI model providers, attack surface graph, data export/import, and troubleshooting

### Changed

- **Agent Orchestrator** — major refactoring: per-session dictionaries for guidance queues and streaming callbacks, central task registry for connection-resilient background tasks, dynamic connection resolution via `ws_manager`
- **Graph Canvas** — new node types (ChainFinding, ChainDecision, ChainFailure) with distinct visual styling, session-aware coloring and particle rendering
- **Graph API** — expanded to return attack chain data with session-level grouping
- **PageBottomBar** — redesigned with session visibility controls, view-mode awareness, and session title display
- **UI Theme Hierarchy** — light mode background layers reorganized (white → gray-50 → gray-100 → gray-200 → gray-300), added `--bg-quaternary` token
- **Global Header** — navigation tabs (Projects/Red Zone) moved to right side, Graph Map/Data Table view tabs added, AI Agent button restyled to crimson, user selector added
- **Node Drawer** — styling improvements, new chain node type support
- **Target Section** — domain, subdomains, and root domain toggle locked in edit mode to prevent graph data inconsistency
- **README** — comprehensive rewrite reflecting v2.0 features

### Removed

- **`exploit_writer.py`** — replaced by `chain_graph_writer.py` with full EvoGraph support
- **`README.METASPLOIT.GUIDE.md`** — removed from agentic module

### Fixed

- **Race condition in chat message persistence** — fire-and-forget `asyncio.create_task()` caused messages to be saved with incorrect `sequenceNum`; replaced with ordered queue + single background worker
- **Race condition in concurrent sessions** — `_guidance_queue` and `_streaming_callback` were single instance variables overwritten by each new session; changed to per-session dictionaries keyed by `session_id`

---

## [1.3.0] - 2026-02-19

### Added

- **Multi-Provider LLM Support** — the agent now supports **4 AI providers** (OpenAI, Anthropic, OpenRouter, AWS Bedrock) with 400+ selectable models. Models are dynamically fetched from each provider's API and cached for 1 hour. Provider is auto-detected via a prefix convention (`openrouter/`, `bedrock/`, `claude-*`, or plain OpenAI)
- **Dynamic Model Selector** — replaced the hardcoded 11-model dropdown with a searchable, provider-grouped model picker in Project Settings. Type to filter across all providers instantly; each model shows name, context window, and pricing info
- **`GET /models` API Endpoint** — new agent endpoint that fetches available models from all configured providers in parallel. Proxied through the webapp at `/api/models`
- **`model_providers.py`** — new provider discovery module with async fetchers for OpenAI, Anthropic, OpenRouter, and AWS Bedrock APIs, with in-memory caching (1h TTL)
- **Stealth Mode** — new per-project toggle that forces the entire pipeline to use only passive and low-noise techniques:
  - Recon: disables Kiterunner and banner grabbing, switches Naabu to CONNECT scan with rate limiting, throttles httpx/Katana/Nuclei, disables DAST and interactsh callbacks
  - Agent: injects stealth rules into the system prompt — only passive/stealthy methods allowed, agent must refuse if stealth is impossible
  - GVM scanning disabled in stealth mode (generates ~50K active probes per target)
- **Stealth Mode UI** — toggle in Target section of Project Settings with description of what it does
- **Kali Sandbox Tooling Expansion** — 15+ new packages installed in the Kali container: `netcat`, `socat`, `rlwrap`, `exploitdb`, `john`, `smbclient`, `sqlmap`, `jq`, `gcc`, `g++`, `make`, `perl`, `go`
- **`kali_shell` MCP Tool** — direct Kali Linux shell command execution, available in all phases
- **`execute_code` MCP Tool** — run custom Python/Bash exploit scripts on the Kali sandbox
- **`msf_restart` MCP Tool** — restart Metasploit RPC daemon when it becomes unresponsive
- **`execute_nmap` MCP Tool** — deep service analysis, OS fingerprinting, NSE scripts (consolidated from previous naabu-only setup)
- **MCP Server Consolidation** — merged curl and naabu servers into a unified `network_recon_server.py`, added dedicated `nmap_server.py`, fixed tool loading race condition
- **Failure Loop Detection** — agent detects 3+ consecutive similar failures and injects a pivot warning to break out of unproductive loops
- **Prompt Token Optimization** — lazy no-module fallback injection (saves ~1.1K tokens), compact formatting for older execution trace steps (full output only for last 5), trimmed rarely-used wordlist tables
- **Metasploit Prewarm** — pre-initializes Metasploit console on agent startup to reduce first-use latency
- **Markdown Report Export** — download the full agent conversation as a formatted Markdown file
- **Hydra Brute Force & CVE (MSF) Settings** — new Project Settings sections for configuring Hydra brute force (threads, timeouts, extra checks, wordlist limits) and CVE exploit attack path parameters
- **Node.js Deserialization Guinea Pig** — new test environment for CVE-2017-5941 (node-serialize RCE)
- **Phase Tools Tooltip** — hover on phase badges to see which MCP tools are available in that phase
- **GitHub Secrets Suggestion** — new suggestion button in AI Assistant to leverage discovered GitHub secrets during exploitation

### Changed

- **Agent Orchestrator** — rewritten `_setup_llm()` with 4-way provider detection (OpenAI, Anthropic, OpenRouter via ChatOpenAI + custom base_url, Bedrock via ChatBedrockConverse with lazy import)
- **Model Display** — `formatModelDisplay()` helper cleans up prefixed model names in the AI Assistant badge and markdown export (e.g., `openrouter/meta-llama/llama-4-maverick` → `llama-4-maverick (OR)`)
- **Prompt Architecture** — tool registry extracted into dedicated `tool_registry.py`, attack path prompts (CVE exploit, brute force, post-exploitation) significantly reworked for better token efficiency and exploitation success rates
- **curl-based Exploitation** — expanded curl-based vulnerability probing and no-module fallback workflows for when Metasploit modules aren't available
- **kali_shell & execute_nuclei** — expanded to all phases (previously restricted)
- **GVM Button** — disabled in stealth mode with tooltip explaining why
- **README** — extensive updates: 4-provider documentation, AI Model Providers section, Kali sandbox tooling tables, new badges (400+ AI Models, Stealth Mode, Full Kill Chain, 30+ Security Tools, 9000+ Vuln Templates, 170K+ NVTs, 180+ Settings), version bump to v1.3.0

---

## [1.2.0] - 2026-02-13

### Added

- **GVM Vulnerability Scanning** — full end-to-end integration of Greenbone Vulnerability Management (GVM/OpenVAS) into the RedAmon pipeline:
  - Python scanner module (`gvm_scan/`) with `GVMScanner` class wrapping the GMP protocol for headless API-based scanning
  - Orchestrator endpoints (`/gvm/{id}/start`, `/gvm/{id}/status`, `/gvm/{id}/stop`, `/gvm/{id}/logs`) with SSE log streaming
  - Webapp API routes, `useGvmStatus` polling hook, `useGvmSSE` streaming hook, toolbar buttons, and log drawer on the Graph page
  - Neo4j graph integration — GVM findings stored as `Vulnerability` nodes (source="gvm") linked to IP/Subdomain via `HAS_VULNERABILITY`, with associated `CVE` nodes
  - JSON result download from the Graph page toolbar
- **GitHub Secret Hunt** — automated secret and credential detection across GitHub organizations and user repositories:
  - Python scanner module (`github_secret_hunt/`) with `GitHubSecretHunter` class supporting 40+ regex patterns for AWS, Azure, GCP, GitHub, Slack, Stripe, database connection strings, CI/CD tokens, cryptographic keys, JWT/Bearer tokens, and more
  - High-entropy string detection via Shannon entropy to catch unknown secret formats
  - Sensitive filename detection (`.env`, `.pem`, `.key`, credentials files, Kubernetes kubeconfig, Terraform tfvars, etc.)
  - Commit history scanning (configurable depth, default 100 commits) and gist scanning
  - Organization member repository enumeration with rate-limit handling and exponential backoff
  - Orchestrator endpoints (`/github-hunt/{id}/start`, `/github-hunt/{id}/status`, `/github-hunt/{id}/stop`, `/github-hunt/{id}/logs`) with SSE log streaming
  - Webapp API routes for start, status, stop, log streaming, and JSON result download
  - `useGithubHuntStatus` polling hook and `useGithubHuntSSE` streaming hook for real-time UI updates
  - Graph page toolbar integration with start/stop button, log drawer, and result download
  - JSON output with statistics (repos scanned, files scanned, commits scanned, gists scanned, secrets found, sensitive files, high-entropy findings)
- **GitHub Hunt Per-Project Settings** — GitHub scan configuration is now configurable per-project via the webapp UI:
  - New "GitHub" section in Project Settings with token, target org/user, and scan options
  - 7 configurable fields: Access Token, Target Organization, Scan Members, Scan Gists, Scan Commits, Max Commits, Output JSON
  - `github_secret_hunt/project_settings.py` mirrors the recon/GVM settings pattern (fetch from webapp API, fallback to defaults)
  - 7 new Prisma schema fields (`github_access_token`, `github_target_org`, `github_scan_members`, `github_scan_gists`, `github_scan_commits`, `github_max_commits`, `github_output_json`)
- **GVM Per-Project Settings** — GVM scan configuration is now configurable per-project via the webapp UI:
  - New "GVM Scan" tab in Project Settings (between Integrations and Agent Behaviour)
  - 5 configurable fields: Scan Profile, Scan Targets Strategy, Task Timeout, Poll Interval, Cleanup After Scan
  - `gvm_scan/project_settings.py` mirrors the recon/agentic settings pattern (fetch from webapp API, fallback to defaults)
  - Defaults served via orchestrator `/defaults` endpoint using `importlib` to avoid module name collision
  - 5 new Prisma schema fields (`gvm_scan_config`, `gvm_scan_targets`, `gvm_task_timeout`, `gvm_poll_interval`, `gvm_cleanup_after_scan`)

### Changed

- **Webapp Dockerfile** — embedded Prisma CLI in the production image; entrypoint now runs `prisma db push` automatically on startup, eliminating the separate `webapp-init` container
- **Dev Compose** — `docker-compose.dev.yml` now runs `prisma db push` before `npm run dev` to ensure schema is always in sync
- **Docker Compose** — removed `webapp-init` service and `webapp_prisma_cache` volume; webapp handles its own schema migration

### Removed

- **`webapp-init` service** — replaced by automatic migration in the webapp entrypoint (both production and dev modes)
- **`gvm_scan/params.py`** — hardcoded GVM settings replaced by per-project `project_settings.py`

---

## [1.1.0] - 2026-02-08

### Added

- **Attack Path System** — agent now supports dynamic attack path selection with two built-in paths:
  - **CVE (MSF)** — automated Metasploit module search, payload configuration, and exploit execution
  - **Hydra Brute Force** — THC Hydra-based credential guessing with configurable threads, timeouts, extra checks, and wordlist retry strategies
- **Agent Guidance** — send real-time steering messages to the agent while it works, injected into the system prompt before the next reasoning step
- **Agent Stop & Resume** — stop the agent at any point and resume from the last LangGraph checkpoint with full context preserved
- **Project Creation UI** — full frontend project form with all configurable settings sections:
  - Naabu (port scanner), Httpx (HTTP prober), Katana (web crawler), GAU (passive URLs), Kiterunner (API discovery), Nuclei (vulnerability scanner), and agent behavior settings
- **Agent Settings in Frontend** — transferred agent configuration parameters from hardcoded `params.py` to PostgreSQL, editable via webapp UI
- **Metasploit Progress Streaming** — HTTP progress endpoint (port 8013) for real-time MSF command tracking with ANSI escape code cleaning
- **Metasploit Session Auto-Reset** — `msf_restart()` MCP tool for clean msfconsole state; auto-reset on first use per chat session
- **WebSocket Integration** — real-time bidirectional communication between frontend and agent orchestrator
- **Markdown Chat UI** — react-markdown with syntax highlighting for agent chat messages
- **Smart Auto-Scroll** — chat only auto-scrolls when user is at the bottom of the conversation
- **Connection Status Indicator** — color-coded WebSocket connection status (green/red) in the chat interface

### Changed

- **Unified Docker Compose** — replaced per-module `.env` files and `start.sh`/`stop.sh` scripts with a single root `docker-compose.yml` and `docker-compose.dev.yml` for full-stack orchestration
- **Settings Source of Truth** — migrated all recon and agent settings from hardcoded `params.py` to PostgreSQL via Prisma ORM, fetched at runtime via webapp API
- **Recon Pipeline Improvements** — multi-level improvements across all recon modules for reliability and accuracy
- **Orchestrator Model Selection** — fixed model selection logic in the agent orchestrator
- **Frontend Usability** — unified RedAmon primary crimson color (#d32f2f), styled message containers with ghost icons and gradient backgrounds, improved markdown heading and list spacing
- **Environment Configuration** — added root `.env.example` with all required keys; forwarded NVD_API_KEY and Neo4j credentials from recon-orchestrator to spawned containers
- **Webapp Header** — replaced Crosshair icon with custom logo.png image, bumped logo text size

### Fixed

- **Double Approval Dialog** — fixed duplicate approval confirmation with ref-based state tracking
- **Orchestrator Model Selection** — corrected model selection logic when switching between AI providers

---

## [1.0.0] - Initial Release

### Added

- Automated reconnaissance pipeline (6-phase: domain discovery, port scanning, HTTP probing, resource enumeration, vulnerability scanning, MITRE mapping)
- Neo4j graph database with 17 node types and 20+ relationship types
- MCP tool servers (Naabu, Curl, Nuclei, Metasploit)
- LangGraph-based AI agent with ReAct pattern
- Next.js webapp with graph visualization (2D/3D)
- Recon orchestrator with SSE log streaming
- GVM scanner integration (under development)
- Test environments (Apache CVE containers)
