from __future__ import annotations

import re
from typing import Any

from .ml_specs import (
    attr,
    attrs_map,
    capacity_gb,
    extract_specs as _base_extract_specs,
    memory_types,
    unique,
)
from ..utils.normalizers import clean_text


_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")


def _clean(value: Any) -> str:
    return _ZERO_WIDTH.sub("", clean_text(value) or "")


def _localized_bool(value: Any) -> bool | None:
    token = _clean(value).casefold()
    if token in {"sim", "yes", "true", "ja", "j", "supported", "suportado"}:
        return True
    if token in {"nao", "não", "no", "false", "nein", "n", "unsupported", "nao suportado", "não suportado"}:
        return False
    return None


def _memory_rates(value: Any) -> tuple[list[int], list[int]]:
    """Separa frequências JEDEC e OC de linhas estruturadas como as do Geizhals."""
    text = _clean(value)
    if not text:
        return [], []

    jedec: list[int] = []
    overclock: list[int] = []
    for segment in re.split(r"[,;|]+", text):
        speeds = [
            int(raw)
            for raw in re.findall(r"\bDDR\s*[345]\s*[- ]\s*(\d{3,5})\b", segment, re.I)
        ]
        if not speeds:
            continue
        if re.search(r"\bOC\b|overclock", segment, re.I):
            overclock.extend(speeds)
        else:
            jedec.extend(speeds)
    return unique(jedec), unique(overclock)


def _sum_sata_ports(value: Any) -> int | None:
    text = _clean(value)
    counts = [int(raw) for raw in re.findall(r"\b(\d{1,2})\s*[xX]\s*SATA\b", text, re.I)]
    return sum(counts) if counts else None


def _count_storage_m2_slots(value: Any) -> int | None:
    """Conta somente slots M.2 M-Key de armazenamento; ignora E-Key de Wi-Fi."""
    text = _clean(value)
    if not text:
        return None

    total = 0
    matched = False
    for segment in re.split(r"[,;|]+", text):
        if not re.search(r"M\.?\s*2", segment, re.I):
            continue
        if not re.search(r"M\s*[-/]?\s*Key", segment, re.I):
            continue
        count = re.search(r"\b(\d{1,2})\s*[xX]\s*M\.?\s*2", segment, re.I)
        if count:
            total += int(count.group(1))
            matched = True
    return total if matched else None


def _video_outputs(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []

    out: list[str] = []
    patterns = [
        ("HDMI", r"\b(\d{1,2})\s*[xX]\s*HDMI(?:\s*([0-9]+(?:\.[0-9]+)?))?"),
        ("DisplayPort", r"\b(\d{1,2})\s*[xX]\s*(?:Display\s*Port|DisplayPort|DP)(?:\s*([0-9]+(?:\.[0-9]+)?))?"),
        ("DVI", r"\b(\d{1,2})\s*[xX]\s*DVI(?:[-A-Za-z]*)?"),
        ("VGA", r"\b(\d{1,2})\s*[xX]\s*VGA"),
    ]
    for label, pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            count = int(match.group(1))
            version = match.group(2) if match.lastindex and match.lastindex >= 2 else None
            item = f"{count} x {label}"
            if version:
                item += f" {version}"
            out.append(item)
    return unique(out)


def _motherboard_structured_complements(attributes: list[dict[str, Any]] | None) -> dict[str, Any]:
    mapping = attrs_map(attributes or [])
    specs: dict[str, Any] = {}

    ram = attr(mapping, "RAM", "Memória", "Memory")
    if ram:
        ram_text = _clean(ram)
        kinds = memory_types(ram_text)
        if kinds:
            specs["tiposMemoriaSuportados"] = kinds

        if re.search(r"\bSO[- ]?DIMM\b", ram_text, re.I):
            specs["formatosMemoriaSuportados"] = ["SO_DIMM"]
        elif re.search(r"\b(?:U?DIMM)\b", ram_text, re.I):
            specs["formatosMemoriaSuportados"] = ["DIMM"]

        slots = re.search(r"\b(\d{1,2})\s*[xX]\s*(?:DDR\s*[345]\s*)?(?:U?DIMM|SO[- ]?DIMM)", ram_text, re.I)
        if slots:
            specs["slotsMemoria"] = int(slots.group(1))

        maximum = re.search(r"\bmax\.?\s*([0-9.,]+\s*(?:GB|TB))\b", ram_text, re.I)
        if maximum:
            value = capacity_gb(maximum.group(1))
            if value is not None:
                specs["capacidadeMaximaMemoriaGb"] = value

        if re.search(r"\bUDIMM\b", ram_text, re.I) and not re.search(r"\bRDIMM\b", ram_text, re.I):
            specs["suportaMemoriaRegistrada"] = False

    rates = attr(mapping, "RAM-Datenrate", "RAM Datenrate", "Memory Data Rate", "Memory Speed")
    jedec, overclock = _memory_rates(rates)
    if jedec:
        specs["frequenciasMemoriaJedecMhz"] = jedec
    if overclock:
        specs["frequenciasMemoriaOverclockMhz"] = overclock

    ecc = _localized_bool(attr(mapping, "ECC-Unterstützung", "ECC Unterstutzung", "ECC Support", "ECC"))
    if ecc is not None:
        specs["suportaEcc"] = ecc

    sata = _sum_sata_ports(attr(mapping, "Sonstige Schnittstellen", "Other Interfaces", "Storage Interfaces"))
    if sata is not None:
        specs["portasSata"] = sata

    m2 = _count_storage_m2_slots(attr(mapping, "M.2-Slots", "M2 Slots", "M.2 Slots", "Slots M.2"))
    if m2 is not None:
        specs["slotsM2"] = m2

    ethernet = attr(mapping, "Netzwerk", "Network", "Ethernet", "LAN")
    if ethernet:
        specs["ethernet"] = _clean(ethernet)

    outputs = _video_outputs(attr(mapping, "Anschlüsse extern", "Anschlusse extern", "External Connectors", "External I/O"))
    if outputs:
        specs["saidasVideo"] = outputs

    buttons = _clean(attr(mapping, "Buttons/Switches", "Buttons", "Switches"))
    if buttons and re.search(r"BIOS\s+Flashback|Flash\s+BIOS|Q[- ]Flash\s+Plus", buttons, re.I):
        specs["biosFlashback"] = True

    wireless = _clean(attr(mapping, "Wireless", "WLAN"))
    if wireless:
        if re.search(r"\bWi[- ]?Fi\b|\bWLAN\b", wireless, re.I):
            specs["wifi"] = True
        if re.search(r"\bBluetooth\b", wireless, re.I):
            specs["bluetooth"] = True

    return specs


def extract_research_specs(category: str, attributes=None, context_text: str = "") -> dict[str, Any]:
    """Extrator usado pelo agente técnico, com correções para fontes estruturadas.

    O extrator histórico continua sendo a base. Complementos estruturados só entram
    quando a própria fonte publicou o valor de forma explícita. Para campos onde a
    heurística antiga podia subcontar (SATA/M.2) ou inverter ECC, o valor estruturado
    explícito tem prioridade.
    """
    category = str(category or "").strip().upper()
    base = dict(_base_extract_specs(category, attributes or [], context_text=context_text) or {})

    if category != "PLACA_MAE":
        return base

    structured = _motherboard_structured_complements(attributes or [])
    authoritative = {
        "tiposMemoriaSuportados",
        "formatosMemoriaSuportados",
        "frequenciasMemoriaJedecMhz",
        "frequenciasMemoriaOverclockMhz",
        "slotsMemoria",
        "capacidadeMaximaMemoriaGb",
        "suportaMemoriaRegistrada",
        "suportaEcc",
        "portasSata",
        "slotsM2",
        "ethernet",
        "saidasVideo",
        "biosFlashback",
        "wifi",
        "bluetooth",
    }
    for field, value in structured.items():
        if value in (None, "", []):
            continue
        if field in authoritative or base.get(field) in (None, "", []):
            base[field] = value
    return base
