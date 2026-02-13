# MVP v0 Architecture

## Scope and Constraints

This architecture implements the brief under `CONSTITUTION.md`.

Hard constraints:
- Read-only integrations only (Saxo + Lunar primary).
- No execution, transfers, or account-changing actions.
- Deterministic analytics/risk/tax engines.
- LLM limited to narrative/reporting/macro summaries.
- Full auditability for pull/report/proposal/approval lifecycle.

## System Context

External systems:
- Saxo (broker API or CSV fallback) read-only.
- Lunar (bank API or CSV fallback) read-only.
- Email provider for monthly report delivery.
- Optional Slack webhook/bot for summary delivery.

Internal services/modules:
- `integration.adapters` (SaxoReadOnlyAdapter, LunarReadOnlyAdapter, CSV adapters)
- `ingestion.pipeline` (normalize + upsert + idempotency)
- `analytics.portfolio` (allocation, drift, concentration, performance)
- `analytics.risk` (volatility proxy, drawdown, currency exposure, stress)
- `analytics.tax` (monthly/YTD estimate, realized gains/losses, reserve suggestion)
- `suggestions.engine` (proposal generation with risk gates/allowlist)
- `macro.digest` (source collection + LLM narrative mapped to exposure)
- `reporting.composer` (email/slack formatting)
- `orchestrator.jobs` (monthly workflows, optional weekly ingestion)
- `audit.log` (append-only event store)

## Runtime Design

Primary cadence:
- Weekly optional ingestion sync.
- Monthly close job: ingest -> analytics -> proposals -> macro digest -> report -> delivery.

Job model:
- Single orchestrator triggers typed jobs.
- Every job run has `run_id` and writes audit metadata.
- Jobs are idempotent with deterministic re-run behavior by period.

Failure strategy:
- Adapter failures are isolated per source/account.
- Partial failures mark run `DEGRADED`, never corrupt existing state.
- Analytics run only on validated snapshots.
- Reporting includes data freshness and missing-source flags.

## Data Flow (Monthly)

1. Pull balances/holdings/transactions/dividends/interest (API first, CSV fallback).
2. Normalize source payloads into canonical tables.
3. Materialize period snapshot.
4. Compute deterministic analytics/risk/tax outputs.
5. Generate proposal objects (no execution path).
6. Build macro narrative mapped to exposure outputs.
7. Compose and deliver report.
8. Capture approval/reject/expire events for proposals.

## Security Design

- Tokens/scopes restricted to read-only endpoints.
- Secrets stored in secret manager or OS keychain (dev).
- No secret values in logs; structured logs redact sensitive fields.
- API client retries use bounded exponential backoff and rate limiting.
- Approval tokens are short TTL JWTs with server-side nonce tracking.
- Kill switch blocks new approvals globally when enabled.

## Suggested Technical Baseline

- Python 3.12+
- FastAPI + Pydantic
- Postgres 15+
- Alembic migrations
- APScheduler or cron + worker entrypoint
- SMTP provider and optional Slack webhook
- pytest + ruff + mypy + safety/pip-audit in CI

## Deliverables from This Architecture

- Adapter interfaces and provider-specific implementations.
- Canonical schema and migrations.
- Deterministic analytics engines.
- Proposal + approval API surface (no execute endpoint).
- Monthly report job with email delivery.
