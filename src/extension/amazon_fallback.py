"""Fallback da extensão Amazon usando apenas os dados lidos da aba do admin.

A Amazon pode devolver uma página vazia/bloqueada ao navegador do servidor.
Isso não deve descartar o título e os identificadores obtidos no Chrome.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ..extractors.backend_schemas import SCHEMAS
from ..main import build_result
from ..technical_ai.auto import auto_enrich_link_result


def hydrate_amazon_analysis(
    analysis: dict[str, Any],
    *,
    url: str,
    capture: Any,
    forced_category: str | None = None,
) -> dict[str, Any]:
    """Substitui análise inconclusiva pela captura da aba, sem inventar specs.

    A análise remota completa continua prioritária. O fallback só ocorre para
    páginas Amazon, quando o coletor não identificou a categoria ou o nome.
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
    if current_category in SCHEMAS and current_payload.get("nome"):
        return analysis

    asin = str(getattr(capture, "asin", None) or "").strip().upper()
    page_price = getattr(capture, "preco", None)
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
        "price": page_price,
        "currency": "BRL",
        "marketplace_product_code": asin or getattr(capture, "codigoMarketplace", None),
        "attributes": [],
        "product_attributes": [],
        "attributes_text": "",
    }
    local = build_result(page_raw, forced_category)
    category = str(local.get("categoriaDetectada") or "").upper()
    if category not in SCHEMAS:
        return analysis

    # Se a coleta remota já encontrou atributos úteis da MESMA categoria,
    # preservá-los. Não transferir specs de uma categoria potencialmente errada.
    if current_category == category:
        original_spec = SCHEMAS[category][1]
        if original_spec and isinstance(current_payload.get(original_spec), dict):
            local_payload = local["payloadParcialBackend"]
            local_payload[original_spec] = dict(current_payload[original_spec])
        for key in ("descricao", "imagemUrl"):
            if current_payload.get(key) and not local["payloadParcialBackend"].get(key):
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
    # A IA recebe o NOME REAL antes de pesquisar especificações; erro/timeout
    # no provedor não descarta título, categoria ou preço já capturados.
    return auto_enrich_link_result(local)
