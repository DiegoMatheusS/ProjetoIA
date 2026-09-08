"""Fallback técnico opcional usando uma resposta visível do Meta AI no WhatsApp Web.

O módulo NÃO automatiza login nem usa o Meta AI como fonte principal. Ele recebe o
texto já exibido no navegador local, extrai especificações e preenche somente
lacunas da ficha técnica quando a cobertura do buscador normal está baixa.
"""
from __future__ import annotations

import os
import re
from typing import Any

from .backend_schemas import SCHEMAS
from .dto_normalizer import normalize_hardware_payload_for_backend, normalize_specs_for_backend
from .ml_specs import extract_specs


DEFAULT_FALLBACK_COVERAGE = 0.60


def fallback_coverage_threshold() -> float:
    raw = os.getenv("META_AI_WHATSAPP_FALLBACK_COVERAGE", str(DEFAULT_FALLBACK_COVERAGE))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = DEFAULT_FALLBACK_COVERAGE
    return min(0.95, max(0.20, value))


def should_use_meta_ai_fallback(coverage: float | int | None, *, threshold: float | None = None) -> bool:
    try:
        current = float(coverage or 0.0)
    except (TypeError, ValueError):
        current = 0.0
    limit = fallback_coverage_threshold() if threshold is None else min(0.95, max(0.20, float(threshold)))
    return current < limit


def build_meta_ai_prompt(category: str, name: str, missing_fields: list[str] | None = None) -> str:
    category = str(category or "HARDWARE").strip().upper()
    name = str(name or "hardware").strip()
    missing = [str(field).strip() for field in (missing_fields or []) if str(field).strip()]
    missing_hint = ""
    if missing:
        missing_hint = " Priorize também estes dados que ainda faltam: " + ", ".join(missing[:18]) + "."
    return (
        f"Liste todas as especificações técnicas confirmadas de {name}, uma por linha no formato Campo: valor. "
        f"É um item da categoria {category}. Não informe preço, lojas, promoções ou recomendações. "
        "Não invente dados; se não tiver certeza de um campo, omita esse campo."
        f"{missing_hint}"
    )


def _line_attributes(text: str) -> list[dict[str, str]]:
    """Transforma listas Campo: valor / Campo - valor em atributos genéricos."""
    attrs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in str(text or "").splitlines():
        line = re.sub(r"^[\s\-–—•*▪◦·]+", "", raw_line).strip()
        if not line or len(line) > 500:
            continue

        match = re.match(r"^([^:]{2,100})\s*:\s*(.{1,350})$", line)
        if not match:
            match = re.match(r"^([^–—]{2,100})\s+[–—]\s+(.{1,350})$", line)
        if not match:
            # Hífen simples é comum em nomes/valores; só usamos quando há espaços
            # em volta para reduzir falsos positivos como DDR5-5600.
            match = re.match(r"^(.{2,100}?)\s+-\s+(.{1,350})$", line)
        if not match:
            continue

        name = match.group(1).strip().strip("*_")
        value = match.group(2).strip().strip("*_")
        if not name or not value:
            continue
        key = (name.casefold(), value.casefold())
        if key in seen:
            continue
        seen.add(key)
        attrs.append({"name": name, "value_name": value})
    return attrs


def parse_meta_ai_response(category: str, response_text: str) -> dict[str, Any]:
    category = str(category or "").strip().upper()
    if category not in SCHEMAS:
        return {}
    text = str(response_text or "").strip()
    if not text:
        return {}
    attrs = _line_attributes(text)
    specs = extract_specs(category, attrs, context_text=text)
    return normalize_specs_for_backend(category, specs)


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def merge_meta_ai_response_into_payload(
    category: str,
    payload: dict[str, Any] | None,
    response_text: str,
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    """Preenche apenas lacunas do payload e devolve payload, campos e specs lidas."""
    category = str(category or (payload or {}).get("categoria") or "").strip().upper()
    current_payload = normalize_hardware_payload_for_backend(category, payload or {})
    schema = SCHEMAS.get(category)
    if not schema or not schema[1]:
        return current_payload, [], {}

    spec_field = schema[1]
    current_specs = dict(current_payload.get(spec_field) or {})
    meta_specs = parse_meta_ai_response(category, response_text)

    filled: list[str] = []
    for field, value in meta_specs.items():
        if _missing(value):
            continue
        if _missing(current_specs.get(field)):
            current_specs[field] = value
            filled.append(field)

    current_payload[spec_field] = current_specs
    current_payload = normalize_hardware_payload_for_backend(category, current_payload)
    return current_payload, filled, meta_specs
