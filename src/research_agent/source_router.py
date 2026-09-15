from __future__ import annotations

from collections.abc import Iterable
import os

from ..enrichment.providers import (
    CPUMonkeyProvider,
    CPUWorldProvider,
    GeizhalsProvider,
    IcecatProvider,
    ManufacturerProvider,
    PCKomboProvider,
    TechPowerUpProvider,
    WikiChipProvider,
)
from .focused_search import FocusedSearchResolver


_PROVIDER_FACTORIES = {
    "FABRICANTE_OFICIAL": ManufacturerProvider,
    "ICECAT": IcecatProvider,
    "CPU_MONKEY": CPUMonkeyProvider,
    "CPU_WORLD": CPUWorldProvider,
    "WIKICHIP": WikiChipProvider,
    "TECHPOWERUP": TechPowerUpProvider,
    "GEIZHALS": GeizhalsProvider,
    "PC_KOMBO": PCKomboProvider,
}


def _focused_query_count() -> int:
    try:
        value = int(os.getenv("TECH_RESEARCH_FOCUSED_QUERY_COUNT", "1"))
    except ValueError:
        value = 1
    return max(1, min(2, value))


def build_providers(
    source_names: Iterable[str],
    *,
    category: str | None = None,
    missing_fields: Iterable[str] | None = None,
):
    providers = []
    seen = set()
    missing = tuple(str(x) for x in (missing_fields or ()) if x)
    category = str(category or "").strip().upper()

    for source_name in source_names:
        key = str(source_name or "").strip().upper()
        if not key or key in seen:
            continue
        factory = _PROVIDER_FACTORIES.get(key)
        if factory is None:
            continue
        seen.add(key)
        provider = factory()

        # A fonte continua usando o resolver original. O proxy apenas tenta uma
        # consulta mais específica para as lacunas atuais antes da consulta geral.
        resolver = getattr(provider, "resolver", None)
        if resolver is not None and category and missing:
            provider.resolver = FocusedSearchResolver(
                resolver,
                category=category,
                missing_fields=missing,
                max_focused_queries=_focused_query_count(),
            )
        providers.append(provider)
    return providers
