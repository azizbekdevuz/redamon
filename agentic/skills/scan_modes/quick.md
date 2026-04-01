---
name: quick
description: Time-boxed rapid assessment targeting high-impact vulnerabilities.
---

# Quick Scan Mode

## Overview

Breadth over depth. Evaluate high-value attack surfaces. Skip low-severity issues.

## Phase 1 — Rapid Orientation

- **Whitebox**: analyze recent code modifications
- **Blackbox**: map authentication flows (no exhaustive enumeration)

## Phase 2 — High-Impact Targets

Priority list:
1. Authentication bypass
2. Broken access control
3. Remote code execution
4. SQL injection
5. SSRF
6. Exposed secrets

## Phase 3 — Validation

- Demonstrate concrete exploitability (not theoretical)
- Report confirmed findings immediately

## Strategic Principles

- Chain vulnerabilities when a strong primitive is found
- Selective tool usage: browser for critical flows, targeted terminal scans, proxy inspection
- No extensive fuzzing, no unnecessary parallel investigation
- Pivot away from unproductive vectors
- Mindset: time-boxed bug bounty hunting focused on quick wins
