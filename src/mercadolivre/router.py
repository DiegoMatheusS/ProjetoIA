from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..scrapers.mercadolivre_scraper import MercadoLivreScraper


router = APIRouter(prefix="/mercadolivre", tags=["Mercado Livre"])


class MercadoLivreProductRequest(BaseModel):
    url: str | None = Field(default=None, min_length=8, max_length=4096)
    itemId: str | None = Field(default=None, min_length=3, max_length=40)
    permitirFallback: bool = True


def _validate_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


def _normalize_item_id(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"MLB-?(\d{6,})", value.strip(), re.I)
    if match:
        return f"MLB{match.group(1)}"
    digits = re.sub(r"\D", "", value)
    return f"MLB{digits}" if len(digits) >= 6 else None


def _request_url(payload: MercadoLivreProductRequest) -> tuple[str, str | None]:
    url = str(payload.url or "").strip()
    item_id = _normalize_item_id(payload.itemId)

    if url:
        if not MercadoLivreScraper.is_mercadolivre(url):
            raise HTTPException(status_code=422, detail="A URL informada não pertence ao Mercado Livre.")
        ids = MercadoLivreScraper.extract_ids(url)
        item_id = ids.get("item_id") or item_id
        return url, item_id

    if not item_id:
        raise HTTPException(status_code=422, detail="Informe uma URL do Mercado Livre ou itemId MLB.")

    # A URL é usada apenas como referência pelo coletor; o itemId extraído dela
    # direciona a consulta exata à API oficial.
    return f"https://produto.mercadolivre.com.br/MLB-{item_id[3:]}", item_id


def _discount_percent(current: Any, previous: Any) -> float | None:
    try:
        current_value = float(current)
        previous_value = float(previous)
    except (TypeError, ValueError):
        return None
    if current_value <= 0 or previous_value <= current_value:
        return None
    return round(((previous_value - current_value) / previous_value) * 100, 2)


def _normalize_result(raw: dict[str, Any], requested_url: str, requested_item_id: str | None) -> dict[str, Any]:
    price = raw.get("price")
    previous = raw.get("previous_price")
    discount = _discount_percent(price, previous)
    source = str(raw.get("source") or "MERCADO_LIVRE")
    item_id = raw.get("item_id") or requested_item_id

    return {
        "fonte": source,
        "marketplace": "MERCADO_LIVRE",
        "apiOficial": bool(raw.get("api_used")),
        "fallbackUsado": source != "MERCADO_LIVRE_API",
        "itemId": item_id,
        "catalogProductId": raw.get("catalog_product_id"),
        "codigoMarketplace": raw.get("marketplace_product_code") or item_id,
        "nome": raw.get("title"),
        "urlOriginal": requested_url,
        "urlFinal": raw.get("url_final") or requested_url,
        "imagemUrl": raw.get("image_url"),
        "preco": price,
        "precoAnterior": previous,
        "descontoPercentual": discount,
        "emPromocao": bool(discount and discount > 0),
        "moeda": raw.get("currency") or "BRL",
        "disponivel": raw.get("available"),
        "vendedorId": raw.get("seller_id"),
        "categoriaId": raw.get("category_id"),
        "origemPreco": raw.get("price_source"),
        "apiErrors": raw.get("api_errors") or [],
        "requiresLocalCapture": bool(raw.get("requires_local_capture")),
    }


@router.get("/api/status")
def mercadolivre_api_status(x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    return {
        "ok": True,
        "fonte": "MERCADO_LIVRE_API",
        "apiOficial": True,
        "clientIdConfigurado": bool(os.getenv("ML_CLIENT_ID", "").strip()),
        "clientSecretConfigurado": bool(os.getenv("ML_CLIENT_SECRET", "").strip()),
        "accessTokenConfigurado": bool(os.getenv("ML_ACCESS_TOKEN", "").strip()),
        "refreshTokenConfigurado": bool(os.getenv("ML_REFRESH_TOKEN", "").strip()),
        "pkce": os.getenv("ML_USE_PKCE", "").strip().lower() in {"1", "true", "yes", "sim", "on"},
    }


@router.post("/agente/produto")
def mercadolivre_agent_product(
    payload: MercadoLivreProductRequest,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    url, item_id = _request_url(payload)

    scraper = MercadoLivreScraper()
    raw = scraper.collect(url, no_browser=not payload.permitirFallback)
    normalized = _normalize_result(raw, url, item_id)

    if not raw.get("ok") and normalized.get("preco") is None:
        error = raw.get("error") or (raw.get("api_errors") or ["Mercado Livre não retornou dados."])[0]
        raise HTTPException(status_code=502, detail=str(error))

    return {
        "agente": "MERCADO_LIVRE_OFERTAS",
        "modo": "API_OFICIAL_COM_FALLBACK" if payload.permitirFallback else "API_OFICIAL",
        "item": normalized,
    }
