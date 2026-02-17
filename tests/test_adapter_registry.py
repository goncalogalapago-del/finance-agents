from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.csv.lunar_csv import LunarCsvReadOnlyAdapter
from app.adapters.csv.santander_totta_csv import SantanderTottaCsvReadOnlyAdapter
from app.adapters.csv.saxo_csv import SaxoCsvReadOnlyAdapter
from app.adapters.facade import ProviderMode
from app.adapters.fallback import FallbackReadOnlyAdapter
from app.adapters.lunar_read_only import LunarReadOnlyAdapter
from app.adapters.registry import build_adapter_registry, build_provider_facade
from app.adapters.santander_totta_read_only import SantanderTottaReadOnlyAdapter
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


def test_registry_uses_santander_fallback_when_token_and_csv_are_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_accounts_csv(tmp_path)
    monkeypatch.setenv("SANTANDER_TOTTA_ACCESS_TOKEN", "configured-token")
    monkeypatch.setenv("SANTANDER_TOTTA_CSV_DIR", str(tmp_path))
    get_settings.cache_clear()

    registry = build_adapter_registry()

    assert "santander_totta" in registry
    assert isinstance(registry["santander_totta"], FallbackReadOnlyAdapter)
    get_settings.cache_clear()


def test_registry_uses_santander_csv_adapter_when_only_csv_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_accounts_csv(tmp_path)
    monkeypatch.delenv("SANTANDER_TOTTA_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("SANTANDER_TOTTA_CSV_DIR", str(tmp_path))
    get_settings.cache_clear()

    registry = build_adapter_registry()

    assert "santander_totta" in registry
    assert isinstance(registry["santander_totta"], SantanderTottaCsvReadOnlyAdapter)
    get_settings.cache_clear()


def test_registry_uses_santander_api_adapter_when_only_token_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANTANDER_TOTTA_ACCESS_TOKEN", "configured-token")
    monkeypatch.delenv("SANTANDER_TOTTA_CSV_DIR", raising=False)
    get_settings.cache_clear()

    registry = build_adapter_registry()

    assert "santander_totta" in registry
    assert isinstance(registry["santander_totta"], SantanderTottaReadOnlyAdapter)
    get_settings.cache_clear()


def test_provider_facade_exposes_descriptors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUNAR_ACCESS_TOKEN", "configured-token")
    get_settings.cache_clear()

    facade = build_provider_facade()

    assert "fixture" in facade.source_names()
    lunar_descriptor = facade.describe("lunar")
    assert lunar_descriptor is not None
    assert lunar_descriptor.mode == ProviderMode.API
    assert lunar_descriptor.provider_code == "LUNAR"
    get_settings.cache_clear()


def _write_accounts_csv(tmp_path: Path) -> None:
    (tmp_path / "accounts.csv").write_text(
        "external_account_id,account_label,account_type,base_currency\n"
        "A1,Main,brokerage,USD\n",
        encoding="utf-8",
    )
