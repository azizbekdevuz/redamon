# GraphQL Security Testing Overview

This document covers comprehensive security testing for GraphQL APIs, emphasizing resolver-level authorization, field access control, and abuse vectors.

## Key Attack Surface Areas

The guide identifies several critical zones: **Operations** (queries, mutations, subscriptions, persisted queries), **Transports** (HTTP POST/GET, WebSocket protocols, multipart uploads), and **Schema Features** (introspection, directives, custom scalars, Relay patterns).

## Primary Vulnerability Classes

**Authorization Bypass** represents the most dangerous category. The document warns that "Parent resolver checks auth, child resolver assumes it's already validated," creating cascade gaps where sensitive data becomes accessible through child fields despite parent-level protections.

**Batching and Alias Abuse** enable enumeration attacks—using multiple aliases in a single request bypasses per-request rate limits while exposing inconsistent authorization between field and request levels.

**Input Manipulation** exploits type confusion, duplicate keys, and unexpected fields to trigger validation bypasses or downstream logic flaws.

## Federation-Specific Risks

Federation architectures introduce cross-subgraph boundaries where gateways enforce authorization but subgraph resolvers may not, enabling IDOR through `_entities` queries.

## Methodology Highlights

The testing approach prioritizes: endpoint fingerprinting, complete schema acquisition, building a principal matrix across roles, field-by-field sweep comparing owned vs. foreign resources, and transport parity verification to ensure HTTP and WebSocket enforce identical controls.
