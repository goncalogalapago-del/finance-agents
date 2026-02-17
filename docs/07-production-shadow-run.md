# Production Shadow Run (Milestone 2)

## Goal

Run real-source ingestion safely in shadow mode (read-only source pulls, canonical persistence, no execution workflow).

## Preconditions

1. App is running locally or in staging.
2. DB migrations are applied:
   - `alembic upgrade head`
3. Configure source credentials:
   - API mode: `SAXO_ACCESS_TOKEN` (and optional `SAXO_BASE_URL`)
   - CSV mode: `SAXO_CSV_DIR` with `accounts.csv` and optional `balances.csv`, `positions.csv`, `transactions.csv`
   - API mode: `LUNAR_ACCESS_TOKEN` (and optional `LUNAR_BASE_URL`, `LUNAR_DEVICE_ID`, `LUNAR_OS`)
   - CSV mode: `LUNAR_CSV_DIR` with `accounts.csv` and optional `balances.csv`, `positions.csv`, `transactions.csv`
4. Keep `KILL_SWITCH_ENABLED=true` in production environments until proposal workflow rollout.

## Step 1: Preflight

Validate adapter readiness and read-only scope:

```bash
make preflight
```

Expected statuses:
- `READY`: all selected sources are ready
- `DEGRADED`: at least one source failed preflight
- `FAILED`: all selected sources failed preflight

## Step 2: Shadow Ingestion

Run all configured sources:

```bash
make ingest-all
```

Or run only Saxo:

```bash
make ingest-saxo
```

Or run only Lunar:

```bash
make ingest-lunar
```

Expected run statuses:
- `SUCCESS`: all selected sources ingested successfully
- `DEGRADED`: partial failure, at least one source ingested
- `FAILED`: all selected sources failed

## Step 3: Verify Persistence and Audit

1. Confirm `ingestion_runs` row exists for the run id.
2. Confirm `audit_events` includes:
   - `INGESTION_PULL_STARTED`
   - `INGESTION_PULL_COMPLETED` or `INGESTION_PULL_FAILED`
3. Confirm canonical upserts:
   - `accounts`, `balances`, `positions`, `transactions`

## Rollback / Mitigation

If production-source ingestion is unstable:

1. Disable Saxo API source:
   - unset `SAXO_ACCESS_TOKEN`
2. Disable Saxo CSV source:
   - unset `SAXO_CSV_DIR`
3. Keep fixture-only ingestion:
   - run with `{"source":"fixture"}`

These steps keep ingestion operable while isolating provider instability.
