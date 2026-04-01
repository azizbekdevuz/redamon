# FastAPI Security Testing Playbook - Summary

This comprehensive guide addresses security vulnerabilities in FastAPI/Starlette applications across multiple attack vectors.

## Core Focus Areas

The playbook emphasizes three critical domains:

1. **Dependency Injection Flaws** - Routes may lack security dependencies present elsewhere, and using `Depends` instead of `Security` bypasses scope enforcement.

2. **Middleware Gaps** - ASGI components like CORS, TrustedHost, and ProxyHeaders can be misconfigured or inconsistently applied across mounted sub-applications.

3. **Authorization Drift** - "Routes missing security dependencies present on other routes" and scope bypass vulnerabilities across routers and channels.

## High-Risk Targets

- OpenAPI documentation endpoints exposing the full attack surface in production
- Authentication flows (tokens, sessions, OAuth implementations)
- File operations and upload/download functionality
- WebSocket endpoints lacking per-message authorization
- Mounted sub-applications bypassing global middleware

## Key Vulnerability Classes

**Input Handling**: Pydantic's type coercion and extra field policies can enable injection attacks. Content-type switching between JSON and form data may traverse different validation paths.

**Token Security**: Unsigned JWT acceptance, algorithm confusion, and missing issuer/audience validation represent common JWT misuse patterns.

**Access Control**: IDOR vulnerabilities arise when "object IDs in path/query [are] not validated against caller," and tenant isolation breaks under spoofed headers.

**Proxy Trust**: "ProxyHeadersMiddleware without network boundary" allows spoofing `X-Forwarded-For` to bypass IP-based controls.

Testing requires systematic enumeration, dependency mapping, and cross-channel validation to confirm authorization enforcement consistency.
