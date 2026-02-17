from __future__ import annotations

from app.adapters.contracts import ReadOnlyFinanceAdapter
from app.adapters.csv.lunar_csv import LunarCsvReadOnlyAdapter
from app.adapters.csv.santander_totta_csv import SantanderTottaCsvReadOnlyAdapter
from app.adapters.csv.saxo_csv import SaxoCsvReadOnlyAdapter
from app.adapters.facade import ProviderDescriptor, ProviderFacade, ProviderMode
from app.adapters.fallback import FallbackReadOnlyAdapter
from app.adapters.fixture import FixtureReadOnlyAdapter
from app.adapters.lunar_read_only import LunarReadOnlyAdapter
from app.adapters.santander_totta_read_only import SantanderTottaReadOnlyAdapter
from app.adapters.saxo_read_only import SaxoReadOnlyAdapter
from app.core.config import get_settings


def build_provider_facade() -> ProviderFacade:
    settings = get_settings()
    adapters: dict[str, ReadOnlyFinanceAdapter] = {}
    descriptors: dict[str, ProviderDescriptor] = {}

    _add_provider(
        adapters=adapters,
        descriptors=descriptors,
        source="fixture",
        adapter=FixtureReadOnlyAdapter(),
        mode=ProviderMode.FIXTURE,
    )

    _register_provider_with_csv_fallback(
        adapters=adapters,
        descriptors=descriptors,
        source="saxo",
        api_adapter=(
            SaxoReadOnlyAdapter(
                base_url=settings.saxo_base_url,
                access_token=settings.saxo_access_token,
            )
            if settings.saxo_access_token
            else None
        ),
        csv_adapter=(
            SaxoCsvReadOnlyAdapter(csv_dir=settings.saxo_csv_dir)
            if settings.saxo_csv_dir
            else None
        ),
    )

    _register_provider_with_csv_fallback(
        adapters=adapters,
        descriptors=descriptors,
        source="lunar",
        api_adapter=(
            LunarReadOnlyAdapter(
                base_url=settings.lunar_base_url,
                access_token=settings.lunar_access_token,
                device_id=settings.lunar_device_id,
                os_name=settings.lunar_os,
            )
            if settings.lunar_access_token
            else None
        ),
        csv_adapter=(
            LunarCsvReadOnlyAdapter(csv_dir=settings.lunar_csv_dir)
            if settings.lunar_csv_dir
            else None
        ),
    )

    _register_provider_with_csv_fallback(
        adapters=adapters,
        descriptors=descriptors,
        source="santander_totta",
        api_adapter=(
            SantanderTottaReadOnlyAdapter(
                base_url=settings.santander_totta_base_url,
                access_token=settings.santander_totta_access_token,
            )
            if settings.santander_totta_access_token
            else None
        ),
        csv_adapter=(
            SantanderTottaCsvReadOnlyAdapter(csv_dir=settings.santander_totta_csv_dir)
            if settings.santander_totta_csv_dir
            else None
        ),
    )

    return ProviderFacade(adapters=adapters, descriptors=descriptors)


def build_adapter_registry() -> dict[str, ReadOnlyFinanceAdapter]:
    return build_provider_facade().registry()


def _register_provider_with_csv_fallback(
    *,
    adapters: dict[str, ReadOnlyFinanceAdapter],
    descriptors: dict[str, ProviderDescriptor],
    source: str,
    api_adapter: ReadOnlyFinanceAdapter | None,
    csv_adapter: ReadOnlyFinanceAdapter | None,
) -> None:
    if api_adapter and csv_adapter:
        _add_provider(
            adapters=adapters,
            descriptors=descriptors,
            source=source,
            adapter=FallbackReadOnlyAdapter(primary=api_adapter, fallback=csv_adapter),
            mode=ProviderMode.FALLBACK,
        )
    elif api_adapter:
        _add_provider(
            adapters=adapters,
            descriptors=descriptors,
            source=source,
            adapter=api_adapter,
            mode=ProviderMode.API,
        )
    elif csv_adapter:
        _add_provider(
            adapters=adapters,
            descriptors=descriptors,
            source=source,
            adapter=csv_adapter,
            mode=ProviderMode.CSV,
        )


def _add_provider(
    *,
    adapters: dict[str, ReadOnlyFinanceAdapter],
    descriptors: dict[str, ProviderDescriptor],
    source: str,
    adapter: ReadOnlyFinanceAdapter,
    mode: ProviderMode,
) -> None:
    adapters[source] = adapter
    descriptors[source] = ProviderDescriptor(
        source=source,
        provider_code=adapter.provider_code,
        institution_kind=adapter.institution_kind,
        mode=mode,
        capabilities=adapter.capabilities,
    )
