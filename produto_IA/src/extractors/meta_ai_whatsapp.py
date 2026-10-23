"""Facade do parser Meta AI/OpenAI com higiene de valores técnicos.

O parser histórico permanece em ``meta_ai_whatsapp_base`` para manter compatibilidade.
Esta camada impede que links/citações retornados pela busca web sejam gravados como
parte da especificação. As fontes continuam sendo tratadas separadamente pelo provider
OpenAI e pela camada de proveniência.
"""
from __future__ import annotations

import re
from typing import Any

from . import meta_ai_whatsapp_base as _base


# Reexporta o contrato anterior inteiro. As funções abaixo são sobrescritas depois.
for _name in dir(_base):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_base, _name))


_WRAPPED_MARKDOWN_LINK_SUFFIX = re.compile(
    r"\s*\(\s*\[[^\]\n]{1,200}\]\(\s*https?://.+?\)\s*\)\s*$",
    re.I,
)
_MARKDOWN_LINK_SUFFIX = re.compile(
    r"\s*\[[^\]\n]{1,200}\]\(\s*https?://.+?\)\s*$",
    re.I,
)
_OPENAI_CITATION_SUFFIX = re.compile(r"\s*【[^】\n]{1,200}】\s*$")
_RAW_URL_SUFFIX = re.compile(r"\s*(?:\(\s*)?https?://\S+?(?:\s*\))?\s*$", re.I)


def _strip_reference_suffix(value: str) -> str:
    """Remove somente referências web anexadas ao valor, sem apagar conteúdo técnico."""
    text = str(value or "").strip()
    if not text:
        return text

    # Casos observados/esperados:
    # 1.11 ([asrock.com](https://www.asrock.com/...))
    # 1.11 [asrock.com](https://www.asrock.com/...)
    # 1.11 (https://www.asrock.com/...)
    # 1.11 【fonte】
    previous = None
    while text != previous:
        previous = text
        text = _OPENAI_CITATION_SUFFIX.sub("", text).strip()
        text = _WRAPPED_MARKDOWN_LINK_SUFFIX.sub("", text).strip()
        text = _MARKDOWN_LINK_SUFFIX.sub("", text).strip()
        text = _RAW_URL_SUFFIX.sub("", text).strip()

    # Limpa separadores que ficaram no fim depois da retirada da citação.
    text = re.sub(r"\s+(?:[-–—|;,])\s*$", "", text).strip()
    return text


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _strip_reference_suffix(value)
    if isinstance(value, list):
        cleaned = [_sanitize_value(item) for item in value]
        return [item for item in cleaned if item not in (None, "", [], {})]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _sanitize_value(item) for key, item in value.items()}
    return value


def build_meta_ai_prompt(category: str, name: str, missing_fields: list[str] | None = None) -> str:
    prompt = _base.build_meta_ai_prompt(category, name, missing_fields)
    return (
        f"{prompt}\n"
        "- No valor de cada campo, informe SOMENTE o dado técnico. Não inclua URL, domínio, "
        "link, citação, referência, Markdown ou nome do site junto ao valor. As fontes são "
        "coletadas separadamente pelo sistema."
    )


def parse_meta_ai_response(category: str, response_text: str) -> dict[str, Any]:
    parsed = _base.parse_meta_ai_response(category, response_text)
    cleaned = _sanitize_value(parsed)
    return cleaned if isinstance(cleaned, dict) else {}


def merge_meta_ai_response_into_payload_detailed(
    category: str,
    payload: dict[str, Any] | None,
    response_text: str,
) -> tuple[dict[str, Any], list[str], dict[str, Any], list[dict[str, Any]]]:
    """Preenche lacunas usando valores já higienizados e preserva conflitos."""
    category = str(category or (payload or {}).get("categoria") or "").strip().upper()
    current_payload = _base.normalize_hardware_payload_for_backend(category, payload or {})
    schema = _base.SCHEMAS.get(category)
    if not schema or not schema[1]:
        return current_payload, [], {}, []

    spec_field = schema[1]
    current_specs = dict(current_payload.get(spec_field) or {})
    meta_specs = parse_meta_ai_response(category, response_text)

    filled: list[str] = []
    conflicts: list[dict[str, Any]] = []
    for field, value in meta_specs.items():
        if _base._missing(value):
            continue
        current = current_specs.get(field)
        if _base._missing(current):
            current_specs[field] = value
            filled.append(field)
        elif _base._normalized_for_compare(current) != _base._normalized_for_compare(value):
            conflicts.append({"campo": field, "atual": current, "metaAi": value})

    current_payload[spec_field] = current_specs
    current_payload = _base.normalize_hardware_payload_for_backend(category, current_payload)
    return current_payload, filled, meta_specs, conflicts


def merge_meta_ai_response_into_payload(
    category: str,
    payload: dict[str, Any] | None,
    response_text: str,
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    current_payload, filled, meta_specs, _ = merge_meta_ai_response_into_payload_detailed(
        category, payload, response_text
    )
    return current_payload, filled, meta_specs
