# Root Agent Documentation Summary

The Root Agent serves as an orchestration layer for security assessments, coordinating specialized subagents rather than conducting direct testing.

## Key Responsibilities

The agent decomposes targets into parallelizable tasks, spawns and monitors subagents, aggregates findings, and manages dependencies. It analyzes attack surfaces, defines boundaries, determines assessment approaches, and prioritizes assets by risk before initiating specialized work.

## Agent Structure

The documentation outlines four functional categories:

- **Reconnaissance**: Asset discovery, technology fingerprinting, and attack surface mapping
- **Vulnerability Assessment**: Testing for injections, authentication flaws, access control issues, business logic problems, and infrastructure weaknesses
- **Exploitation**: Proof-of-concept development and impact demonstration
- **Reporting**: Documentation and remediation guidance

## Operational Principles

The Root Agent emphasizes "minimal dependencies" between agents to enable parallel execution. Each agent requires "a specific, measurable goal" to prevent scope creep. The documentation recommends analyzing target scope, checking existing agents to prevent overlap, and creating focused objectives before spawning new agents.

The coordination approach uses hierarchical delegation—discovery agents identify vulnerabilities, validation agents confirm exploitability, reporting agents document findings, and specialized agents provide remediation guidance.

## Completion Process

Upon agent completion, the Root Agent collects deduplicated findings, assesses overall security posture, compiles an executive summary with prioritized recommendations, and invokes the finish tool with the final report.
