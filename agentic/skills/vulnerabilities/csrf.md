# CSRF Testing Guide: Key Takeaways

## Core Vulnerability

Cross-site request forgery exploits a browser's automatic credential submission (cookies, HTTP auth) across origins. The guide emphasizes: "Do not rely on CORS alone; enforce non-replayable tokens and strict origin checks for every state change."

## Primary Attack Vectors

The document identifies several high-impact targets:
- Credential changes (email, password, phone)
- Payment and subscription modifications
- API key/secret generation and rotations
- OAuth connect/disconnect and account deletion
- Administrative actions

## Critical Testing Areas

The methodology prioritizes three defenses:

1. **Anti-CSRF tokens** - Must be validated, non-reusable, and bound to sessions/paths
2. **Origin/Referer verification** - Server should explicitly reject null origins and cross-site requests
3. **SameSite cookie attributes** - Strict/Lax policies prevent automatic credential submission

## Common Bypasses

The guide highlights practical weaknesses:
- GET requests that perform state changes
- Simple content-types (`application/x-www-form-urlencoded`, `text/plain`) bypassing preflight checks
- Method override headers (`_method`) allowing POST-as-DELETE attacks
- Sandbox/iframe navigation producing null Origin headers that frameworks incorrectly accept

## Validation Requirements

Proving CSRF requires demonstrating that a cross-origin page triggers account state changes without legitimate origin verification—across multiple browsers and request contexts.
