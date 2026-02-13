PYTHON ?= python3

.PHONY: install install-dev run lint typecheck test audit

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
