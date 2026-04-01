# Business Logic Flaws: Key Security Concepts

Based on the provided documentation, business logic flaws represent a critical attack surface where adversaries exploit intended functionality to violate domain invariants.

## Core Definition

The resource defines business logic flaws as attacks that "move money without paying, exceed limits, retain privileges, or bypass reviews" by requiring understanding of business operations rather than just technical payloads.

## Primary Attack Categories

The document identifies several high-value vulnerability areas:

- **Financial operations**: pricing, discounts, payments, refunds, and chargebacks
- **Account management**: lifecycle transitions, trial periods, and privilege changes
- **Authorization weaknesses**: feature gates and approval workflow bypasses
- **Resource constraints**: quotas, inventory, and entitlement limits
- **Isolation failures**: cross-tenant data or action leakage

## Testing Framework

The methodology emphasizes:

1. Mapping state machines and documenting invariants
2. Testing transition skipping, reordering, and repetition
3. Introducing variance through timing and concurrency
4. Validating enforcement across all system boundaries

## Critical Insight

"If any step trusts the client or prior steps, expect abuse." This principle underscores that server-side recomputation and validation at every transition point is essential.

The document stresses proving durable state violations with observable evidence in authoritative sources, distinguishing genuine vulnerabilities from benign promotional or visual inconsistencies.
