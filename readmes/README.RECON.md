# RedAmon Reconnaissance Module

**Unmask the hidden before the world does.**

An automated OSINT reconnaissance and vulnerability scanning framework combining multiple security tools for comprehensive target assessment.

---

## Table of Contents

- [Quick Start](#-docker-quick-start-recommended)
- [Architecture](#-docker-in-docker-architecture)
- [Pipeline Overview](#-scanning-pipeline-overview)
- [Scan Modules](#-scan-modules-explained)
- [Tool Comparison](#-complete-tool-comparison)
- [Configuration](#-key-configuration-parameters)
- [Prerequisites](#-prerequisites)
- [Project Structure](#-project-structure)
- [Output Format](#-output-format)
- [Test Targets](#-test-targets)

---

## 🐳 Docker Quick Start (Recommended)

The recon module is fully containerized. All tools run inside Docker containers.

### Option 1: Start from Webapp (Recommended)

The easiest way to run recon is through the webapp UI, which provides:
- Real-time log streaming
- Phase progress tracking
- Project-specific settings from PostgreSQL
- Automatic Neo4j graph updates

```bash
# 1. Start all services
cd postgres_db && docker-compose up -d
cd ../graph_db && docker-compose up -d
cd ../recon_orchestrator && docker-compose up -d
cd ../webapp && npm run dev

# 2. Open http://localhost:3000/graph
# 3. Click "Start Recon" button
```

### Option 2: CLI with Environment Variables

For standalone CLI usage without the webapp:

```bash
# 1. Build the container (first time only)
cd recon/
docker-compose build

# 2. Run a scan with target specified via environment variable
TARGET_DOMAIN=testphp.vulnweb.com docker-compose run --rm recon python /app/recon/main.py
```

### Docker Environment Variables

Override default settings via environment variables:

```bash
# Run with custom target
TARGET_DOMAIN=example.com docker-compose run --rm recon python /app/recon/main.py

# Run with Tor anonymity
USE_TOR_FOR_RECON=true docker-compose run --rm recon python /app/recon/main.py

# Run specific modules only
SCAN_MODULES="domain_discovery,port_scan,http_probe" docker-compose run --rm recon python /app/recon/main.py
```

### When to Rebuild

| Change Type | Action Required |
|-------------|-----------------|
| Python code (*.py) changes | `docker-compose build` |
| `requirements.txt` changes | `docker-compose build --no-cache` |
| `Dockerfile` changes | `docker-compose build --no-cache` |
| `.env` file changes | No rebuild needed (mounted as volume) |

---

## 🔗 Recon Orchestrator Integration

When started from the webapp, the recon module is managed by the **Recon Orchestrator** service, which provides:

- **Container Lifecycle Management** - Start/stop/monitor recon containers
- **Real-time Log Streaming** - SSE-based log streaming to the frontend
- **Phase Detection** - Automatic detection of scan phases from log output
- **Status Tracking** - Track running/completed/error states per project

### Configuration Hierarchy

Settings are resolved in the following order of precedence:

1. **Webapp API (Primary)** - When `PROJECT_ID` and `WEBAPP_API_URL` environment variables are set:
   ```bash
   # Set by recon orchestrator when starting container
   PROJECT_ID=cml6xov4q0002h58pln96n20d
   WEBAPP_API_URL=http://localhost:3000
   ```
   The recon module fetches all 169+ configurable parameters from:
   ```
   GET /api/projects/{projectId}
   ```

2. **Environment Variables** - Override individual settings:
   ```bash
   TARGET_DOMAIN=example.com docker-compose run --rm recon python /app/recon/main.py
   ```

3. **DEFAULT_SETTINGS (Fallback)** - Built-in defaults in `project_settings.py` for CLI usage without webapp

### project_settings.py

The `project_settings.py` module handles settings resolution:

```python
from recon.project_settings import get_settings

# Returns dict with all settings from API or DEFAULT_SETTINGS fallback
settings = get_settings()

TARGET_DOMAIN = settings['TARGET_DOMAIN']
SUBDOMAIN_LIST = settings['SUBDOMAIN_LIST']
SCAN_MODULES = settings['SCAN_MODULES']
# ... all 169+ parameters
```

### Orchestrator Communication Flow

```mermaid
sequenceDiagram
    participant Webapp as Webapp UI
    participant Orchestrator as Recon Orchestrator
    participant Recon as Recon Container
    participant API as Webapp API
    participant Neo4j as Neo4j

    Webapp->>Orchestrator: POST /recon/{projectId}/start
    Orchestrator->>Recon: docker run with PROJECT_ID, WEBAPP_API_URL
    Recon->>API: GET /api/projects/{projectId}
    API-->>Recon: Project settings (169+ params)
    Recon->>Recon: Execute scan pipeline
    Recon->>Neo4j: Update graph with results
    Orchestrator->>Webapp: SSE log stream
    Recon-->>Orchestrator: Container exits
    Orchestrator->>Webapp: Complete event
```

---

## 🏗️ Docker-in-Docker Architecture

The recon module uses a **Docker-in-Docker (DinD)** pattern where the main recon container orchestrates sibling containers for each scanning tool.

### How It Works

The recon container shares the **host's Docker daemon** via a socket mount, meaning all containers are **siblings** managed by the same host Docker daemon.

```mermaid
flowchart TB
    subgraph Host["🖥️ HOST MACHINE"]
        subgraph DockerDaemon["Docker Daemon (dockerd)"]
            Socket["/var/run/docker.sock"]
        end

        subgraph Containers["Sibling Containers"]
            Recon["redamon-recon<br/>Python Orchestrator<br/>📋 Coordinates all scans"]
            NaabuC["naabu<br/>projectdiscovery/naabu<br/>🔌 Port Scanner"]
            HttpxC["httpx<br/>projectdiscovery/httpx<br/>🌐 HTTP Prober"]
            NucleiC["nuclei<br/>projectdiscovery/nuclei<br/>🎯 Vuln Scanner"]
            KatanaC["katana<br/>projectdiscovery/katana<br/>🕸️ Web Crawler"]
            GAUC["gau<br/>sxcurity/gau<br/>📚 URL Archives"]
        end

        Volume["📁 Shared Volume<br/>recon/output/"]
    end

    Socket -.->|socket mount| Recon
    Recon -->|docker run| NaabuC
    Recon -->|docker run| HttpxC
    Recon -->|docker run| NucleiC
    Recon -->|docker run| KatanaC
    Recon -->|docker run| GAUC

    NaabuC --> Volume
    HttpxC --> Volume
    NucleiC --> Volume
    KatanaC --> Volume
    GAUC --> Volume
    Recon --> Volume
```

### Container Execution Flow

```mermaid
sequenceDiagram
    participant User
    participant Recon as redamon-recon
    participant Docker as Docker Daemon
    participant Naabu as naabu container
    participant Httpx as httpx container
    participant Katana as katana container
    participant GAU as gau container
    participant Nuclei as nuclei container

    User->>Recon: docker-compose run recon python main.py
    activate Recon

    Note over Recon: Phase 1: Domain Discovery (Python native)
    Recon->>Recon: WHOIS lookup
    Recon->>Recon: crt.sh + HackerTarget API
    Recon->>Recon: DNS resolution

    Note over Recon: Phase 1b: OSINT Enrichment (Python native)
    Recon->>Recon: Shodan enrichment (if enabled)
    Recon->>Recon: URLScan.io enrichment (if enabled)
    Recon->>Recon: External domain aggregation

    Note over Recon,Naabu: Phase 2: Port Scan
    Recon->>Docker: docker run projectdiscovery/naabu
    Docker->>Naabu: Start container
    activate Naabu
    Naabu->>Naabu: SYN scan targets
    Naabu-->>Recon: JSON output (open ports)
    deactivate Naabu

    Note over Recon,Httpx: Phase 3: HTTP Probe
    Recon->>Docker: docker run projectdiscovery/httpx
    Docker->>Httpx: Start container
    activate Httpx
    Httpx->>Httpx: Probe HTTP/HTTPS
    Httpx->>Httpx: Detect technologies
    Httpx-->>Recon: JSON output (live URLs)
    deactivate Httpx

    Note over Recon,GAU: Phase 4: Resource Enumeration
    Recon->>Docker: docker run projectdiscovery/katana
    Docker->>Katana: Start container
    activate Katana
    Katana->>Katana: Crawl live URLs
    Katana-->>Recon: JSON output (endpoints)
    deactivate Katana
    Recon->>Docker: docker run sxcurity/gau
    Docker->>GAU: Start container
    activate GAU
    GAU->>GAU: Fetch archived URLs
    GAU-->>Recon: JSON output (historical URLs)
    deactivate GAU
    Recon->>Recon: Merge & classify endpoints

    Note over Recon,Nuclei: Phase 5: Vuln Scan
    Recon->>Docker: docker run projectdiscovery/nuclei
    Docker->>Nuclei: Start container
    activate Nuclei
    Nuclei->>Nuclei: Run 9000+ templates
    Nuclei-->>Recon: JSON output (vulns)
    deactivate Nuclei

    Recon->>Recon: Save recon_domain.json
    Recon-->>User: Scan complete
    deactivate Recon
```

### Why Docker-in-Docker?

| Benefit | Description |
|---------|-------------|
| **Isolation** | Each tool runs in its own container with minimal dependencies |
| **Consistency** | Same tool versions regardless of host OS |
| **No host pollution** | Go binaries (naabu, httpx, nuclei) don't need to be installed on host |
| **Easy updates** | Just pull new Docker images to update tools |
| **Portability** | Works on any system with Docker installed |

---

## 🔄 Scanning Pipeline Overview

RedAmon executes scans in a modular pipeline. Each module adds data to a single JSON output file.

### High-Level Pipeline

```mermaid
flowchart LR
    subgraph Input["📥 Input"]
        Domain[🌐 Target Domain]
    end

    subgraph Pipeline["🔄 Recon Pipeline"]
        DD[1️⃣ domain_discovery<br/>WHOIS + Subdomains + DNS]
        OSINT[1b️ osint_enrichment<br/>Shodan + URLScan]
        PS[2️⃣ port_scan<br/>Naabu]
        HP[3️⃣ http_probe<br/>Httpx + Wappalyzer]
        RE[4️⃣ resource_enum<br/>Katana + GAU]
        VS[5️⃣ vuln_scan<br/>Nuclei + MITRE]
        GH[6️⃣ github<br/>Secret Hunting]
    end

    subgraph Output["📤 Output"]
        JSON[(recon_domain.json)]
        Graph[(Neo4j Graph)]
    end

    Domain --> DD
    DD --> OSINT
    OSINT --> PS
    PS --> HP
    HP --> RE
    RE --> VS
    VS --> GH
    GH --> JSON
    JSON --> Graph
```

### Detailed Module Flow

```mermaid
flowchart TB
    subgraph Phase1["Phase 1: Domain Discovery"]
        direction TB
        Start([🌐 TARGET_DOMAIN]) --> WHOIS[WHOIS Lookup<br/>Registrar, dates, contacts]
        WHOIS --> SubD[Subdomain Discovery]

        subgraph SubSources["Subdomain Sources"]
            CRT[crt.sh<br/>Certificate Transparency]
            HT[HackerTarget API<br/>DNS records]
            Knock[Knockpy<br/>Bruteforce]
        end

        SubD --> CRT
        SubD --> HT
        SubD --> Knock

        CRT --> Merge[Merge & Dedupe]
        HT --> Merge
        Knock --> Merge

        Merge --> DNS[DNS Resolution<br/>A, AAAA, MX, NS, TXT, CNAME]
        DNS --> Out1[(Subdomains + IPs)]
    end

    subgraph Phase1b["Phase 1b: OSINT Enrichment"]
        direction TB
        Out1 --> ShodanE[Shodan Enrichment<br/>Host, DNS, CVEs]
        Out1 --> URLScanE[URLScan.io Enrichment<br/>Historical scans]
        ShodanE --> ExtAgg[Aggregate External Domains]
        URLScanE --> ExtAgg
        ExtAgg --> Out1b[(Enriched IPs + ExternalDomains)]
    end

    subgraph Phase2["Phase 2: Port Scanning"]
        direction TB
        Out1b --> Naabu[Naabu Port Scanner]

        subgraph NaabuOpts["Scan Options"]
            SYN[SYN Scan<br/>Fast, requires root]
            Connect[CONNECT Scan<br/>Slower, no root needed]
            Passive[Shodan InternetDB<br/>No packets sent]
        end

        Naabu --> SYN
        Naabu --> Connect
        Naabu -.-> Passive

        SYN --> CDN{CDN Detected?}
        Connect --> CDN
        Passive --> CDN

        CDN -->|Yes| Skip[Skip CDN IPs]
        CDN -->|No| Out2[(Open Ports + Services)]
        Skip --> Out2
    end

    subgraph Phase3["Phase 3: HTTP Probing"]
        direction TB
        Out2 --> Httpx[Httpx HTTP Prober]

        subgraph HttpxFeatures["Detection Features"]
            Live[Live URL Check<br/>Status codes]
            Tech[Technology Detection<br/>Wappalyzer enhanced]
            TLS[TLS/SSL Analysis<br/>Certs, ciphers]
            Headers[Header Analysis<br/>Security headers]
        end

        Httpx --> Live
        Httpx --> Tech
        Httpx --> TLS
        Httpx --> Headers

        Live --> Out3[(Live URLs + Tech Stack)]
        Tech --> Out3
        TLS --> Out3
        Headers --> Out3
    end

    subgraph Phase4["Phase 4: Resource Enumeration"]
        direction TB
        Out3 --> ResEnum[Resource Enumeration]

        subgraph EnumTools["Discovery Methods (Parallel)"]
            Katana[Katana<br/>Active Crawling<br/>Current site structure]
            GAU[GAU<br/>Passive Archives<br/>Historical URLs]
            KR[Kiterunner<br/>API Bruteforce<br/>Hidden endpoints]
        end

        ResEnum --> Katana
        ResEnum --> GAU
        ResEnum --> KR

        Katana --> MergeURL[Merge & Classify]
        GAU --> MergeURL
        KR --> MergeURL

        MergeURL --> Out4[(Endpoints + Parameters)]
    end

    subgraph Phase5["Phase 5: Vulnerability Scanning"]
        direction TB
        Out4 --> Nuclei[Nuclei Scanner]

        subgraph NucleiFeatures["Scan Types"]
            CVE[CVE Detection<br/>Known vulnerabilities]
            DAST[DAST Fuzzing<br/>XSS, SQLi, SSTI]
            Misconfig[Misconfiguration<br/>Exposed panels, defaults]
            Info[Info Disclosure<br/>Backup files, .git]
        end

        Nuclei --> CVE
        Nuclei --> DAST
        Nuclei --> Misconfig
        Nuclei --> Info

        CVE --> MITRE[MITRE Enrichment<br/>CWE + CAPEC]
        DAST --> MITRE
        Misconfig --> MITRE
        Info --> MITRE

        MITRE --> Out5[(Vulnerabilities + Attack Patterns)]
    end

    subgraph Phase6["Phase 6: GitHub Hunting"]
        direction TB
        Out5 --> GitHub[GitHub Secret Hunter]

        subgraph Secrets["Secret Types"]
            API[API Keys<br/>AWS, GCP, Stripe]
            Creds[Credentials<br/>Passwords, tokens]
            Keys[Private Keys<br/>SSH, SSL]
            DB[Database Strings<br/>Connection strings]
        end

        GitHub --> API
        GitHub --> Creds
        GitHub --> Keys
        GitHub --> DB

        API --> Out6[(Exposed Secrets)]
        Creds --> Out6
        Keys --> Out6
        DB --> Out6
    end

    subgraph FinalOutput["📤 Final Output"]
        Out6 --> FinalJSON[(recon_domain.json)]
        FinalJSON --> Neo4j[(Neo4j Graph DB)]
    end
```

### Data Enrichment Flow

```mermaid
flowchart LR
    subgraph Discovery["Discovery Phase"]
        Sub[Subdomains] --> IP[IP Addresses]
        IP --> Port[Open Ports]
        Port --> Service[Services]
    end

    subgraph Analysis["Analysis Phase"]
        Service --> URL[Live URLs]
        URL --> Tech[Technologies]
        Tech --> Endpoint[Endpoints]
    end

    subgraph Assessment["Assessment Phase"]
        Endpoint --> Vuln[Vulnerabilities]
        Vuln --> CVE[CVE IDs]
        CVE --> CWE[CWE Weaknesses]
        CWE --> CAPEC[CAPEC Attacks]
    end

    subgraph Graph["Graph Storage"]
        CAPEC --> Neo4j[(Neo4j)]
    end
```

---

## 📋 Scan Modules Explained

### Configure Which Modules to Run

Configure via the webapp project settings or environment variables:

```bash
# Run all modules (recommended for full assessment)
SCAN_MODULES="domain_discovery,port_scan,http_probe,resource_enum,vuln_scan"

# Quick recon only (no vulnerability scanning)
SCAN_MODULES="domain_discovery"

# Port scan + HTTP probing (skip vulnerability scanning)
SCAN_MODULES="domain_discovery,port_scan,http_probe"
```

### Module 1: `domain_discovery`

```mermaid
flowchart LR
    subgraph Input
        Domain[example.com]
    end

    subgraph Discovery["Domain Discovery"]
        WHOIS[WHOIS<br/>Registrar info]
        CRT[crt.sh<br/>CT logs]
        HT[HackerTarget<br/>DNS search]
        Knock[Knockpy<br/>Bruteforce]
        DNS[DNS Resolver<br/>All record types]
    end

    subgraph Output
        Subs[Subdomains]
        IPs[IP Addresses]
        Records[DNS Records]
    end

    Domain --> WHOIS
    Domain --> CRT
    Domain --> HT
    Domain --> Knock

    WHOIS --> DNS
    CRT --> DNS
    HT --> DNS
    Knock --> DNS

    DNS --> Subs
    DNS --> IPs
    DNS --> Records
```

| What It Does | Output |
|--------------|--------|
| **WHOIS lookup** | Registrar, creation date, owner info |
| **Subdomain discovery** | Finds subdomains via passive sources |
| **DNS enumeration** | A, AAAA, MX, NS, TXT, CNAME records |
| **IP resolution** | Maps all discovered hostnames to IPs |

📖 **Key Parameters:**
```python
TARGET_DOMAIN = "example.com"           # Root domain
SUBDOMAIN_LIST = []                     # Empty = discover ALL
USE_BRUTEFORCE_FOR_SUBDOMAINS = False   # Brute force mode
```

---

### Module 2: `port_scan`

```mermaid
flowchart LR
    subgraph Input
        IPs[IP Addresses]
    end

    subgraph Scanner["Naabu Scanner"]
        SYN[SYN Scan]
        Service[Service Detection]
        CDN[CDN Detection]
    end

    subgraph Output
        Ports[Open Ports]
        Services[Service Names]
        CDNInfo[CDN/WAF Info]
    end

    IPs --> SYN
    SYN --> Service
    Service --> CDN
    CDN --> Ports
    CDN --> Services
    CDN --> CDNInfo
```

| What It Finds | Examples |
|---------------|----------|
| **Open ports** | 22/SSH, 80/HTTP, 443/HTTPS, 3306/MySQL |
| **CDN detection** | Cloudflare, Akamai, Fastly |
| **Service hints** | Common service identification |

📖 **Key Parameters:**
```python
NAABU_TOP_PORTS = "1000"        # Number of top ports
NAABU_RATE_LIMIT = 1000         # Packets per second
NAABU_SCAN_TYPE = "s"           # SYN scan
```

📖 **Detailed documentation:** [readmes/README.PORT_SCAN.md](README.PORT_SCAN.md)

---

### Module 3: `http_probe`

```mermaid
flowchart LR
    subgraph Input
        URLs[Target URLs<br/>from port scan]
    end

    subgraph Httpx["Httpx Prober"]
        Probe[HTTP/S Requests]
        Tech[Technology Detection]
        TLS[TLS Analysis]
        Headers[Header Extraction]
    end

    subgraph Wappalyzer["Wappalyzer Enhancement"]
        CMS[CMS Detection]
        Plugins[Plugin Detection]
        Analytics[Analytics Tools]
    end

    subgraph Output
        Live[Live URLs]
        Stack[Tech Stack]
        Certs[Certificates]
        SecHeaders[Security Headers]
    end

    URLs --> Probe
    Probe --> Tech
    Probe --> TLS
    Probe --> Headers

    Tech --> Wappalyzer
    Wappalyzer --> CMS
    Wappalyzer --> Plugins
    Wappalyzer --> Analytics

    CMS --> Live
    Plugins --> Stack
    Analytics --> Stack
    TLS --> Certs
    Headers --> SecHeaders
```

| What It Finds | Examples |
|---------------|----------|
| **Live URLs** | Which endpoints are responding |
| **Technologies** | WordPress, nginx, PHP, React |
| **CMS Plugins** | Yoast SEO, WooCommerce (via Wappalyzer) |
| **TLS certificates** | Issuer, expiry, SANs |

📖 **Detailed documentation:** [readmes/README.HTTP_PROBE.md](README.HTTP_PROBE.md)

---

### Module 4: `resource_enum`

```mermaid
flowchart TB
    subgraph Input
        URLs[Live URLs]
    end

    subgraph Parallel["Parallel Execution"]
        subgraph Active["Active Discovery"]
            Katana[🕸️ Katana<br/>Web Crawler<br/>Current endpoints]
        end

        subgraph Passive["Passive Discovery"]
            GAU[📚 GAU<br/>Archive Search<br/>Historical URLs]
        end

        subgraph Bruteforce["API Discovery"]
            KR[🔑 Kiterunner<br/>Swagger Specs<br/>Hidden APIs]
        end
    end

    subgraph Merge["Merge & Classify"]
        Dedup[Deduplicate]
        Classify[Classify Endpoints<br/>API, Admin, Form, Static]
        Parse[Parse Parameters]
    end

    subgraph Output
        Endpoints[All Endpoints]
        Forms[Forms + Inputs]
        APIs[API Routes]
    end

    URLs --> Katana
    URLs --> GAU
    URLs --> KR

    Katana --> Dedup
    GAU --> Dedup
    KR --> Dedup

    Dedup --> Classify
    Classify --> Parse

    Parse --> Endpoints
    Parse --> Forms
    Parse --> APIs
```

| Tool | Method | What It Finds |
|------|--------|---------------|
| **Katana** | Active crawling | Current live endpoints |
| **GAU** | Passive archives | Historical/deleted pages |
| **Kiterunner** | API bruteforce | Hidden API routes |

📖 **Detailed documentation:** [readmes/README.RESOURCE_ENUM.md](README.RESOURCE_ENUM.md)

---

### Module 5: `vuln_scan`

```mermaid
flowchart TB
    subgraph Input
        Endpoints[All Endpoints]
        Tech[Technology Stack]
    end

    subgraph Nuclei["Nuclei Scanner"]
        Templates[9000+ Templates]

        subgraph ScanTypes["Scan Types"]
            CVEScan[CVE Detection<br/>Known vulns]
            DAST[DAST Fuzzing<br/>XSS, SQLi, SSTI]
            Misconfig[Misconfiguration<br/>Exposed panels]
            InfoLeak[Info Disclosure<br/>.git, backups]
        end
    end

    subgraph CVELookup["CVE Lookup"]
        NVD[Query NVD<br/>by technology version]
        Match[Match CVEs<br/>nginx:1.19 → CVE-2021-23017]
    end

    subgraph MITRE["MITRE Enrichment"]
        CWE[CWE Weaknesses<br/>Weakness hierarchy]
        CAPEC[CAPEC Patterns<br/>Attack techniques]
    end

    subgraph Output
        Vulns[Vulnerabilities]
        CVEs[CVE Details]
        Attacks[Attack Patterns]
    end

    Endpoints --> Templates
    Tech --> CVELookup

    Templates --> CVEScan
    Templates --> DAST
    Templates --> Misconfig
    Templates --> InfoLeak

    CVEScan --> MITRE
    DAST --> MITRE
    CVELookup --> NVD
    NVD --> Match
    Match --> MITRE

    MITRE --> CWE
    CWE --> CAPEC

    Misconfig --> Vulns
    InfoLeak --> Vulns
    CAPEC --> CVEs
    CAPEC --> Attacks
```

| What It Finds | Examples |
|---------------|----------|
| **Web CVEs** | Log4Shell, Spring4Shell |
| **Injection flaws** | SQL injection, XSS |
| **Misconfigurations** | Exposed admin panels |
| **CWE Weaknesses** | Weakness hierarchy |
| **CAPEC Attacks** | Attack techniques |

📖 **Detailed documentation:** [readmes/README.VULN_SCAN.md](README.VULN_SCAN.md) | [readmes/README.MITRE.md](README.MITRE.md)

---

### Module 6: `github`

```mermaid
flowchart LR
    subgraph Input
        Org[GitHub Org/User]
    end

    subgraph Hunter["GitHub Secret Hunter"]
        Repos[List Repositories]
        Commits[Search Commits]
        Code[Search Code]
    end

    subgraph Patterns["Detection Patterns"]
        AWS[AWS Keys]
        GCP[GCP Credentials]
        Stripe[Stripe Keys]
        DB[Database Strings]
        SSH[SSH Keys]
    end

    subgraph Output
        Secrets[Exposed Secrets]
    end

    Org --> Repos
    Repos --> Commits
    Repos --> Code

    Commits --> Patterns
    Code --> Patterns

    AWS --> Secrets
    GCP --> Secrets
    Stripe --> Secrets
    DB --> Secrets
    SSH --> Secrets
```

---

## 🆚 Complete Tool Comparison

### Overview Matrix

```mermaid
flowchart TB
    subgraph Layer1["Layer 1: DNS/Registry"]
        WHOIS[WHOIS<br/>Domain info]
        DNS[DNS<br/>Resolution]
    end

    subgraph Layer2["Layer 4: Transport"]
        Naabu[Naabu<br/>Port scan]
    end

    subgraph Layer3["Layer 7: Application"]
        Httpx[Httpx<br/>HTTP probe]
        Katana[Katana<br/>Crawl]
        GAU[GAU<br/>Archives]
        KR[Kiterunner<br/>API brute]
        Nuclei[Nuclei<br/>Vuln scan]
    end

    subgraph Layer1b["OSINT Enrichment"]
        Shodan2[Shodan<br/>Host/DNS/CVEs]
        URLScan[URLScan<br/>Historical scans]
    end

    subgraph Layer4["Data Enrichment"]
        MITRE[MITRE<br/>CWE/CAPEC]
        GVM[GVM<br/>Deep scan]
    end

    WHOIS --> DNS
    DNS --> Shodan2
    DNS --> URLScan
    Shodan2 --> Naabu
    URLScan --> Naabu
    Naabu --> Httpx
    Httpx --> Katana
    Httpx --> GAU
    Httpx --> KR
    Katana --> Nuclei
    GAU --> Nuclei
    KR --> Nuclei
    Nuclei --> MITRE
    Nuclei --> GVM
```

### Feature Comparison

| Feature | WHOIS | DNS | Shodan | URLScan | Naabu | httpx | Katana | GAU | Kiterunner | Nuclei | GVM |
|---------|-------|-----|--------|---------|-------|-------|--------|-----|------------|--------|-----|
| **Domain Info** | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **IP Resolution** | ❌ | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Subdomain Discovery** | ❌ | ❌ | ⚠️ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Port Scanning** | ❌ | ❌ | ⚠️ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Live URL Check** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Tech Detection** | ❌ | ❌ | ⚠️ | ⚠️ | ❌ | ✅ | ❌ | ❌ | ❌ | ⚠️ | ⚠️ |
| **Endpoint Discovery** | ❌ | ❌ | ❌ | ⚠️ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Historical URLs** | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **API Discovery** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **CVE Detection** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| **External Domains** | ❌ | ❌ | ❌ | ✅ | ❌ | ⚠️ | ⚠️ | ⚠️ | ❌ | ❌ | ❌ |
| **XSS/SQLi Testing** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ⚠️ |

**Legend:** ✅ Primary | ⚠️ Limited | ❌ Not supported

### Timing Comparison

| Tool | Typical Duration | Notes |
|------|------------------|-------|
| WHOIS | <1 second | Instant |
| DNS | <1 second | Instant |
| Shodan | 5-15 seconds | Passive, per-IP queries |
| URLScan | 5-20 seconds | Passive, API rate-limited |
| Naabu | 5-10 seconds | 1000 ports |
| httpx | 10-30 seconds | All options |
| Katana | 1-5 minutes | Crawl depth 3 |
| GAU | 10-30 seconds | Passive |
| Nuclei | 1-30 minutes | Depends on templates |
| GVM | 30 min - 2+ hours | Full scan |

---

## ⚙️ Key Configuration Parameters

### Essential Settings

All settings are managed through the webapp project form or via environment variables. Key defaults are defined in `project_settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `TARGET_DOMAIN` | — | Root domain to scan |
| `SUBDOMAIN_LIST` | `[]` | Empty = discover all |
| `SCAN_MODULES` | all 5 modules | Modules to run |
| `NAABU_TOP_PORTS` | `"1000"` | Top-N ports to scan |
| `NAABU_SCAN_TYPE` | `"s"` | SYN scan |
| `NUCLEI_DAST_MODE` | `true` | Active fuzzing |
| `NUCLEI_SEVERITY` | critical, high, medium, low | Severity filter |
| `WAPPALYZER_ENABLED` | `true` | Technology detection |
| `MITRE_INCLUDE_CWE` | `true` | CWE enrichment |
| `MITRE_INCLUDE_CAPEC` | `true` | CAPEC enrichment |

---

## 🔧 Prerequisites

### Docker Mode (Recommended)

- **Docker** with Docker Compose
- **Docker socket access** for nested container execution

```bash
# Verify Docker is running
docker info

# Build and run
cd recon/
docker-compose build --network=host
docker-compose run --rm recon python /app/recon/main.py
```

### Tool Containers (auto-pulled)

| Tool | Docker Image | Purpose |
|------|--------------|---------|
| Naabu | `projectdiscovery/naabu:latest` | Port scanning |
| httpx | `projectdiscovery/httpx:latest` | HTTP probing |
| Nuclei | `projectdiscovery/nuclei:latest` | Vuln scanning |
| Katana | `projectdiscovery/katana:latest` | Web crawling |
| GAU | `sxcurity/gau:latest` | URL discovery |

---

## 📁 Project Structure

```
recon/
├── Dockerfile              # Container build
├── docker-compose.yml      # Orchestration
├── project_settings.py     # 🔗 Settings fetcher (API or built-in defaults)
├── main.py                 # 🚀 Entry point
├── domain_recon.py         # Subdomain discovery
├── whois_recon.py          # WHOIS lookup
├── urlscan_enrich.py       # URLScan.io OSINT enrichment
├── port_scan.py            # Port scanning
├── http_probe.py           # HTTP probing
├── resource_enum.py        # Endpoint discovery
├── vuln_scan.py            # Vulnerability scanning
├── add_mitre.py            # MITRE enrichment
├── github_secret_hunt.py   # GitHub secrets
├── output/                 # 📄 Scan results (JSON)
├── data/                   # 📦 Cached databases
│   ├── mitre_db/           # CVE2CAPEC database
│   └── wappalyzer/         # Technology rules
├── helpers/                # Tool helpers
└── readmes/                # 📖 Module docs
```

---

## 📊 Output Format

All modules write to: `recon/output/recon_<domain>.json`

```mermaid
flowchart TB
    subgraph JSON["recon_domain.json"]
        Meta[metadata<br/>scan info, timestamps]
        WHOIS[whois<br/>registrar, dates]
        Subs[subdomains<br/>discovered hosts]
        DNSData[dns<br/>A, MX, TXT records]
        Ports[port_scan<br/>open ports, services]
        HTTP[http_probe<br/>live URLs, tech stack]
        Resources[resource_enum<br/>endpoints, forms]
        Vulns[vuln_scan<br/>CVEs, misconfigs]
        TechCVE[technology_cves<br/>version-based CVEs]
    end

    Meta --> WHOIS
    WHOIS --> Subs
    Subs --> DNSData
    DNSData --> Ports
    Ports --> HTTP
    HTTP --> Resources
    Resources --> Vulns
    Vulns --> TechCVE
```

---

## 🧪 Test Targets

Safe, **legal** targets for security testing:

| Target | Technology | Vulnerabilities |
|--------|------------|-----------------|
| `testphp.vulnweb.com` | PHP + MySQL | SQLi, XSS, LFI |
| `testhtml5.vulnweb.com` | HTML5 | DOM XSS |
| `testasp.vulnweb.com` | ASP.NET | SQLi, XSS |
| `scanme.nmap.org` | N/A | Port scanning only |

```python
# Example configuration
TARGET_DOMAIN = "vulnweb.com"
SUBDOMAIN_LIST = ["testphp."]
NUCLEI_DAST_MODE = True
```

---

## ⚠️ Legal Disclaimer

**Only scan systems you own or have explicit written permission to test.**

Unauthorized scanning is illegal. RedAmon is intended for:
- Penetration testers with proper authorization
- Security researchers on approved targets
- Bug bounty hunters within program scope
- System administrators testing their infrastructure

---

## 📖 Detailed Documentation

| Module | Documentation |
|--------|---------------|
| Port Scan | [readmes/README.PORT_SCAN.md](README.PORT_SCAN.md) |
| HTTP Probe | [readmes/README.HTTP_PROBE.md](README.HTTP_PROBE.md) |
| Vuln Scan | [readmes/README.VULN_SCAN.md](README.VULN_SCAN.md) |
| MITRE CWE/CAPEC | [readmes/README.MITRE.md](README.MITRE.md) |
| GVM/OpenVAS | [README.GVM.md](README.GVM.md) |
