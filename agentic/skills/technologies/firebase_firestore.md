# Firebase / Firestore Security Testing Overview

## Key Vulnerability Categories

The document outlines four primary attack surfaces in Firebase applications:

**Data Stores & Authentication**
Firestore, Realtime Database, and Cloud Storage each have distinct rule engines. "Rules are not filters—a query must include constraints that make the rule true for all returned documents." Common misconfigurations include overly permissive rules like `allow read: if request.auth != null`.

**Server-Side Risks**
Cloud Functions present distinct challenges. While `onCall` functions automatically receive `context.auth`, `onRequest` handlers must manually verify ID tokens. The Admin SDK bypasses all rules entirely, requiring explicit ownership checks in code rather than relying on rule enforcement.

**Tenant Isolation Issues**
Multi-tenant applications frequently fail by trusting client-supplied organization IDs instead of deriving tenant context from server state. The guidance emphasizes: "Bind tenant from server context (membership doc or custom claim), not client payload."

**App Check Limitations**
"App Check is not a substitute for authorization." REST API calls succeed with valid ID tokens regardless of attestation status, and mobile clients can potentially be reverse-engineered to extract credential flows.

## Testing Approach

The methodology prioritizes building a resource-principal-action matrix across all Firebase services, then exercising each combination via both SDK and REST endpoints to identify parity gaps where authorization differs between code paths.
