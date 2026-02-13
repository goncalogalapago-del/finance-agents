# Workflows, State Machine, and Audit Events

## Proposal State Machine

States:
- `PROPOSED`
- `APPROVED`
- `REJECTED`
- `EXPIRED`

Rules:
- Initial state is `PROPOSED`.
- Only one terminal state is allowed.
- Approval/rejection requires valid token, nonce, and idempotency key.
- Expired proposals cannot transition.
- No execution transition exists in MVP v0.

## Monthly Orchestration Workflow

1. Start `run_id`.
2. Ingest from Saxo/Lunar adapters (API first, CSV fallback).
3. Persist canonical balances, positions, transactions.
4. Run deterministic portfolio/risk/tax analytics.
5. Generate proposal set with risk gates and allowlist checks.
6. Generate macro commentary narrative from deterministic exposure inputs.
7. Compose monthly report (email; optional Slack).
8. Persist report artifact metadata.
9. Emit completion audit event.

## Minimum Audit Event Types

- `INGESTION_PULL_STARTED`
- `INGESTION_PULL_COMPLETED`
- `INGESTION_PULL_FAILED`
- `ANALYTICS_COMPUTED`
- `PROPOSAL_CREATED`
- `PROPOSAL_APPROVED`
- `PROPOSAL_REJECTED`
- `PROPOSAL_EXPIRED`
- `REPORT_GENERATED`
- `REPORT_DELIVERED`
- `KILL_SWITCH_TOGGLED`

## Event Payload Baseline

Each event stores:
- `event_type`
- `event_time_utc`
- `actor_id` (or `system`)
- `run_id` (if job-scoped)
- `entity_type` / `entity_id`
- `payload` (structured JSON)

Optional integrity chain:
- `prev_hash`
- `event_hash`

## Partial Failure Policy

- Source-level failures do not erase previous valid snapshots.
- Run status `DEGRADED` if at least one source fails but others succeed.
- Reports must disclose missing/stale sources.
- Proposal generation is blocked if required data completeness threshold is unmet.

