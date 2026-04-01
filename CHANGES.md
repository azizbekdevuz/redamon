# RedAmon — PR Change Log

## Features Added

### 1. Claude Code Integration (No API Key Required)

#### Overview
Claude Code CLI is integrated into RedAmon in two complementary ways:
- **As a pentest analysis tool** — the AI agent can call `claude_code` during a pentest session to analyze source code, hunt for secrets, review configs, and inspect JS bundles for exposed endpoints.
- **As the LLM provider** — Claude Code can replace OpenAI/Anthropic as the underlying LLM that drives the entire pentest agent, using your existing Claude Code login session instead of an API key.

Both modes work via a lightweight **host proxy** (`claude_proxy/server.py`) that runs on the developer's machine and exposes an OpenAI-compatible HTTP API. The Docker containers call `http://host.docker.internal:8099` — the proxy runs `claude --print` using the host's authenticated Claude Code session (macOS Keychain OAuth), so no API key is ever needed.

---

#### 1a. Claude Code Host Proxy

**New file: `claude_proxy/server.py`**

FastAPI server running on the host machine at port 8099.

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness probe |
| `POST /claude` | Tool-use endpoint — runs `claude --print <task>` |
| `GET /v1/models` | OpenAI-compatible model list (5 Claude models) |
| `POST /v1/chat/completions` | OpenAI-compatible chat completions (streaming + non-streaming) |

- Converts OpenAI messages arrays into a single structured prompt for `claude --print`
- Supports SSE streaming responses
- Model IDs are prefixed `claude-code/` (e.g. `claude-code/claude-opus-4-6`)

**`redamon.sh`** — Two new commands:
```sh
./redamon.sh start-claude-proxy   # Start proxy on port 8099
./redamon.sh stop-claude-proxy    # Stop proxy
```

---

#### 1b. Claude Code as a Pentest Tool

**`agentic/tools.py`**
- Added `ClaudeCodeToolManager` class — calls the host proxy via `httpx`, does not run `claude` subprocess directly inside the container
- `get_tool()` checks proxy reachability before registering the tool (graceful disable if proxy is down)
- Tool is added to `DANGEROUS_TOOLS` (requires human confirmation before each call)

**`agentic/project_settings.py`**
- `DANGEROUS_TOOLS`: added `claude_code`
- `TOOL_PHASE_MAP`: `claude_code` enabled in all three phases (`informational`, `exploitation`, `post_exploitation`)
- `DEFAULT_AGENT_SETTINGS`: added `CLAUDE_CODE_ENABLED: False` and `CLAUDE_CODE_PATH: 'claude'`
- `fetch_agent_settings()`: maps `agentClaudeCodeEnabled` and `agentClaudeCodePath` from DB

**`agentic/orchestrator.py`**
- Imports `ClaudeCodeToolManager`
- `_setup_tools()`: instantiates manager, passes tool to `PhaseAwareToolExecutor`
- `_apply_project_settings()`: respects `CLAUDE_CODE_ENABLED` flag, enables/disables tool per project

**`agentic/Dockerfile`**
- Added `@anthropic-ai/claude-code` to global npm install so the binary is available inside the container

**`docker-compose.yml`** (agent service)
- Volume mounts: `~/.claude:/root/.claude:rw` and `~/.claude.json:/root/.claude.json:rw`
- Environment pass-through: `ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}`

**`webapp/prisma/schema.prisma`** (`Project` model)
```prisma
agentClaudeCodeEnabled  Boolean @default(false) @map("agent_claude_code_enabled")
agentClaudeCodePath     String  @default("claude") @map("agent_claude_code_path")
```

**`webapp/src/components/projects/ProjectForm/sections/AgentBehaviourSection.tsx`**
- Added **"Claude Code — AI Code Analysis"** subsection under Agent Behaviour
- Toggle: `agentClaudeCodeEnabled`
- Input (shown when enabled): `agentClaudeCodePath` — path to `claude` binary

---

#### 1c. Claude Code as the LLM Provider

**`webapp/src/lib/llmProviderPresets.ts`**
- Added `claude_code` to `PROVIDER_TYPES`:
  ```ts
  { id: 'claude_code', name: 'Claude Code', description: 'Use Claude models via Claude Code login — no API key needed', icon: '🤖' }
  ```

**`webapp/src/components/settings/LlmProviderForm.tsx`**
- Added Claude Code config section in the provider form:
  - Model dropdown (5 pre-populated Claude models with `claude-code/` prefix)
  - Proxy URL field (pre-filled: `http://host.docker.internal:8099`)
  - Hint linking to `./redamon.sh start-claude-proxy`
- `selectType()` auto-populates `modelIdentifier` and `baseUrl` defaults when Claude Code is selected (prevents save button staying disabled)
- Save button condition updated — no API key required for `claude_code` type

**`agentic/model_providers.py`**
- Added `fetch_claude_code_models()` — queries proxy `/v1/models`, falls back to a static list of 5 models if the proxy is unreachable
- `fetch_all_models()`: handles `claude_code` provider type, calls `fetch_claude_code_models()`

**`agentic/orchestrator_helpers/llm_setup.py`**
- `parse_model_provider()`: detects `claude-code/` prefix → returns `("claude_code", model)`
- `setup_llm()`: new `claude_code` case — routes to `ChatOpenAI` pointing at `http://host.docker.internal:8099/v1`; uses `"claude-code"` as placeholder API key (proxy ignores it)
- **Auto-fallback**: if a project is configured with e.g. `claude-opus-4-6` but no Anthropic API key is set, the agent automatically falls back to `claude-code/claude-opus-4-6` via the proxy and logs a warning

**`agentic/project_settings.py`**
- When model starts with `claude-code/`, looks up the user's `claude_code` provider config and sets it as `CUSTOM_LLM_CONFIG` (so the custom proxy URL is respected)

**`agentic/api.py`**
- `test_llm_provider()` endpoint: added `claude_code` case — tests connectivity to the proxy and sends a simple message

---

### 2. Censys Personal API Token

#### Overview
Censys offers two authentication methods:
1. **API ID + Secret** (existing) — HTTP Basic Auth for the Censys Search API
2. **Personal API Token** (new) — Bearer token, generated from `https://accounts.censys.io/settings/personal-access-tokens`

The Personal API Token is now supported as a simpler alternative. When both are configured, the token takes precedence.

---

**`webapp/prisma/schema.prisma`** (`UserSettings` model)
```prisma
censysApiToken  String  @default("") @map("censys_api_token")
```

**`webapp/src/app/api/users/[id]/settings/route.ts`**
- `censysApiToken` added to GET (empty default + masked response), PUT (fields list + masked response)

**`webapp/src/app/settings/page.tsx`**
- `UserSettings` interface: added `censysApiToken`
- `EMPTY_SETTINGS`: added `censysApiToken: ''`
- `fetchSettings` / save handler: maps `censysApiToken`
- UI: new `SecretField` **"Censys Personal API Token"** placed below "Censys API Secret"
  - Link: `https://accounts.censys.io/settings/personal-access-tokens`
  - Hint: "Alternative to API ID + Secret. Takes precedence when both are set."
  - Badges: `['AI Agent', 'Recon Pipeline']`

**`recon/project_settings.py`**
- `DEFAULT_SETTINGS`: added `CENSYS_API_TOKEN: ''`
- `fetch_agent_settings()`: maps `CENSYS_API_TOKEN` ← `censysApiToken`

**`recon/censys_enrich.py`**
- `_censys_get_host()`: new `api_token` parameter — uses `Authorization: Bearer <token>` when set, falls back to `auth=(api_id, api_secret)`
- `run_censys_enrichment()`: reads `CENSYS_API_TOKEN`; credential check passes if token alone OR ID+Secret pair is present
- `run_censys_enrichment_isolated()`: inherits token support

**`agentic/tools.py`** (`CensysToolManager`)
- `__init__()`: new `api_token` parameter
- `get_tool()`: accepts token alone (no ID+Secret needed) to activate the tool
- Inside the tool: Bearer auth when token is set, Basic auth otherwise

**`agentic/orchestrator.py`**
- `_osint_key_map` for `censys`: added `token_field: 'censysApiToken'`
- `_apply_project_settings()`: reads `censysApiToken`, sets `mgr.api_token`, triggers tool update on any credential change

---

### 3. Jhaddix All.txt Wordlist for Amass Brute Force

#### Overview
The [jhaddix all.txt](https://gist.github.com/jhaddix/86a06c5dc309d08580a018c66354a056) subdomain wordlist (~2.18M entries) is now permanently baked into the `redamon-recon` Docker image and automatically used when Amass brute-force mode is enabled.

**`recon/Dockerfile`**
- Added `curl` step to download `jhaddix-all.txt` to `/app/recon/wordlists/jhaddix-all.txt` at build time

**`recon/domain_recon.py`**
- `run_amass()`: when brute mode is enabled, derives the host-side recon path from `HOST_RECON_OUTPUT_PATH` env var, bind-mounts the wordlist into the Amass container, and passes `-w /wordlist/jhaddix-all.txt` to Amass
- Falls back to Amass built-in list with a warning if wordlist file is not found (e.g. older image)
- Added `import os` to imports

---

### 4. Infosec-skills-Compatible Specialist Skills

#### Overview
The agent's system prompt can now be enriched with specialist knowledge packages, fully compatible with the [Infosec-skills skills system](https://github.com/useinfosec-skills/infosec-skills). Up to 5 skills can be active per session. Skills are stored as markdown files and dynamically injected into the LLM's system prompt.

**Skill categories available:**

| Category | Skills |
|---|---|
| **tooling** | ffuf, httpx, katana, naabu, nmap, nuclei, semgrep, sqlmap, subfinder |
| **vulnerabilities** | authentication_jwt, broken_function_level_authorization, business_logic, csrf, idor, information_disclosure, insecure_file_uploads, mass_assignment, open_redirect, path_traversal_lfi_rfi, race_conditions, rce, sql_injection, ssrf, subdomain_takeover, xss, xxe |
| **scan_modes** | quick, deep, standard |
| **frameworks** | fastapi, nestjs, nextjs |
| **technologies** | firebase_firestore, supabase |
| **protocols** | graphql |
| **coordination** | root_agent |

**`agentic/skills/`** — New directory
- 36 markdown skill files organized by category, sourced from Infosec-skills

**`agentic/skill_loader.py`** — New file
- `list_skills()` — discovers all `.md` skill files, parses YAML frontmatter, returns metadata catalog
- `load_skill_content(skill_id)` — loads a single skill's full content by ID
- `build_skills_prompt_section(skill_ids)` — builds the `## SPECIALIST SKILLS` system prompt section for up to 5 enabled skills

**`agentic/project_settings.py`**
- `DEFAULT_AGENT_SETTINGS`: added `AGENT_SKILLS: []`
- `fetch_agent_settings()`: maps `agentSkills` from DB

**`agentic/orchestrator_helpers/nodes/think_node.py`**
- Imports `build_skills_prompt_section` from `skill_loader`
- After the RoE injection block: reads `AGENT_SKILLS` setting and appends the skills section to the system prompt when any skills are enabled

**`agentic/api.py`**
- Added `GET /skills` endpoint — returns the full skill catalog (id, name, description, category) for the webapp's skill selector UI

**`webapp/prisma/schema.prisma`** (`Project` model)
```prisma
agentSkills  Json  @default("[]")  @map("agent_skills")
```

**`webapp/src/app/api/skills/route.ts`** — New file
- Proxies `GET /api/skills` to the agentic service's `/skills` endpoint
- Returns empty list if agent is unreachable (graceful degradation)

**`webapp/src/components/projects/ProjectForm/sections/AgentBehaviourSection.tsx`**
- Added **"Specialist Skills"** subsection under Agent Behaviour
- Fetches skill catalog from `/api/skills` on mount
- Renders skills as toggle-pill buttons grouped by category
- Enforces 5-skill maximum (excess pills become disabled with `cursor: not-allowed`)
- Shows active count: "N/5 skills active"

---

### 5. Bug Fixes

#### ngrok Download URL (kali-sandbox)
**`mcp/kali-sandbox/Dockerfile`**
- Fixed broken ngrok download URL (the old `bin.equinox.io` URL returned exit 2)
- Switched to the official ngrok APT repository with `|| echo "[WARN]..."` fallback so the build doesn't fail if ngrok is unavailable

#### Claude Code Proxy Missing Entrypoint
**`claude_proxy/server.py`**
- Added `if __name__ == "__main__": uvicorn.run(...)` — the proxy was silently exiting when started via `python3 server.py` because there was no server startup code

---

## Files Changed

| File | Change Type | Description |
|---|---|---|
| `claude_proxy/server.py` | **New** | Claude Code host proxy (FastAPI, OpenAI-compatible API) |
| `agentic/Dockerfile` | Modified | Add `@anthropic-ai/claude-code` npm package |
| `agentic/tools.py` | Modified | `ClaudeCodeToolManager` + `CensysToolManager` token auth |
| `agentic/orchestrator.py` | Modified | Claude Code tool setup + Censys token handling |
| `agentic/project_settings.py` | Modified | `CLAUDE_CODE_ENABLED`, `CLAUDE_CODE_PATH`, `AGENT_SKILLS`, `claude-code/` model routing |
| `agentic/model_providers.py` | Modified | `fetch_claude_code_models()` + `claude_code` in aggregator |
| `agentic/orchestrator_helpers/llm_setup.py` | Modified | `claude_code` provider + auto-fallback logic |
| `agentic/orchestrator_helpers/nodes/think_node.py` | Modified | Infosec-skills skills injection into system prompt |
| `agentic/api.py` | Modified | `claude_code` test case + `GET /skills` endpoint |
| `agentic/skill_loader.py` | **New** | Skill discovery, content loading, prompt injection |
| `agentic/skills/` | **New** | 36 Infosec-skills-compatible skill markdown files (7 categories) |
| `recon/Dockerfile` | Modified | Bake in jhaddix all.txt wordlist at build time |
| `recon/domain_recon.py` | Modified | Mount + pass jhaddix wordlist to Amass brute force |
| `recon/censys_enrich.py` | Modified | Bearer token auth support |
| `recon/project_settings.py` | Modified | `CENSYS_API_TOKEN` setting |
| `redamon.sh` | Modified | `start-claude-proxy` / `stop-claude-proxy` commands |
| `docker-compose.yml` | Modified | `~/.claude` volume mounts + `ANTHROPIC_API_KEY` env pass-through |
| `mcp/kali-sandbox/Dockerfile` | Modified | Fixed ngrok APT repo install |
| `webapp/prisma/schema.prisma` | Modified | `agentClaudeCodeEnabled`, `agentClaudeCodePath`, `agentSkills`, `censysApiToken` fields |
| `webapp/src/app/api/users/[id]/settings/route.ts` | Modified | `censysApiToken` field handling |
| `webapp/src/app/api/skills/route.ts` | **New** | Proxy to agentic `/skills` endpoint |
| `webapp/src/app/settings/page.tsx` | Modified | Censys Personal API Token UI field |
| `webapp/src/components/projects/ProjectForm/sections/AgentBehaviourSection.tsx` | Modified | Claude Code toggle + Specialist Skills selector UI |
| `webapp/src/components/settings/LlmProviderForm.tsx` | Modified | Claude Code provider config UI |
| `webapp/src/lib/llmProviderPresets.ts` | Modified | `claude_code` provider type |

---

## Database Migrations

No manual migration needed. The webapp container runs `prisma db push` automatically on startup.

New columns added to PostgreSQL:

| Table | Column | Type | Default |
|---|---|---|---|
| `projects` | `agent_claude_code_enabled` | `BOOLEAN` | `false` |
| `projects` | `agent_claude_code_path` | `VARCHAR` | `'claude'` |
| `projects` | `agent_skills` | `JSONB` | `'[]'` |
| `user_settings` | `censys_api_token` | `VARCHAR` | `''` |

---

## Usage Guide

### Using Claude Code as the AI Agent's LLM

1. Start the host proxy (one-time, keep running):
   ```sh
   ./redamon.sh start-claude-proxy
   ```

2. In RedAmon → **Global Settings** → **LLM Providers** → **Add Provider**
   - Select **Claude Code 🤖**
   - Model and proxy URL are pre-filled
   - Click **Save Provider**

3. In your project → **AI Agent** tab → **Agent Behaviour**
   - Open the **LLM Model** dropdown
   - Select any `Claude Code (via Claude Code)` model

> **No API key required.** The proxy uses your existing `claude login` session.
>
> **Auto-fallback:** If a project has `claude-opus-4-6` selected but no Anthropic API key, the agent automatically switches to `claude-code/claude-opus-4-6` via the proxy.

---

### Using Claude Code as a Pentest Analysis Tool

1. Start the host proxy (same as above)

2. In your project → **AI Agent** tab → **Agent Behaviour** → scroll to **"Claude Code — AI Code Analysis"**
   - Toggle **Enable Claude Code** on

3. During a pentest, the agent can now call `claude_code(task=...)` to:
   - Analyze discovered source code for vulnerabilities
   - Hunt for hardcoded secrets and API keys
   - Review configuration files
   - Inspect JS bundles for exposed internal endpoints

> Tool confirmation is always enforced for `claude_code` calls (part of `DANGEROUS_TOOLS`).

---

### Using Specialist Skills

1. In your project → **AI Agent** tab → **Agent Behaviour** → scroll to **"Specialist Skills"**

2. Click skill pills to toggle them on/off (max 5 active at a time):
   - **Vulnerability skills** — deep expertise on SSRF, XSS, SQLi, IDOR, JWT, RCE, etc.
   - **Tooling skills** — exact CLI playbooks for Nuclei, Nmap, Naabu, ffuf, sqlmap, etc.
   - **Scan mode skills** — `quick` (time-boxed high-impact), `standard`, `deep`
   - **Framework skills** — FastAPI, Next.js, NestJS security patterns
   - **Technology skills** — Supabase, Firebase Firestore attack surfaces
   - **Protocol skills** — GraphQL attack surface

3. The selected skills are injected into the agent's system prompt under a `## SPECIALIST SKILLS` section at the start of every iteration.

> The agent automatically applies skill expertise when relevant — no explicit prompting needed.

---

### Using the Jhaddix Wordlist for Amass Brute Force

The wordlist is automatically used when **Amass** is configured in brute force mode. No manual configuration needed — it's baked into the `redamon-recon` image.

To enable brute force in the Recon Pipeline settings, toggle **"Brute Force Subdomain Enumeration"** on in your project's Recon settings.

---

### Censys Personal API Token

1. Generate a token at: `https://accounts.censys.io/settings/personal-access-tokens`

2. In RedAmon → **Global Settings** → **API Keys & Tunneling**
   - Enter the token in **"Censys Personal API Token"**
   - The existing API ID + Secret fields remain supported
   - If both are configured, the token takes precedence
