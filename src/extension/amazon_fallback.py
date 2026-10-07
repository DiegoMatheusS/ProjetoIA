"""Fallback da extensão Amazon usando dados lidos da aba do administrador.

A Amazon pode devolver uma página bloqueada ao servidor. A captura local
preserva a identidade do produto, mas não substitui confirmação da ficha técnica.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ..extractors.backend_schemas import SCHEMAS
from ..main import build_result
from ..technical_ai.auto import auto_enrich_link_result


# Aplicados apenas quando a análise REMOTA falha e a categoria veio da aba.
# Não aceitar publicação automática de hardware sem sequer uma ficha mínima.
_MINIMUM_AMAZON_HARDWARE_SPECS = {
    "PROCESSADOR": ("socket", "nucleos"),
    "PLACA_MAE": ("socket", "chipset"),
    "MEMORIA_RAM": ("tipo", "capacidadePorModuloGb"),
    "PLACA_VIDEO": ("gpu", "memoriaVideoGb"),
    "ARMAZENAMENTO": ("tipo", "capacidadeGb"),
    "FONTE": ("formato", "potenciaWatts"),
    "GABINETE": ("tamanho",),
    "COOLER": ("tipo",),
    "VENTOINHA": ("tamanhoMm",),
}


def amazon_browser_minimum_issues(category: str, payload: dict[str, Any]) -> list[str]:
    schema = SCHEMAS.get(str(category or "").upper())
    if not schema or schema[0] != "HARDWARE" or not schema[1]:
        return []
    spec_field = schema[1]
    specs = payload.get(spec_field)
    specs = specs if isinstance(specs, dict) else {}
    issues = []
    for field in _MINIMUM_AMAZON_HARDWARE_SPECS.get(category, ()):
        value = specs.get(field)
        if value is None or value == "" or value == [] or (
            isinstance(value, str) and value.strip().casefold() in {
                "n/a", "não informado", "nao informado", "desconhecido", "unknown",
            }
        ):
            issues.append(f"{spec_field}.{field} não confirmado")
    return issues


def hydrate_amazon_analysis(
    analysis: dict[str, Any],
    *,
    url: str,
    capture: Any,
    forced_category: str | None = None,
) -> dict[str, Any]:
    """Substitui análise inconclusiva pela captura da aba, sem inventar specs.

    Uma análise remota completa continua prioritária. Só usar captura local
    quando a categoria ou o nome da coleta remota estiverem ausentes.
    """
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not any(host == domain or host.endswith(f".{domain}") for domain in ("amazon.com.br", "amazon.com")):
        return analysis

    page_name = str(getattr(capture, "nome", None) or "").strip()
    if len(page_name) < 8:
        return analysis

    current = analysis if isinstance(analysis, dict) else {}
    current_payload = current.get("payloadParcialBackend")
    current_payload = current_payload if isinstance(current_payload, dict) else {}
    current_category = str(current.get("categoriaDetectada") or "").upper()
    captured_attributes = []
    for item in getattr(capture, "atributos", None) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or item.get("value_name") or "").strip()
        if name and value:
            captured_attributes.append({"name": name[:160], "value_name": value[:1000]})
        if len(captured_attributes) >= 250:
            break

    current_schema = SCHEMAS.get(current_category)
    current_spec_field = current_schema[1] if current_schema else None
    current_specs = (
        current_payload.get(current_spec_field)
        if current_spec_field and isinstance(current_payload.get(current_spec_field), dict)
        else {}
    )
    # Se a análise remota já trouxe ficha técnica e a aba não trouxe atributos
    # adicionais, não há nada para complementar localmente.
    if current_category in SCHEMAS and current_payload.get("nome") and current_specs and not captured_attributes:
        return analysis

    asin = str(getattr(capture, "asin", None) or "").strip().upper()
    page_raw = {
        "ok": True,
        "blocked": False,
        "source": "EXTENSAO_ABA_LOCAL_AMAZON",
        "url_original": url,
        "url_final": url,
        "title": page_name,
        "brand": getattr(capture, "marca", None),
        "model": getattr(capture, "modelo", None),
        "mpn": getattr(capture, "mpn", None),
        "gtin": getattr(capture, "gtin", None),
        "price": getattr(capture, "preco", None),
        "currency": "BRL",
        "marketplace_product_code": asin or getattr(capture, "codigoMarketplace", None),
        "description": getattr(capture, "descricao", None),
        "image_url": getattr(capture, "imagemUrl", None),
        "attributes": captured_attributes,
        "product_attributes": list(captured_attributes),
        "attributes_text": "\n".join(
            f"{item['name']}: {item['value_name']}" for item in captured_attributes
        ),
    }
    local = build_result(page_raw, forced_category or current_category or None)
    category = str(local.get("categoriaDetectada") or "").upper()
    if category not in SCHEMAS:
        return analysis

    # Reaproveitar dados remotos úteis apenas da MESMA categoria. Em conflitos,
    # a coleta remota continua autoritativa; a captura da aba só preenche lacunas.
    if current_category == category:
        spec_field = SCHEMAS[category][1]
        if spec_field:
            local_specs = (
                local["payloadParcialBackend"].get(spec_field)
                if isinstance(local["payloadParcialBackend"].get(spec_field), dict)
                else {}
            )
            remote_specs = (
                current_payload.get(spec_field)
                if isinstance(current_payload.get(spec_field), dict)
                else {}
            )
            merged_specs = dict(local_specs)
            for key, value in remote_specs.items():
                if value is not None and value != "" and value != []:
                    merged_specs[key] = value
            local["payloadParcialBackend"][spec_field] = merged_specs
        for key in ("nome", "marca", "modelo", "mpn", "gtin", "descricao", "imagemUrl"):
            if current_payload.get(key):
                local["payloadParcialBackend"][key] = current_payload[key]

    remote_offer = current.get("ofertaColetada")
    if isinstance(remote_offer, dict):
        local_offer = local["ofertaColetada"]
        for field in ("preco", "precoAnterior", "disponivel", "codigoMarketplace"):
            if local_offer.get(field) is None and remote_offer.get(field) is not None:
                local_offer[field] = remote_offer[field]

    local["origemColeta"]["capturaLocal"] = True
    local["origemColeta"]["fonte"] = "EXTENSAO_ABA_LOCAL_AMAZON"
    local["fallbackCapturaAmazon"] = True
    # IA recebe o título REAL antes da consulta; falha/timeout do provider não
    # descarta título, categoria, ASIN nem preço capturados.
    return auto_enrich_link_result(local)
