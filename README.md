# finance-agents

Backend-only personal finance operations system (MVP v0).

## Current Status

Milestone 1 scaffold is in place:
- FastAPI app with `/health`
- Postgres/Alembic baseline
- Canonical initial migration
- Append-only audit event service
- CI for lint/type/test/dependency audit

Milestone 2 (step 1) is in place:
- Read-only adapter contracts
- Shared retry/rate-limit HTTP client wrapper
- Deterministic fixture adapter for ingestion wiring
- `POST /jobs/ingestion/run` endpoint
- Ingestion run + audit event tests

Milestone 2 (current) additions:
- Canonical idempotent upserts for accounts, balances, positions, transactions
- `source=all` orchestration with `SUCCESS` / `DEGRADED` / `FAILED` status semantics
- Saxo read-only API adapter (scope validation + pagination + DTO mapping)
- Saxo CSV fallback adapter + fallback registry wiring
- Lunar read-only API adapter (scope validation + account/transaction mapping)
- Lunar CSV fallback adapter + fallback registry wiring
- `POST /jobs/ingestion/preflight` readiness endpoint

## Project Docs

- `CONSTITUTION.md`
- `docs/01-mvp-architecture.md`
- `docs/02-domain-model.md`
- `docs/03-adapter-contracts.md`
- `docs/04-workflows-audit.md`
- `docs/05-mvp-backlog.md`
- `docs/06-agent-interaction-spec.md`
- `docs/07-production-shadow-run.md`

## Quick Start

1. Create venv and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

2. Set environment:
```bash
cp .env.example .env
```

3. Run API:
```bash
uvicorn app.main:app --reload
```

4. Run quality checks:
```bash
make lint
make typecheck
make test
```

## Database Migrations

Run migrations with:
```bash
alembic upgrade head
```

## Try Ingestion Endpoint

Run:
```bash
curl -X POST "http://127.0.0.1:8000/jobs/ingestion/run" \
  -H "Content-Type: application/json" \
  -d '{"source":"fixture"}'
```

## Natural Language Interaction

List personas:
```bash
curl "http://127.0.0.1:8000/agents/personas"
```

Create interaction over API:
```bash
curl -X POST "http://127.0.0.1:8000/agents/interactions" \
  -H "Content-Type: application/json" \
  -d '{"channel":"api","conversation_id":"demo-1","message":"Summarize risk for this month"}'
```

CLI:
```bash
finance-agents personas
finance-agents ask "Summarize risk for this month"
```

Slack channel adapter (webhook-style):
```bash
curl -X POST "http://127.0.0.1:8000/channels/slack/interactions" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"U123","channel_id":"C123","text":"What is my tax estimate?"}'
```

Email channel adapter (inbound-style):
```bash
curl -X POST "http://127.0.0.1:8000/channels/email/interactions" \
  -H "Content-Type: application/json" \
  -d '{"from_email":"user@example.com","subject":"Portfolio check","body":"How is my allocation drift?"}'
```

## Production Shadow Run

1. Configure `.env` with either:
- `SAXO_ACCESS_TOKEN` (+ optional `SAXO_BASE_URL`)
- or `SAXO_CSV_DIR` for CSV fallback
- `LUNAR_ACCESS_TOKEN` (+ optional `LUNAR_BASE_URL`, `LUNAR_DEVICE_ID`, `LUNAR_OS`)
- or `LUNAR_CSV_DIR` for CSV fallback

2. Preflight configured sources:
```bash
make preflight
```

3. Run ingestion (all configured sources):
```bash
make ingest-all
```

Run Lunar only:
```bash
make ingest-lunar
```

See `/Users/goncalo.alvarez/Documents/finance-agents/docs/07-production-shadow-run.md` for detailed rollout.
