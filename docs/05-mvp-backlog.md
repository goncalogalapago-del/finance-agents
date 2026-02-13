# MVP v0 Backlog and Delivery Plan

## Milestone 1 - Platform Skeleton

1. Bootstrap FastAPI project, settings, dependency injection.
2. Set up Postgres + Alembic baseline migrations.
3. Add append-only audit event writer.
4. Add CI: ruff, mypy, pytest, dependency scan.

Acceptance criteria:
- App starts locally and DB migrations apply.
- CI blocks on lint/type/test/security failures.

## Milestone 2 - Integrations (Read-Only)

1. Implement adapter interface and shared retry/rate-limit client.
2. Implement `SaxoReadOnlyAdapter` API pull.
3. Implement `LunarReadOnlyAdapter` API pull.
4. Implement CSV fallback importers for Saxo and Lunar.
5. Add ingestion jobs with idempotent upserts.

Acceptance criteria:
- Balances/positions/transactions ingest into canonical schema.
- Read-only scope validation enforced and audited.

## Milestone 3 - Deterministic Analytics

1. Portfolio analytics engine (allocation, drift, concentration, perf).
2. Risk engine (volatility proxy, drawdown, FX exposure, simple stress).
3. Tax estimator (monthly/YTD, dividends/interest, realized gains/losses).
4. Data quality checks and freshness flags.

Acceptance criteria:
- Deterministic outputs for identical inputs.
- Unit and integration tests cover core calculations.

## Milestone 4 - Proposals and Approvals

1. Proposal generator with contribution rules + drift logic.
2. Enforce instrument allowlist and risk limits.
3. Approval token service (short TTL JWT + nonce + idempotency).
4. Approval/rejection endpoints and state transitions.
5. Kill switch support.

Acceptance criteria:
- Proposals are created but never executed.
- Invalid/expired/replayed approvals are rejected and audited.

## Milestone 5 - Reporting and Narrative

1. Monthly report composer (snapshot, risk, tax, proposals).
2. Macro/geopolitics digest pipeline mapped to exposures.
3. Email delivery integration.
4. Optional Slack summary delivery.

Acceptance criteria:
- Monthly report delivered with deterministic metrics and narrative sections.
- Macro narrative references deterministic exposure outputs.

## Milestone 6 - Hardening and Ops

1. Observability: structured logging and job metrics.
2. Backfill/re-run tooling by period.
3. Runbooks for incident handling and degraded mode.
4. Security review against constitution requirements.

Acceptance criteria:
- Re-runs are idempotent.
- Audit trail complete for ingest/report/proposal lifecycle.

## Initial API Surface (MVP)

- `POST /jobs/ingestion/run`
- `POST /jobs/monthly-close/run`
- `GET /portfolio/snapshot?period=YYYY-MM`
- `GET /risk/summary?period=YYYY-MM`
- `GET /tax/estimate?period=YYYY-MM`
- `GET /proposals?period=YYYY-MM`
- `POST /proposals/{proposal_id}/approve`
- `POST /proposals/{proposal_id}/reject`
- `POST /system/kill-switch/{enabled}`

