# Subdomain Takeover: Key Takeaways

## Core Concept
"Subdomain takeover lets an attacker serve content from a trusted subdomain by claiming resources referenced by dangling DNS" or misconfigured cloud resources.

## Primary Attack Vectors

The document identifies several exploitation paths:
- Orphaned DNS records (CNAME/A/ALIAS/NS) pointing to unclaimed third-party services
- Decommissioned integrations still referenced in DNS
- CDN alternate domain mappings lacking ownership verification
- Storage endpoints and static hosting without proper claims

## Detection Methodology

The reconnaissance approach combines:
- Subdomain enumeration via certificate transparency and passive DNS
- DNS resolution across record types to identify external endpoints
- HTTP fingerprinting for provider-specific "unclaimed resource" signatures
- TLS certificate inspection for hostname mismatches

## Claiming Resources

Successful takeover typically requires creating the missing resource with the exact required name on the third-party platform—whether that's an S3 bucket, GitHub Pages repository, or CDN distribution.

## Validation Process

Proper confirmation involves documenting the before-state (DNS records and HTTP responses), then serving unique content post-claim and accessing it via HTTPS to demonstrate control.

## Risk Mitigation

The guidance emphasizes treating subdomain safety as a lifecycle concern: "if DNS points at anything, you must own and verify the thing on every provider and product path."
