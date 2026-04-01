# Supabase Security Testing Guide

This document provides a comprehensive framework for assessing Supabase application security, covering six primary attack vectors:

## Core Vulnerability Categories

**Data Access Layer**: The guide emphasizes that PostgREST endpoints expose table CRUD operations, remote procedure calls, and GraphQL interfaces. The architecture relies on JWT-based authorization headers to establish user context through `auth.uid()`.

**Critical Principle**: "auth.uid() returns current user UUID from JWT. Policies must never trust client-supplied IDs over server context." This foundational concept underpins all security testing.

## High-Impact Testing Areas

Row Level Security (RLS) gaps represent the most frequently exploited vulnerability class. Common failures include:

- Incomplete policy coverage (SELECT protected but UPDATE/DELETE open)
- Missing tenant isolation filters
- Reliance on client-provided values instead of JWT context
- Policy evaluation timing issues enabling inference attacks

Storage misconfigurations frequently expose sensitive files through:
- Overly permissive bucket policies
- Signed URL reuse patterns
- Content-type handling bypasses allowing script execution

## Testing Approach

The methodology emphasizes building a "principal × resource × action" matrix across all surfaces (REST, GraphQL, Realtime, Storage, Edge Functions). Key techniques include:

- Comparing response metadata (counts, ETags) to infer unauthorized data existence
- Testing policy enforcement consistency between transport protocols
- Validating tenant isolation through header/parameter manipulation
- Verifying JWT claims (issuer, audience, expiration) aren't bypassed by service keys

The guide stresses documenting minimal reproducible requests with explicit role contexts for validation.
