# JWT/OIDC Authentication Security Overview

This comprehensive guide addresses vulnerabilities in JWT and OIDC implementations across web, mobile, and API environments.

## Core Threat Model

The document emphasizes that "JWT/OIDC failures often enable token forgery, token confusion, cross-service acceptance, and durable account takeover." The fundamental issue is trusting unvalidated headers, claims, or token signatures without strict binding to issuer, audience, key, and context.

## Primary Attack Vectors

**Signature Exploitation**: Algorithm confusion attacks (RS256 to HS256 downgrade), acceptance of "none" algorithms, and ECDSA verification weaknesses represent initial targets.

**Header Abuse**: The material highlights critical vulnerabilities including kid path traversal, jku/x5u external key loading, jwk header injection, and SSRF via remote key fetching.

**Claims Gaps**: Missing enforcement of issuer, audience, scope, expiration, and token type validation enables cross-service token reuse and privilege escalation.

**OIDC-Specific Issues**: Access token and ID token confusion, PKCE downgrades, state/nonce weaknesses, and device flow misconfigurations.

## Testing Approach

The methodology emphasizes systematic inventory of issuers/consumers, token capture across roles, verification endpoint mapping, and mutation testing of headers and claims. Success requires demonstrating actual cross-context acceptance rather than theoretical vulnerabilities.

## Key Insight

"Verification must bind the token to the correct issuer, audience, key, and client context on every acceptance path." Any missing binding creates exploitable gaps.
