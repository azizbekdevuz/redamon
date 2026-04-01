# Broken Function Level Authorization (BFLA) – Summary

**BFLA** represents action-level authorization failures where callers invoke functions they lack entitlement for. The core principle: "Bind subject × action at the service that performs the action."

## Key Vulnerability Categories

**Vertical Escalation**
Unprivileged users reach admin-only endpoints. "Privileged/admin/staff-only actions reachable by basic users" exemplify this surface.

**Transport Inconsistency**
Different protocols enforce checks unevenly. REST, GraphQL, gRPC, and WebSocket may have misaligned authorization logic, allowing bypass via alternate transports.

**Gateway Trust Issues**
Backends incorrectly rely on injected headers like X-User-Id without validating underlying tokens, enabling header spoofing.

**High-Impact Actions at Risk**
Role changes, financial approvals, data deletion, security overrides, and license modifications are frequent targets.

## Testing Strategy

The methodology involves:
1. Building an actor-by-action matrix across privilege levels
2. Obtaining credentials for each role
3. Testing every action via multiple transports and encodings
4. Varying identity headers and tenant selectors
5. Validating background job authorization

## Critical Enforcement Points

- Function-level checks must occur at service boundaries, not delegated to UI or gateways
- Each microservice must re-validate authorization independently
- Per-message validation applies to WebSocket and streaming protocols
- Batch operations and background jobs require per-action verification

**Validation requires** demonstrating privilege escalation across multiple transports or encodings with before/after state proof.
