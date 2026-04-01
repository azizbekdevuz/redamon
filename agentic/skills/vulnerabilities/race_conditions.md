# Race Conditions Testing Guide

This document outlines comprehensive strategies for identifying and exploiting concurrency vulnerabilities in web applications.

## Core Concept

"Concurrency bugs enable duplicate state changes, quota bypass, financial abuse, and privilege errors." The framework emphasizes treating all read–modify–write operations as potentially vulnerable to adversarial concurrent access.

## Primary Attack Vectors

**Payment and Financial Systems**
Authentication, capture, refund, and void operations are high-value targets, as are credit issuance and loyalty points.

**Single-Use Controls**
Coupons, discount codes, and one-time tokens become vulnerable when concurrent requests can bypass consumption checks.

**Quota Enforcement**
API rate limits and inventory reservations frequently fail when protection mechanisms operate only at system edges rather than within transactional boundaries.

## Testing Approach

The methodology involves five key stages: modeling invariants, mapping read/write locations, establishing baselines with single requests, issuing synchronized parallel requests, and scaling concurrency levels. The guide emphasizes HTTP/2 multiplexing and "last-byte synchronization: hold requests open and release final byte simultaneously" for precise timing control.

## Critical Validation Points

Valid findings require demonstrating that sequential requests fail while concurrent ones succeed, with durable state changes persisting across restarts. Cross-channel testing (REST, GraphQL, WebSocket) strengthens evidence of widespread vulnerability.

## Key Insight

Fundamental protection requires atomicity at the database level, proper isolation levels, and idempotency enforcement across all mutation pathways—not just selective endpoints.
