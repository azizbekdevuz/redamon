# SSRF Testing Guide Summary

This document provides comprehensive guidance for identifying and exploiting Server-Side Request Forgery vulnerabilities across cloud, Kubernetes, and internal service environments.

## Key Attack Surfaces

The guide identifies vulnerable endpoints including HTTP/HTTPS fetchers, non-HTTP protocol handlers, and service-to-service communication paths. Common parameters include `url=`, `link=`, `fetch=`, and `webhook=`.

## High-Value Targets

AWS IMDSv1/v2, GCP metadata endpoints, Azure MSI, and Kubernetes kubelet are primary objectives. The document notes: "IMDSv2: requires token via PUT `/latest/api/token` with header `X-aws-ec2-metadata-token-ttl-seconds`" for accessing credentials.

Internal services like Docker, Redis, and Elasticsearch represent secondary targets when accessible through SSRF.

## Exploitation Techniques

**Protocol abuse** leverages gopher, file, and wrapper schemes to interact with raw protocols. **Address encoding** bypasses filters using decimal, hexadecimal, and IPv6 representations. **Redirect chains** exploit timing differences between allowlist validation and actual request execution.

## Testing Approach

The methodology progresses from establishing out-of-band confirmation through OAST callbacks, then systematically testing internal addresses, protocols, and parser differentials.

## Impact Chain

Successful exploitation enables credential theft, lateral movement into Kubernetes clusters, and potential RCE through protocol abuse or daemon access.
