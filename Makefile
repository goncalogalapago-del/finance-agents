PYTHON ?= python3
API_URL ?= http://127.0.0.1:8000

.PHONY: install install-dev run lint typecheck test audit preflight ingest-all ingest-saxo ingest-lunar

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e .[dev]

run:
	uvicorn app.main:app --reload

lint:
	ruff check .

typecheck:
	mypy app tests

test:
	pytest

audit:
	pip-audit

preflight:
	curl -sS -X POST "$(API_URL)/jobs/ingestion/preflight" \
	  -H "Content-Type: application/json" \
	  -d '{"source":"all"}'

ingest-all:
	curl -sS -X POST "$(API_URL)/jobs/ingestion/run" \
	  -H "Content-Type: application/json" \
	  -d '{"source":"all"}'

ingest-saxo:
	curl -sS -X POST "$(API_URL)/jobs/ingestion/run" \
	  -H "Content-Type: application/json" \
	  -d '{"source":"saxo"}'

ingest-lunar:
	curl -sS -X POST "$(API_URL)/jobs/ingestion/run" \
	  -H "Content-Type: application/json" \
	  -d '{"source":"lunar"}'
