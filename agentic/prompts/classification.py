"""
RedAmon Attack Path Classification Prompt

LLM-based classification of user intent to select the appropriate attack path and phase.
Determines both the attack methodology AND the required phase (informational/exploitation).
"""


ATTACK_PATH_CLASSIFICATION_PROMPT = """You are classifying a penetration testing request to determine:
1. The required PHASE (informational vs exploitation)
2. The ATTACK PATH TYPE (for exploitation requests only)

## Phase Types

### informational
- Reconnaissance, OSINT, information gathering
- Querying the graph database for targets, vulnerabilities, services
- Scanning and enumeration without exploitation
- Example requests:
  - "What vulnerabilities exist on 10.0.0.5?"
  - "Show me all open ports on the target"
  - "What services are running?"
  - "Query the graph for CVEs"
  - "Scan the network"
  - "What technologies are used?"

### exploitation
- Active exploitation of vulnerabilities
- Brute force / credential attacks
- Generating payloads, malicious files, reverse shells, or backdoors for victim execution
- Setting up handlers, listeners, or delivery servers
- Any request that involves gaining unauthorized access
- Example requests:
  - "Exploit CVE-2021-41773"
  - "Brute force SSH"
  - "Try to crack the password"
  - "Pwn the target"
  - "Try SQL injection on the web app"
  - "Generate a reverse shell payload"
  - "Create a malicious Word document"
  - "Set up a web delivery attack"

## Attack Path Types (ONLY for exploitation phase)

### cve_exploit
- Exploiting known CVE vulnerabilities
- Using Metasploit exploit modules (`exploit/*`)
- Keywords: CVE-XXXX-XXXX, MS17-XXX, vulnerability, exploit, RCE, remote code execution, pwn, hack
- Requires: TARGET selection, PAYLOAD selection
- Command: `exploit`
- Example requests:
  - "Exploit CVE-2021-41773 on 10.0.0.5"
  - "Use the Apache path traversal vulnerability"
  - "Attack the target using MS17-010"
  - "Test if the server is vulnerable to Log4Shell"

### brute_force_credential_guess
- Password guessing / credential attacks
- Using THC Hydra for password brute-forcing (`execute_hydra`)
- Keywords: brute force, crack password, credential attack, dictionary attack, password spray, guess password, wordlist, login attack
- Services: SSH, FTP, RDP, VNC, SMB, MySQL, MSSQL, PostgreSQL, Telnet, POP3, IMAP, HTTP login, Tomcat
- Requires: wordlists/credential files
- Tool: `execute_hydra` (NOT metasploit_console)
- Example requests:
  - "Brute force SSH on 10.0.0.5"
  - "Try to crack the MySQL password"
  - "Password spray against the FTP server"
  - "Guess credentials for the Tomcat manager"
  - "Dictionary attack on the SSH service"
  - "Try default credentials on PostgreSQL"
  - "Try to get access to SSH guessing password"

### phishing_social_engineering
- **Core concept: ANY attack where a HUMAN VICTIM must execute, open, click, or install something.**
  The attacker generates an artifact (payload file, malicious document, link, one-liner) and delivers it
  to a person. The attack succeeds when the VICTIM runs it on THEIR computer/device.
- This is the opposite of cve_exploit where the attacker sends a crafted request directly to a SERVICE.

- **Victim-executed payloads** — standalone files the victim runs on their machine:
  - Windows: EXE, PowerShell scripts, HTA files, LNK shortcuts
  - Linux: ELF binaries, bash one-liners, Python one-liners
  - macOS: Mach-O binaries, bash/Python one-liners
  - Android: APK files
  - Cross-platform: Python scripts, Java WAR files
- **Malicious documents** — files the victim opens in an application:
  - Word/Excel with VBA macros, trojanized PDFs, weaponized RTF, malicious LNK
- **Web delivery / hosted payloads** — the victim visits a URL or runs a provided one-liner:
  - HTA server, PowerShell web delivery, Python web delivery, Regsvr32 delivery, PHP delivery
- **Email delivery** — payload or link sent to victim via email
- **Payload encoding/evasion** — encoding payloads (shikata_ga_nai, x64/xor) to bypass AV on the victim's machine
- **Handler setup** — setting up Metasploit `exploit/multi/handler` to catch the callback from the victim's machine (NEVER netcat/socat — only Metasploit handlers create tracked sessions)

- **How to distinguish from other attack paths:**
  - "Generate a reverse shell for the target" → phishing (victim must execute it)
  - "Generate a bash one-liner for command injection" → phishing (generating a payload for victim execution)
  - "Exploit CVE-2021-41773 on 10.0.0.5" → cve_exploit (directly attacks a service, no human victim)

- Tools: `kali_shell` (msfvenom), `metasploit_console` (fileformat modules, handler, web_delivery), `execute_code` (email sending)
- Example requests (one per category — applies to ALL OS targets):
  - "Generate a Windows Meterpreter EXE payload and set up the handler" (standalone payload)
  - "Generate a bash reverse shell one-liner for a Linux victim" (one-liner payload)
  - "Generate an Android APK backdoor" (mobile payload)
  - "Generate a macOS Mach-O Meterpreter payload" (macOS payload)
  - "Create a malicious Word document with a VBA macro" (malicious document)
  - "Set up a PowerShell web delivery attack" (web delivery)
  - "Generate a payload and send it via phishing email" (email delivery)
  - "Generate an encoded EXE with shikata_ga_nai for AV evasion" (encoded payload)

### <descriptive_term>-unclassified
- ANY exploitation request that does NOT clearly fit cve_exploit, brute_force_credential_guess, or phishing_social_engineering
- The agent has no specialized workflow for these — it will use available tools generically
- **Key distinction from phishing:** the attacker directly interacts with a SERVICE/APPLICATION, NOT generating a payload for a human victim
  - "Try SQL injection on the web app" → unclassified (attacker sends crafted input to a web service)
  - "Generate a reverse shell payload" → phishing (attacker creates a file for a victim to execute)
- You MUST create a short, descriptive snake_case term followed by "-unclassified"
- Format: `<term>-unclassified` where term is 1-4 lowercase words joined by underscores
- Example values: "sql_injection-unclassified", "dos_attack-unclassified", "ssrf-unclassified", "xss-unclassified", "file_upload-unclassified", "directory_traversal-unclassified"
- Keywords: SQL injection, XSS, cross-site scripting, directory traversal, path traversal, DoS, denial of service, SSRF, file upload, command injection, LFI, RFI, deserialization, XXE, privilege escalation
- Example requests:
  - "Try SQL injection on the web app" -> "sql_injection-unclassified"
  - "Test for SSRF on the API" -> "ssrf-unclassified"
  - "Try to upload a web shell" -> "file_upload-unclassified"
  - "Test for XSS on the login page" -> "xss-unclassified"
  - "Attempt directory traversal" -> "directory_traversal-unclassified"
  - "Try command injection on the web form" -> "command_injection-unclassified"

## User Request
{objective}

## Instructions
Classify the user's request:

1. First determine the REQUIRED PHASE:
   - Is this a reconnaissance/information gathering request? -> "informational"
   - Is this an active attack/exploitation request? -> "exploitation"

2. If exploitation, determine the ATTACK PATH TYPE using this priority order:
   a. **phishing_social_engineering** (check FIRST — highest priority):
      - Is the request asking to GENERATE, CREATE, or SET UP a payload, malicious file, document, backdoor, reverse shell, one-liner, or delivery server?
      - Will the output be something a HUMAN VICTIM must execute, open, click, or install on their machine?
      - Does it mention msfvenom, handler, multi/handler, web delivery, HTA server, encoding for AV evasion?
      - Does it mention sending something via email to a target person?
      - If YES to any → "phishing_social_engineering"
   b. **brute_force_credential_guess**:
      - Does the request mention password guessing, brute force, credential attacks, wordlists, or dictionary attacks?
      - Does it target a login service (SSH, FTP, MySQL, etc.) with credential-based attack?
      - If YES → "brute_force_credential_guess"
   c. **cve_exploit**:
      - Does the request mention a specific CVE ID or Metasploit exploit module to use DIRECTLY against a service?
      - Does it describe exploiting a service vulnerability where NO human victim interaction is needed?
      - If YES → "cve_exploit"
   d. **<descriptive_term>-unclassified**:
      - Does the request describe a specific attack technique (SQLi, XSS, SSRF, DoS, file upload, command injection against a web form) where the attacker directly interacts with a service?
      - If YES → "<descriptive_term>-unclassified"
   e. Default to "cve_exploit" if truly unclear (e.g., vague "hack the target")

3. If informational, set attack_path_type to "cve_exploit" (default, won't be used)

4. Extract TARGET HINTS from the request (best-effort, used for graph linking):
   - target_host: IP address or hostname mentioned (e.g., "10.0.0.5", "www.example.com"). null if none found.
   - target_port: port number mentioned (e.g., 8080, 443). null if none found.
   - target_cves: list of CVE IDs mentioned (e.g., ["CVE-2021-41773"]). Empty list if none found.

Output valid JSON matching this schema:

```json
{{
  "required_phase": "informational" | "exploitation",
  "attack_path_type": "cve_exploit" | "brute_force_credential_guess" | "phishing_social_engineering" | "<descriptive_term>-unclassified",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of the classification",
  "detected_service": "ssh" | "ftp" | "mysql" | "mssql" | "postgres" | "smb" | "rdp" | "vnc" | "telnet" | "tomcat" | "http" | null,
  "target_host": "10.0.0.5" | "www.example.com" | null,
  "target_port": 8080 | null,
  "target_cves": ["CVE-2021-41773"] | []
}}
```

Notes:
- `required_phase` determines if this is reconnaissance ("informational") or active attack ("exploitation")
- `attack_path_type` is only relevant when required_phase is "exploitation"
- For unclassified paths, the term MUST be lowercase snake_case followed by "-unclassified" (e.g., "sql_injection-unclassified")
- `detected_service` should only be set for brute_force_credential_guess, null otherwise
- `confidence` should be 0.9+ if the intent is very clear, 0.6-0.8 if somewhat ambiguous
- `target_host`, `target_port`, `target_cves` are best-effort extraction — null/empty if not mentioned
"""
