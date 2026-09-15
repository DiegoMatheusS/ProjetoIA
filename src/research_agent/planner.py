from __future__ import annotations

from dataclasses import dataclass
import os

from ..enrichment.core import (
    essential_missing_fields,
    technical_coverage,
    technical_missing_fields,
)


CATEGORY_SOURCE_ORDER: dict[str, tuple[str, ...]] = {
    "PROCESSADOR": (
        "FABRICANTE_OFICIAL",
        "CPU_MONKEY",
        "CPU_WORLD",
        "WIKICHIP",
        "ICECAT",
        "GEIZHALS",
        "PC_KOMBO",
    ),
    "PLACA_VIDEO": (
        "FABRICANTE_OFICIAL",
        "TECHPOWERUP",
        "ICECAT",
        "GEIZHALS",
        "WIKICHIP",
        "PC_KOMBO",
    ),
    "PLACA_MAE": (
        "FABRICANTE_OFICIAL",
        "ICECAT",
        "GEIZHALS",
        "PC_KOMBO",
    ),
    "MEMORIA_RAM": (
        "FABRICANTE_OFICIAL",
        "ICECAT",
        "GEIZHALS",
        "PC_KOMBO",
    ),
    "ARMAZENAMENTO": (
        "FABRICANTE_OFICIAL",
        "ICECAT",
        "GEIZHALS",
        "PC_KOMBO",
    ),
    "FONTE": (
        "FABRICANTE_OFICIAL",
        "ICECAT",
        "GEIZHALS",
        "PC_KOMBO",
    ),
    "GABINETE": (
        "FABRICANTE_OFICIAL",
        "ICECAT",
        "GEIZHALS",
        "PC_KOMBO",
    ),
    "COOLER": (
        "FABRICANTE_OFICIAL",
        "ICECAT",
        "GEIZHALS",
        "PC_KOMBO",
    ),
    "VENTOINHA": (
        "FABRICANTE_OFICIAL",
        "ICECAT",
        "GEIZHALS",
        "PC_KOMBO",
    ),
}


_FIELD_SOURCE_HINTS: dict[str, tuple[tuple[set[str], tuple[str, ...]], ...]] = {
    "PROCESSADOR": (
        (
            {
                "arquitetura", "litografiaNm", "nucleos", "threads",
                "frequenciaBaseMhz", "frequenciaTurboMhz", "cacheL2Mb", "cacheL3Mb",
            },
            ("CPU_MONKEY", "CPU_WORLD", "WIKICHIP"),
        ),
        (
            {
                "tiposMemoriaSuportados", "frequenciaMemoriaMaximaMhz",
                "capacidadeMemoriaMaximaGb", "canaisMemoria", "versaoPcie", "lanesPcie",
            },
            ("FABRICANTE_OFICIAL", "CPU_MONKEY", "CPU_WORLD"),
        ),
    ),
    "PLACA_VIDEO": (
        (
            {
                "gpu", "chipset", "arquitetura", "memoriaVideoGb", "tipoMemoriaVideo",
                "barramentoBits", "clockBaseMhz", "clockBoostMhz", "geracaoPcie", "larguraPcie",
            },
            ("TECHPOWERUP", "FABRICANTE_OFICIAL", "GEIZHALS"),
        ),
        (
            {
                "comprimentoMm", "alturaMm", "espessuraMm", "slotsOcupados", "consumoWatts",
                "potenciaFonteRecomendadaWatts", "conectoresPcie6Pinos", "conectoresPcie8Pinos",
                "conectores12vhpwr", "conectores12v2x6", "hdmi", "displayPort", "saidasVideo",
            },
            ("FABRICANTE_OFICIAL", "TECHPOWERUP", "GEIZHALS", "ICECAT"),
        ),
    ),
    "PLACA_MAE": (
        (
            {
                "biosInicial", "biosMinima", "biosFlashback", "revisao", "wifi", "bluetooth",
                "ethernet", "saidasVideo", "portasSata", "slotsM2", "slotsMemoria",
                "capacidadeMaximaMemoriaGb", "capacidadeMaximaPorSlotGb",
                "frequenciasMemoriaJedecMhz", "frequenciasMemoriaOverclockMhz",
            },
            ("FABRICANTE_OFICIAL", "ICECAT", "GEIZHALS"),
        ),
    ),
    "MEMORIA_RAM": (
        (
            {
                "tipo", "formato", "capacidadePorModuloGb", "quantidadeModulos", "frequenciaMhz",
                "frequenciaJedecMhz", "latenciaCl", "tensaoVolts", "suportaXmp", "suportaExpo",
            },
            ("FABRICANTE_OFICIAL", "ICECAT", "GEIZHALS"),
        ),
    ),
}


def _focused_source_order(category: str, missing: tuple[str, ...]) -> tuple[str, ...]:
    base = CATEGORY_SOURCE_ORDER.get(
        category,
        ("FABRICANTE_OFICIAL", "ICECAT", "GEIZHALS", "PC_KOMBO"),
    )
    missing_set = set(missing)
    preferred: list[str] = ["FABRICANTE_OFICIAL"]
    for fields, sources in _FIELD_SOURCE_HINTS.get(category, ()):
        if fields.intersection(missing_set):
            preferred.extend(sources)
    preferred.extend(base)

    ordered: list[str] = []
    for source in preferred:
        if source == "PC_KOMBO":
            continue
        if source not in ordered:
            ordered.append(source)
    if "PC_KOMBO" in base:
        ordered.append("PC_KOMBO")
    return tuple(ordered)


@dataclass(frozen=True)
class ResearchPlan:
    category: str
    mode: str
    missing_fields: tuple[str, ...]
    essential_missing_fields: tuple[str, ...]
    sources: tuple[str, ...]
    max_sources: int
    total_timeout_seconds: float
    source_timeout_seconds: int
    target_coverage: float
    coverage_before: float

    def as_dict(self) -> dict:
        return {
            "categoria": self.category,
            "modo": self.mode,
            "camposAusentes": list(self.missing_fields),
            "camposEssenciaisAusentes": list(self.essential_missing_fields),
            "fontesPlanejadas": list(self.sources[: self.max_sources]),
            "maximoFontes": self.max_sources,
            "orcamentoSegundos": self.total_timeout_seconds,
            "timeoutFonteSegundos": self.source_timeout_seconds,
            "coberturaAlvo": round(self.target_coverage, 4),
            "coberturaAntes": round(self.coverage_before, 4),
        }


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def build_research_plan(category: str, result: dict) -> ResearchPlan:
    category = str(category or "").strip().upper()
    missing = tuple(technical_missing_fields(result))
    essential = tuple(essential_missing_fields(result))
    coverage = technical_coverage(result)
    sources = _focused_source_order(category, missing)

    # Ficha muito vazia ou com lacunas essenciais recebe pesquisa mais profunda.
    deep = bool(essential) or coverage < 0.55 or len(missing) >= 8
    mode = "PROFUNDA" if deep else "FOCADA"

    if deep:
        default_max_sources = 5
        default_total_timeout = 34.0
        default_source_timeout = 6
        default_target_coverage = 0.90
    else:
        default_max_sources = 3
        default_total_timeout = 20.0
        default_source_timeout = 5
        default_target_coverage = 0.88

    max_sources = _int_env(
        "TECH_RESEARCH_MAX_SOURCES",
        default_max_sources,
        1,
        min(7, max(1, len(sources))),
    )
    total_timeout = _float_env(
        "TECH_RESEARCH_TOTAL_TIMEOUT_SECONDS",
        default_total_timeout,
        5.0,
        70.0,
    )
    source_timeout = _int_env(
        "TECH_RESEARCH_SOURCE_TIMEOUT_SECONDS",
        default_source_timeout,
        2,
        15,
    )
    target_coverage = _float_env(
        "TECH_RESEARCH_TARGET_COVERAGE",
        default_target_coverage,
        0.60,
        1.0,
    )

    return ResearchPlan(
        category=category,
        mode=mode,
        missing_fields=missing,
        essential_missing_fields=essential,
        sources=sources,
        max_sources=min(max_sources, len(sources)),
        total_timeout_seconds=total_timeout,
        source_timeout_seconds=source_timeout,
        target_coverage=target_coverage,
        coverage_before=coverage,
    )
