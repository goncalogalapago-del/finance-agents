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

## Project Docs

- `CONSTITUTION.md`
- `docs/01-mvp-architecture.md`
- `docs/02-domain-model.md`
- `docs/03-adapter-contracts.md`
- `docs/04-workflows-audit.md`
- `docs/05-mvp-backlog.md`

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
