from app.adapters.contracts import ReadOnlyFinanceAdapter
from app.adapters.csv.lunar_csv import LunarCsvReadOnlyAdapter
from app.adapters.csv.saxo_csv import SaxoCsvReadOnlyAdapter
from app.adapters.fallback import FallbackReadOnlyAdapter
from app.adapters.fixture import FixtureReadOnlyAdapter
from app.adapters.lunar_read_only import LunarReadOnlyAdapter
from app.adapters.saxo_read_only import SaxoReadOnlyAdapter
from app.core.config import get_settings


def build_adapter_registry() -> dict[str, ReadOnlyFinanceAdapter]:
    settings = get_settings()
    registry: dict[str, ReadOnlyFinanceAdapter] = {
        "fixture": FixtureReadOnlyAdapter(),
    }
    if settings.saxo_access_token:
        saxo_api_adapter: ReadOnlyFinanceAdapter = SaxoReadOnlyAdapter(
            base_url=settings.saxo_base_url,
            access_token=settings.saxo_access_token,
        )
        if settings.saxo_csv_dir:
            saxo_csv_adapter = SaxoCsvReadOnlyAdapter(csv_dir=settings.saxo_csv_dir)
            registry["saxo"] = FallbackReadOnlyAdapter(
                primary=saxo_api_adapter,
                fallback=saxo_csv_adapter,
            )
        else:
            registry["saxo"] = saxo_api_adapter
    elif settings.saxo_csv_dir:
        registry["saxo"] = SaxoCsvReadOnlyAdapter(csv_dir=settings.saxo_csv_dir)

    if settings.lunar_access_token:
        lunar_api_adapter: ReadOnlyFinanceAdapter = LunarReadOnlyAdapter(
            base_url=settings.lunar_base_url,
            access_token=settings.lunar_access_token,
            device_id=settings.lunar_device_id,
            os_name=settings.lunar_os,
        )
        if settings.lunar_csv_dir:
            lunar_csv_adapter = LunarCsvReadOnlyAdapter(csv_dir=settings.lunar_csv_dir)
            registry["lunar"] = FallbackReadOnlyAdapter(
                primary=lunar_api_adapter,
                fallback=lunar_csv_adapter,
            )
        else:
            registry["lunar"] = lunar_api_adapter
    elif settings.lunar_csv_dir:
        registry["lunar"] = LunarCsvReadOnlyAdapter(csv_dir=settings.lunar_csv_dir)

    return registry
