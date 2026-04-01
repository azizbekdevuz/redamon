# Deep Testing Mode - Complete Content

The document outlines an exhaustive security assessment methodology organized into six phases:

**Phase 1: Exhaustive Reconnaissance** combines whitebox analysis (mapping files, using tools like semgrep and gitleaks, tracing entry points) with blackbox enumeration (subdomains, ports, content discovery, API mapping).

**Phase 2: Business Logic Deep Dive** emphasizes creating "a complete storyboard of the application" including user flows, state machines, trust boundaries, and implicit assumptions to identify multi-step attack surfaces.

**Phase 3: Comprehensive Attack Surface Testing** systematically tests input handling, authentication, access control, file operations, business logic, and advanced techniques across the entire application.

**Phase 4: Vulnerability Chaining** treats "every finding as a pivot point" to combine low-severity issues into high-impact attack chains that cross component boundaries.

**Phase 5: Persistent Testing** recommends revisiting areas with alternative techniques when initial attempts fail, leveraging insights from other findings.

**Phase 6: Comprehensive Reporting** requires documenting all severity levels with reproduction steps and remediation guidance.

The methodology emphasizes parallel decomposition through specialized agents targeting specific vulnerability types rather than overloading single agents, maintaining a "relentless" and "thorough" mindset focused on systemic issues others miss.
