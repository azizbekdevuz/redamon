# Standard Testing Mode - Content Summary

This document outlines a balanced security assessment methodology called "Standard Testing Mode" that combines systematic coverage with practical depth.

## Key Phases

**Reconnaissance** begins with understanding the application architecture. In whitebox scenarios, testers should "Map codebase structure: modules, entry points, routing" and run initial automated tools like semgrep for triage before manual review.

**Business Logic Analysis** requires mapping critical flows and trust boundaries before vulnerability testing, ensuring testers understand "what actions are restricted to which users" and proper data isolation.

**Systematic Testing** covers input validation, authentication mechanisms, access controls, and business logic flaws across the full attack surface through focused testing in each area.

**Exploitation** demands working proof-of-concepts with actual impact demonstration rather than theoretical risks, emphasizing "complete end-to-end paths (entry point → pivot → privileged action/data)."

## Approach Philosophy

The methodology prioritizes methodical work with continuous documentation and validation. Testers should pursue vulnerability chaining by asking what each finding enables next, avoiding isolated discoveries in favor of demonstrating maximum impact through realistic attack sequences.

The guidance emphasizes understanding legitimate application workflows before testing, ensuring exploits survive actual usage patterns and state transitions rather than relying on theoretical scenarios.
