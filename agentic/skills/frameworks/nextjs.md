# Next.js Security Testing Playbook Summary

This comprehensive guide addresses vulnerabilities in Next.js applications across multiple attack vectors:

## Core Attack Surface
The documentation identifies critical areas including coexisting routers (App and Pages), dual runtimes (Node.js and Edge), caching mechanisms, and various data paths including Server Components and Server Actions.

## Major Vulnerability Categories

**Middleware Bypass**: The guide notes that "Middleware may normalize differently than route handlers" through techniques like path traversal, double slashes, and parameter pollution.

**Server Actions**: Authorization gaps exist where actions rely on client-side state rather than server-side verification, enabling IDOR attacks.

**Caching Issues**: "User-bound data cached without identity keys" creates scenarios where personalized content reaches unintended users through shared caches.

**Authentication Weaknesses**: NextAuth vulnerabilities include missing CSRF protections and open redirect risks in callback URL handling.

**Data Exposure**: The guide highlights "__NEXT_DATA__ Over-fetching" where server data passes to clients with unnecessary sensitive fields included.

**Image Optimizer SSRF**: Broad domain patterns enable server-side request forgery against internal infrastructure.

## Testing Methodology
The approach involves systematic enumeration via build artifacts and source maps, runtime matrix testing, role-based access verification, cache boundary validation, and cross-router authorization comparison.

**Validation requirements** demand concrete proof: side-by-side requests showing unauthorized access, ETag collisions, and explicit middleware bypass demonstrations.
