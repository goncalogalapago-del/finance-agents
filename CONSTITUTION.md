# Project Constitution

## 1) Safety-First Principle

No action with real financial impact (e.g., order execution, transfers) may be performed without explicit human approval.

The system may propose actions, but never commit them.

## 2) Two-Phase Workflow

All high-impact actions must follow this pattern:

- PROPOSE - the system generates a proposal
- APPROVE - a human explicitly approves
- (Future) EXECUTE - only after approval

Under MVP v0, EXECUTE is out of scope.

Proposals and approvals are tracked with audited events.

## 3) Human in the Loop

High-risk decisions (trade proposals, allocation changes, auto-rebalancing suggestions, etc.) require explicit human confirmation.

LLM components are used only for narrative explanation and summarization, never for making automated operational decisions.

## 4) Least Privilege & Access Control

Each subsystem runs with only the privileges it needs:

- Analytics modules are read-only
- Reporting modules cannot place orders
- Execution modules (future) are isolated and limited

No component may hold credentials beyond its scope.

## 5) Approval Security

Approvals must be protected by:

- Short-lived signed tokens (e.g. JWT with TTL)
- Nonces stored server-side (replay protection)
- Idempotency for all state transitions

Approval links must:

- expire quickly
- be protected from replay
- apply only to the intended proposal

## 6) Instrument Policy & Risk Gates

Only allowlisted instruments (e.g. approved ISINs) can be referenced in proposals.

Proposals must enforce:

- max per-order size
- max daily and monthly turnover

A configurable kill switch must immediately halt approvals and any execution logic.

## 7) Auditability & Traceability

All critical events must be logged to an append-only audit log:

- Proposal created
- Proposal approved
- Proposal rejected
- Proposal expired
- (Future) Execution events

Audit logs must include:

- actor ID
- timestamp
- structured payload
- cryptographic integrity if feasible

## 8) Data Minimization & Privacy

Store only what's necessary for operations, reporting, and audit.

Avoid storing personally identifiable financial data unless required.

Protect sensitive configuration and credentials using secret managers.

Do not commit secrets to the repo.

## 9) Deterministic Core + Narrative Layer

Core calculations (tax estimates, portfolio analytics, risk scores) must be deterministic and testable.

LLM use is confined to narrative generation:

- Monthly reports
- Geopolitical commentary
- Explanation of suggestions

Recommendation narratives must reference deterministic outputs; avoid hallucination.

## 10) Secure Development & Test Requirements

All critical subsystems must have:

- Unit tests
- Integration tests
- Edge case coverage (expiry, invalid tokens, idempotency)
- Security checks (allowlist enforcement, kill switch)

CI must scan for:

- insecure dependencies
- missing tests
- lint/style violations

## 11) No Hidden Automation

The system shall not trigger irreversible actions without approval.

Background automation must be observable and auditable.

## 12) Incremental Progress

Prioritize landing MVP v0 safely over completeness.

MVP v0 scope:

- CSV ingestion
- Deterministic analytics
- Proposal generation
- Email/slack reporting
- Approval capture

Execution integration (broker APIs) is a future phase after stable, audited MVP v0.
