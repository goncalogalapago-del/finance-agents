from app.adapters.contracts import ReadOnlyFinanceAdapter
from app.adapters.fixture import FixtureReadOnlyAdapter


def build_adapter_registry() -> dict[str, ReadOnlyFinanceAdapter]:
    return {
        "fixture": FixtureReadOnlyAdapter(),
    }
