# Open Redirect Testing Guide

## Overview

Open redirects represent a critical vulnerability class enabling phishing attacks, OAuth token interception, and security policy circumvention. The guidance emphasizes treating all redirect destinations as untrusted and implementing strict canonicalization with exact allowlists.

## Key Attack Vectors

The vulnerability manifests across multiple surfaces:

- **HTTP redirects** via 3xx status codes
- **Client-side navigation** through `window.location`, meta refresh, and SPA routers
- **OAuth/OIDC/SAML flows** leveraging `redirect_uri` and related parameters
- **Multi-hop chains** where only initial hops undergo validation

## Common Exploitation Techniques

Testing should explore parser differentials, including userinfo injection (`https://trusted.com@evil.com`), backslash/slash variants, whitespace encoding, fragment/query confusion, and Unicode/IDNA bypasses.

Allowlist evasion frequently exploits substring matching, insufficient scheme pinning, and canonicalization inconsistencies between validators and browsers.

## Validation Strategies

Robust defenses require:

- Single canonical URL parser (WHATWG standard)
- Exact scheme and hostname comparison post-IDNA normalization
- Explicit allowlists with optional path prefixes
- Rejection of protocol-relative URLs and non-standard schemes

## Testing Approach

Effective assessment involves inventorying redirect surfaces, building comprehensive test matrices across encoding variations, comparing server validation against actual browser behavior, and demonstrating multi-hop evasion with proof of external navigation.
