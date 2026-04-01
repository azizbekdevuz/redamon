# Mass Assignment: Security Testing Guide

Mass assignment vulnerabilities occur when APIs bind client-supplied fields directly to models without proper allowlists, potentially enabling privilege escalation and unauthorized state changes.

## Core Attack Vectors

The primary reconnaissance focuses on identifying endpoints with automatic binding—particularly those handling REST/JSON, GraphQL, or form-encoded inputs. As the documentation notes, attackers should map "Controllers with automatic binding (e.g., request.json → model)" and examine "OpenAPI/GraphQL schemas: uncover hidden fields or enums."

Common sensitive fields to test include role/permission attributes, ownership identifiers (userId, ownerId), quota limits, feature flags, and billing parameters. Testing should span multiple encodings and parameter shapes, since "Switch JSON ↔ form-encoded ↔ multipart ↔ text/plain; some code paths only validate one."

## Framework-Specific Risks

Different frameworks have distinct vulnerabilities:

- **Rails**: Misconfigured strong parameters or deep nesting via `accepts_nested_attributes_for`
- **Laravel**: Fillable/guarded configuration errors; empty guards expose all fields
- **Django REST**: Writable nested serializers with insufficient authorization
- **Node.js ORMs**: Schema paths not filtered; `select:false` doesn't prevent writes

## Validation Approach

Effective testing requires capturing baseline responses, building a sensitive-field dictionary per resource, and systematically injecting candidates across transports. Proof involves demonstrating "before/after evidence (response body, subsequent GET, or GraphQL query) proving the forbidden attribute value" with reproducible results across multiple encodings.
