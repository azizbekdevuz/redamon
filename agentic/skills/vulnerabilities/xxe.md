# XXE Testing Guide Summary

## Overview
XML External Entity (XXE) injection is a critical parser-level vulnerability enabling file disclosure, SSRF attacks, denial-of-service, and potentially code execution.

## Key Attack Vectors

The document identifies three primary capabilities:
- **File access**: Reading server files and configuration data
- **SSRF**: Reaching internal metadata services and admin panels
- **DoS**: Entity expansion attacks and resource amplification

Common injection surfaces include REST/SOAP endpoints, file uploads (SVG, Office documents), and XML-RPC services.

## Detection Methods

The guide outlines four detection channels:

1. **Direct**: Entity content appears in HTTP responses or error pages
2. **Error-based**: Parser errors leak file paths or content
3. **OAST**: Blind XXE confirmed via DNS/HTTP callbacks
4. **Timing**: Latency differences from slow external resources

## Testing Approach

The recommended methodology involves five steps:

1. Identify all XML consumers across the application
2. Test parser capabilities (DOCTYPE support, entity resolution)
3. Establish an oracle to detect successful exploitation
4. Execute targeted payloads
5. Validate findings across multiple channels

## Mitigation

"XXE is eliminated by hardening parsers: forbid DOCTYPE, disable external entity" resolution and disable network access for processors.
