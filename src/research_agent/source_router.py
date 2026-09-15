from __future__ import annotations

from collections.abc import Iterable

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


def build_providers(source_names: Iterable[str]):
    providers = []
    seen = set()
    for source_name in source_names:
        key = str(source_name or "").strip().upper()
        if not key or key in seen:
            continue
        factory = _PROVIDER_FACTORIES.get(key)
        if factory is None:
            continue
        seen.add(key)
        providers.append(factory())
    return providers
