from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.csv.lunar_csv import LunarCsvReadOnlyAdapter
from app.adapters.csv.saxo_csv import SaxoCsvReadOnlyAdapter
from app.adapters.fallback import FallbackReadOnlyAdapter
from app.adapters.lunar_read_only import LunarReadOnlyAdapter
from app.adapters.registry import build_adapter_registry
from app.adapters.saxo_read_only import SaxoReadOnlyAdapter
from app.core.config import get_settings


def test_registry_uses_fallback_when_token_and_csv_are_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_accounts_csv(tmp_path)
    monkeypatch.setenv("SAXO_ACCESS_TOKEN", "configured-token")
    monkeypatch.setenv("SAXO_CSV_DIR", str(tmp_path))
    get_settings.cache_clear()

    registry = build_adapter_registry()

    assert "saxo" in registry
    assert isinstance(registry["saxo"], FallbackReadOnlyAdapter)
    get_settings.cache_clear()


def test_registry_uses_csv_adapter_when_only_csv_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_accounts_csv(tmp_path)
    monkeypatch.delenv("SAXO_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("SAXO_CSV_DIR", str(tmp_path))
    get_settings.cache_clear()

    registry = build_adapter_registry()

    assert "saxo" in registry
    assert isinstance(registry["saxo"], SaxoCsvReadOnlyAdapter)
    get_settings.cache_clear()


def test_registry_uses_api_adapter_when_only_token_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAXO_ACCESS_TOKEN", "configured-token")
    monkeypatch.delenv("SAXO_CSV_DIR", raising=False)
    get_settings.cache_clear()

    registry = build_adapter_registry()

    assert "saxo" in registry
    assert isinstance(registry["saxo"], SaxoReadOnlyAdapter)
    get_settings.cache_clear()


def test_registry_uses_lunar_fallback_when_token_and_csv_are_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_accounts_csv(tmp_path)
    monkeypatch.setenv("LUNAR_ACCESS_TOKEN", "configured-token")
    monkeypatch.setenv("LUNAR_CSV_DIR", str(tmp_path))
    get_settings.cache_clear()

    registry = build_adapter_registry()

    assert "lunar" in registry
    assert isinstance(registry["lunar"], FallbackReadOnlyAdapter)
    get_settings.cache_clear()


def test_registry_uses_lunar_csv_adapter_when_only_csv_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_accounts_csv(tmp_path)
    monkeypatch.delenv("LUNAR_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("LUNAR_CSV_DIR", str(tmp_path))
    get_settings.cache_clear()

    registry = build_adapter_registry()

    assert "lunar" in registry
    assert isinstance(registry["lunar"], LunarCsvReadOnlyAdapter)
    get_settings.cache_clear()


def test_registry_uses_lunar_api_adapter_when_only_token_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LUNAR_ACCESS_TOKEN", "configured-token")
    monkeypatch.delenv("LUNAR_CSV_DIR", raising=False)
    get_settings.cache_clear()

    registry = build_adapter_registry()

    assert "lunar" in registry
    assert isinstance(registry["lunar"], LunarReadOnlyAdapter)
    get_settings.cache_clear()


def _write_accounts_csv(tmp_path: Path) -> None:
    (tmp_path / "accounts.csv").write_text(
        "external_account_id,account_label,account_type,base_currency\n"
        "A1,Main,brokerage,USD\n",
        encoding="utf-8",
    )
