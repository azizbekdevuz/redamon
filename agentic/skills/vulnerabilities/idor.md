# IDOR Testing Guide - Summary

This comprehensive resource covers **Object-Level Authorization Failures (BOLA/IDOR)**, which occur when applications fail to properly verify that users can only access objects they own or have permission to view.

## Key Concepts

The document emphasizes treating "every object reference as untrusted until proven bound to the caller." Attack surfaces span multiple dimensions:

- **Horizontal breaches**: accessing peers' data of the same type
- **Vertical breaches**: accessing privileged resources (admin functions)
- **Cross-tenant violations**: breaking isolation in multi-tenant systems

## High-Value Targets

Particularly sensitive endpoints include export/backup functions, billing records, messaging systems, healthcare/education data, and file storage with weak access controls.

## Testing Approach

The methodology recommends:
1. Building a subject-object-action matrix
2. Obtaining multiple privilege levels of test accounts
3. Collecting valid object identifiers from list endpoints
4. Systematically swapping IDs and tokens across actions

## Common Vulnerabilities

The guide highlights that batch operations frequently validate only initial elements, pagination can leak cross-tenant data, and secondary IDOR occurs when valid IDs from notifications or logs enable unauthorized direct access.

## Technology-Specific Issues

GraphQL requires per-resolver checks rather than top-level gates. Microservices often suffer from token confusion and header-injection vulnerabilities. WebSocket implementations frequently skip per-subscription authorization.

The fundamental principle: authorization bindings must cover subject, action, and resource on every single request.
