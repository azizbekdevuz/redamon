# XSS Testing Guide Summary

This comprehensive resource covers Cross-Site Scripting vulnerabilities across reflected, stored, and DOM-based vectors. Here are the key takeaways:

## Core Principles

The document emphasizes that "context, parser, and framework edges are complex." Every user-influenced string requires strict encoding matched to its specific sink and runtime policy protection (CSP/Trusted Types).

## Testing Approach

The methodology prioritizes:
1. Identifying data sources (URLs, postMessage, storage)
2. Tracing flow to sinks (innerHTML, eval, event handlers)
3. Classifying the execution context (HTML, attribute, JavaScript, CSS, SVG)
4. Assessing existing defenses
5. Crafting minimal, context-appropriate payloads

## Critical Contexts

The guide highlights that "SVG/MathML" should be "treated as active content" with separate testing, and frameworks like React require attention to `dangerouslySetInnerHTML` sinks.

## Validation Standards

Effective findings require:
- Minimal payloads with clear before/after DOM evidence
- Cross-browser execution demonstration
- Proven bypass of stated defenses
- Impact beyond simple alerts (token theft, CSRF chains, persistence)

## Defense Mechanisms

Proper protections include output encoding matched to context, CSP with nonces/hashes, Trusted Types enforcement, and tools like DOMPurify configured strictly.

The resource concludes that "context + sink decide execution" and emphasizes validation over payload quantity.
