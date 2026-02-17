from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.csv.santander_totta_csv import SantanderTottaCsvReadOnlyAdapter


def test_validate_read_only_scope_requires_accounts_csv(tmp_path: Path) -> None:
    adapter = SantanderTottaCsvReadOnlyAdapter(csv_dir=str(tmp_path))

    with pytest.raises(ValueError, match=r"accounts\.csv"):
        adapter.validate_read_only_scope()


def test_csv_adapter_maps_records_and_filters_by_since(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "accounts.csv",
        (
            "external_account_id,account_label,account_type,base_currency\n"
            "A1,Conta Ordem,bank,EUR\n"
        ),
    )
    _write_file(
        tmp_path / "balances.csv",
        (
            "external_account_id,as_of_utc,currency,balance_amount,available_amount\n"
            "A1,2025-12-31T23:00:00Z,EUR,99.99,88.88\n"
            "A1,2026-01-31T12:00:00Z,EUR,1000.50,250.25\n"
        ),
    )
    _write_file(
        tmp_path / "transactions.csv",
        (
            "external_account_id,external_txn_id,txn_type,executed_at_utc,settled_at_utc,"
            "gross_amount,fee_amount,tax_amount,net_amount,currency,raw_category\n"
            "A1,T1,withdrawal,2026-01-29T12:00:00Z,2026-01-30T12:00:00Z,"
            "-10.00,0.00,0.00,-10.00,EUR,card\n"
        ),
    )

    adapter = SantanderTottaCsvReadOnlyAdapter(csv_dir=str(tmp_path))
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)

    adapter.validate_read_only_scope()
    accounts = adapter.list_accounts()
    balances = adapter.fetch_balances(since_utc)
    positions = adapter.fetch_positions(since_utc)
    transactions = adapter.fetch_transactions(since_utc)

    assert len(accounts) == 1
    assert accounts[0].external_account_id == "A1"
    assert accounts[0].base_currency == "EUR"

    assert len(balances) == 1
    assert balances[0].as_of_utc == datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc)
    assert balances[0].balance_amount == Decimal("1000.50")

    assert positions == []

    assert len(transactions) == 1
    assert transactions[0].external_txn_id == "T1"
    assert transactions[0].net_amount == Decimal("-10.00")
    assert transactions[0].currency == "EUR"


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
