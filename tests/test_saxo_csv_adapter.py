from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.csv.saxo_csv import SaxoCsvReadOnlyAdapter


def test_validate_read_only_scope_requires_accounts_csv(tmp_path: Path) -> None:
    adapter = SaxoCsvReadOnlyAdapter(csv_dir=str(tmp_path))

    with pytest.raises(ValueError, match=r"accounts\.csv"):
        adapter.validate_read_only_scope()


def test_validate_read_only_scope_requires_existing_directory(tmp_path: Path) -> None:
    adapter = SaxoCsvReadOnlyAdapter(csv_dir=str(tmp_path / "does-not-exist"))

    with pytest.raises(ValueError, match="directory does not exist"):
        adapter.validate_read_only_scope()


def test_csv_adapter_maps_records_and_filters_by_since(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "accounts.csv",
        (
            "external_account_id,account_label,account_type,base_currency\n"
            "A1,Main,brokerage,USD\n"
        ),
    )
    _write_file(
        tmp_path / "balances.csv",
        (
            "external_account_id,as_of_utc,currency,balance_amount,available_amount\n"
            "A1,2025-12-31T23:00:00Z,USD,99.99,88.88\n"
            "A1,2026-01-31T12:00:00Z,USD,1000.50,250.25\n"
        ),
    )
    _write_file(
        tmp_path / "positions.csv",
        (
            "external_account_id,instrument_ref,as_of_utc,quantity,avg_cost,market_price,market_value\n"
            "A1,US0378331005,2026-01-31T12:00:00Z,10,150.00,180.00,1800.00\n"
        ),
    )
    _write_file(
        tmp_path / "transactions.csv",
        (
                "external_account_id,external_txn_id,txn_type,trade_side,instrument_ref,"
                "executed_at_utc,settled_at_utc,quantity,price,gross_amount,fee_amount,tax_amount,"
                "net_amount,currency,raw_category\n"
                "A1,T1,dividend,,US0378331005,2026-01-29T12:00:00Z,2026-01-30T12:00:00Z,,,10.00,0.00,1.50,8.50,USD,cash_dividend\n"
            ),
        )

    adapter = SaxoCsvReadOnlyAdapter(csv_dir=str(tmp_path))
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)

    adapter.validate_read_only_scope()
    accounts = adapter.list_accounts()
    balances = adapter.fetch_balances(since_utc)
    positions = adapter.fetch_positions(since_utc)
    transactions = adapter.fetch_transactions(since_utc)

    assert len(accounts) == 1
    assert accounts[0].external_account_id == "A1"
    assert accounts[0].base_currency == "USD"

    assert len(balances) == 1
    assert balances[0].as_of_utc == datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc)
    assert balances[0].balance_amount == Decimal("1000.50")

    assert len(positions) == 1
    assert positions[0].instrument_ref == "US0378331005"
    assert positions[0].market_value == Decimal("1800.00")

    assert len(transactions) == 1
    assert transactions[0].external_txn_id == "T1"
    assert transactions[0].net_amount == Decimal("8.50")
    assert transactions[0].trade_side is None


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_csv_adapter_returns_empty_lists_for_missing_data_files(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "accounts.csv",
        (
            "external_account_id,account_label,account_type,base_currency\n"
            "A1,Main,brokerage,USD\n"
        ),
    )
    adapter = SaxoCsvReadOnlyAdapter(csv_dir=str(tmp_path))
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert adapter.fetch_balances(since_utc) == []
    assert adapter.fetch_positions(since_utc) == []
    assert adapter.fetch_transactions(since_utc) == []


def test_csv_adapter_filters_out_older_positions_and_transactions(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "accounts.csv",
        (
            "external_account_id,account_label,account_type,base_currency\n"
            "A1,Main,brokerage,USD\n"
        ),
    )
    _write_file(
        tmp_path / "positions.csv",
        (
            "external_account_id,instrument_ref,as_of_utc,quantity,avg_cost,market_price,market_value\n"
            "A1,US0378331005,2025-01-31T12:00:00Z,10,150.00,180.00,1800.00\n"
        ),
    )
    _write_file(
        tmp_path / "transactions.csv",
        (
            "external_account_id,external_txn_id,txn_type,trade_side,instrument_ref,"
            "executed_at_utc,settled_at_utc,quantity,price,gross_amount,fee_amount,tax_amount,"
            "net_amount,currency,raw_category\n"
            "A1,T1,dividend,,US0378331005,2025-01-30T12:00:00Z,2025-01-31T12:00:00Z,,,10.00,0.00,1.50,8.50,USD,cash_dividend\n"
        ),
    )
    adapter = SaxoCsvReadOnlyAdapter(csv_dir=str(tmp_path))
    since_utc = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert adapter.fetch_positions(since_utc) == []
    assert adapter.fetch_transactions(since_utc) == []


def test_csv_helper_methods_validate_and_normalize() -> None:
    assert SaxoCsvReadOnlyAdapter._optional_str(None) is None
    assert SaxoCsvReadOnlyAdapter._optional_datetime(None) is None
    assert SaxoCsvReadOnlyAdapter._normalize_utc(datetime(2026, 1, 1)) == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
    assert SaxoCsvReadOnlyAdapter._datetime("2026-01-01T12:00:00") == datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )

    with pytest.raises(ValueError, match="missing required column"):
        SaxoCsvReadOnlyAdapter._required_str({}, "currency")

    with pytest.raises(ValueError, match="empty value"):
        SaxoCsvReadOnlyAdapter._required_str({"currency": " "}, "currency")

    with pytest.raises(ValueError, match="Invalid decimal value"):
        SaxoCsvReadOnlyAdapter._decimal("abc")

    with pytest.raises(ValueError, match="Invalid currency code"):
        SaxoCsvReadOnlyAdapter._currency("US")
