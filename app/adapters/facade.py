from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from app.adapters.contracts import AdapterCapabilities, InstitutionKind, ReadOnlyFinanceAdapter


class ProviderMode(str, Enum):
    API = "api"
    CSV = "csv"
    FALLBACK = "fallback"
    FIXTURE = "fixture"


@dataclass(frozen=True)
class ProviderDescriptor:
    source: str
    provider_code: str
    institution_kind: InstitutionKind
    mode: ProviderMode
    capabilities: AdapterCapabilities


class ProviderFacade:
    """Provider-agnostic access layer over concrete adapter instances."""

    def __init__(
        self,
        *,
        adapters: Mapping[str, ReadOnlyFinanceAdapter],
        descriptors: Mapping[str, ProviderDescriptor] | None = None,
    ) -> None:
        self._adapters = dict(adapters)
        self._descriptors = dict(descriptors or {})

    def registry(self) -> dict[str, ReadOnlyFinanceAdapter]:
        return dict(self._adapters)

    def source_names(self) -> list[str]:
        return sorted(self._adapters.keys())

    def get_adapter(self, source: str) -> ReadOnlyFinanceAdapter | None:
        return self._adapters.get(source)

    def describe(self, source: str) -> ProviderDescriptor | None:
        return self._descriptors.get(source)

    def list_descriptors(self) -> list[ProviderDescriptor]:
        names = sorted(self._descriptors.keys())
        return [self._descriptors[name] for name in names]
