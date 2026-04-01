# Path Traversal / LFI / RFI Testing Guide

This resource outlines vulnerability assessment for improper file handling that enables unauthorized file access and code execution.

## Core Threats

The document identifies three primary attack vectors:

1. **Path Traversal** – Accessing files outside intended directories using sequences like `../` and encoding variations
2. **Local File Inclusion (LFI)** – Injecting server-side files into interpreters or templates
3. **Remote File Inclusion (RFI)** – Loading external resources for code execution

## Testing Approach

The methodology emphasizes a five-step process:
- Catalog file operations across the application
- Locate where user input joins file paths
- Test encoding, separators, and normalization handling
- Compare web server versus application behavior
- Escalate from information disclosure toward execution

## High-Priority Targets

Unix systems expose `/etc/passwd`, configuration files, and SSH keys. Windows targets include `win.ini`, `web.config`, and IIS settings. Applications risk leaking source code, environment variables, and framework caches.

## Detection Methods

Vulnerabilities surface through direct content disclosure, error messages revealing real paths, out-of-band callbacks confirming inclusion, or unexpected file writes from archive extraction.

## Remediation Strategy

"Eliminate user-controlled paths where possible. Otherwise, resolve to canonical paths and enforce allowlists, forbid remote schemes, and lock down interpreters and extractors."

The guide emphasizes normalizing inputs consistently at boundaries closest to file system operations.
