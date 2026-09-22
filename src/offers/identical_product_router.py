from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..enrichment.search import WebSearchResolver
from ..scrapers.magazine_scraper import MagazineScraper
from ..scrapers.mercadolivre_scraper import MercadoLivreScraper
from ..shopee.agent import ShopeeAffiliateAgent
from ..shopee.client import ShopeeAffiliateClient, ShopeeAffiliateError


router = APIRouter(prefix="/ofertas", tags=["Ofertas idênticas"])


class IdenticalProductOffersRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=500)
    marca: str | None = Field(default=None, max_length=120)
    modelo: str | None = Field(default=None, max_length=240)
    mpn: str | None = Field(default=None, max_length=180)
    gtin: str | None = Field(default=None, max_length=32)
    limitePorLoja: int = Field(default=3, ge=1, le=5)


def _validate_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _brand_matches(expected: str | None, brand: Any, title: Any) -> bool:
    if not expected:
        return True
    wanted = _norm(expected)
    return bool(wanted and (_norm(brand) == wanted or wanted in _norm(title)))


def _identity_match_raw(payload: IdenticalProductOffersRequest, raw: dict[str, Any]) -> tuple[bool, str | None]:
    expected_gtin = _digits(payload.gtin)
    found_gtin = _digits(raw.get("gtin"))
    if expected_gtin and found_gtin and expected_gtin == found_gtin:
        return True, "GTIN"

    expected_mpn = _norm(payload.mpn)
    found_mpn = _norm(raw.get("mpn"))
    if (
        expected_mpn
        and found_mpn
        and expected_mpn == found_mpn
        and _brand_matches(payload.marca, raw.get("brand"), raw.get("title"))
    ):
        return True, "MPN_MARCA"

    expected_model = _norm(payload.modelo)
    found_model = _norm(raw.get("model"))
    title = _norm(raw.get("title"))
    if (
        expected_model
        and len(expected_model) >= 4
        and _brand_matches(payload.marca, raw.get("brand"), raw.get("title"))
        and (found_model == expected_model or expected_model in title)
    ):
        return True, "MARCA_MODELO"

    return False, None


def _identity_match_marketplace_name(
    payload: IdenticalProductOffersRequest,
    title: Any,
) -> tuple[bool, str | None]:
    normalized_title = _norm(title)
    if not normalized_title:
        return False, None

    gtin = _digits(payload.gtin)
    if gtin and len(gtin) >= 8 and gtin in _digits(title):
        return True, "GTIN_TITULO"

    mpn = _norm(payload.mpn)
    brand = _norm(payload.marca)
    if mpn and len(mpn) >= 5 and mpn in normalized_title and (not brand or brand in normalized_title):
        return True, "MPN_MARCA_TITULO"

    model = _norm(payload.modelo)
    if model and len(model) >= 4 and model in normalized_title and (not brand or brand in normalized_title):
        return True, "MARCA_MODELO_TITULO"

    return False, None


def _query(payload: IdenticalProductOffersRequest) -> str:
    gtin = _digits(payload.gtin)
    if gtin:
        return f'"{gtin}" {payload.marca or ""}'.strip()
    if payload.mpn:
        return f'"{payload.mpn.strip()}" {payload.marca or ""}'.strip()
    if payload.modelo:
        return f'{payload.marca or ""} "{payload.modelo.strip()}"'.strip()
    return payload.nome.strip()


def _marketplace_query(payload: IdenticalProductOffersRequest) -> str:
    gtin = _digits(payload.gtin)
    if gtin:
        return f"{gtin} {payload.marca or ''}".strip()
    if payload.mpn:
        return f"{payload.marca or ''} {payload.mpn.strip()}".strip()
    if payload.modelo:
        return f"{payload.marca or ''} {payload.modelo.strip()}".strip()
    return payload.nome.strip()


def _price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 2) if number > 0 else None


def _normalize_web_offer(
    store: str,
    raw: dict[str, Any],
    criterion: str,
    requested_url: str,
) -> dict[str, Any] | None:
    price = _price(raw.get("price"))
    url = str(raw.get("url_final") or raw.get("url_original") or requested_url or "").strip()
    if price is None or not url:
        return None

    return {
        "parceiro": "Mercado Livre" if store == "MERCADO_LIVRE" else "Magazine Luiza",
        "marketplace": store,
        "criterioIdentidade": criterion,
        "nomeEncontrado": raw.get("title"),
        "preco": price,
        "precoAnterior": _price(raw.get("previous_price")),
        "urlOriginal": url,
        "urlAfiliada": None,
        "codigoMarketplace": raw.get("marketplace_product_code") or raw.get("item_id"),
        "vendedorNome": raw.get("seller_name") or raw.get("seller"),
        "vendedorIdentificador": raw.get("seller_id"),
        "imagemUrl": raw.get("image_url"),
        "apiOficial": bool(raw.get("api_used")),
        "fonte": raw.get("source"),
    }


def _search_web_store(
    payload: IdenticalProductOffersRequest,
    store: str,
    domains: list[str],
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    resolver = WebSearchResolver()
    candidates = resolver.results(_query(payload), domains, limit=max(limit * 3, 6))
    offers: list[dict[str, Any]] = []
    checked = 0

    for candidate in candidates:
        if len(offers) >= limit:
            break
        url = str(candidate.get("url") or "").strip()
        if not url:
            continue
        try:
            if store == "MERCADO_LIVRE":
                if not MercadoLivreScraper.is_mercadolivre(url):
                    continue
                raw = MercadoLivreScraper().collect(url, no_browser=False)
            else:
                if not MagazineScraper.is_product_url(url):
                    continue
                raw = MagazineScraper().collect(url, no_browser=False)
        except Exception:
            continue
        checked += 1
        if not isinstance(raw, dict) or not raw.get("ok"):
            continue
        matched, criterion = _identity_match_raw(payload, raw)
        if not matched or not criterion:
            continue
        normalized = _normalize_web_offer(store, raw, criterion, url)
        if normalized:
            offers.append(normalized)

    return offers, {
        "candidatos": len(candidates),
        "verificados": checked,
        "encontrados": len(offers),
        "statusBusca": resolver.last_status,
    }


def _search_shopee(
    payload: IdenticalProductOffersRequest,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = ShopeeAffiliateClient()
    if not client.configured:
        return [], {"configurada": False, "encontrados": 0}

    try:
        response = ShopeeAffiliateAgent(client).find_products(
            query=_marketplace_query(payload),
            limit=max(limit * 5, 20),
        )
    except ShopeeAffiliateError as exc:
        return [], {"configurada": True, "erro": str(exc), "encontrados": 0}

    offers: list[dict[str, Any]] = []
    for item in response.get("itens") or []:
        if len(offers) >= limit:
            break
        matched, criterion = _identity_match_marketplace_name(payload, item.get("nome"))
        if not matched or not criterion:
            continue
        price = _price(item.get("preco") or item.get("precoMin"))
        url = str(item.get("urlOriginal") or "").strip()
        if price is None or not url:
            continue
        offers.append({
            "parceiro": "Shopee",
            "marketplace": "SHOPEE",
            "criterioIdentidade": criterion,
            "nomeEncontrado": item.get("nome"),
            "preco": price,
            "precoAnterior": None,
            "urlOriginal": url,
            "urlAfiliada": item.get("urlAfiliada"),
            "codigoMarketplace": item.get("itemId"),
            "vendedorNome": item.get("loja"),
            "vendedorIdentificador": item.get("shopId"),
            "imagemUrl": item.get("imagemUrl"),
            "apiOficial": True,
            "fonte": "SHOPEE_AFFILIATE_API",
        })

    return offers, {
        "configurada": True,
        "candidatos": len(response.get("itens") or []),
        "encontrados": len(offers),
    }


@router.post("/produto-identico")
def find_identical_product_offers(
    payload: IdenticalProductOffersRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)

    if not any((_digits(payload.gtin), str(payload.mpn or "").strip(), str(payload.modelo or "").strip())):
        raise HTTPException(
            status_code=422,
            detail="O Produto precisa ter GTIN/EAN, MPN ou modelo para confirmar correspondência idêntica.",
        )

    limit = max(1, min(5, int(payload.limitePorLoja)))
    mercado_livre, ml_diag = _search_web_store(
        payload,
        "MERCADO_LIVRE",
        ["mercadolivre.com.br", "mercadolivre.com", "mercadolibre.com"],
        limit,
    )
    magalu, magalu_diag = _search_web_store(
        payload,
        "MAGALU",
        ["magazineluiza.com.br", "magazinevoce.com.br", "magalu.com"],
        limit,
    )
    shopee, shopee_diag = _search_shopee(payload, limit)

    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for offer in [*mercado_livre, *magalu, *shopee]:
        key = (
            str(offer.get("marketplace") or ""),
            str(offer.get("urlOriginal") or "").split("#", 1)[0].rstrip("/").casefold(),
        )
        if not key[1] or key in seen:
            continue
        seen.add(key)
        unique.append(offer)

    return {
        "modo": "BUSCA_PRODUTO_IDENTICO",
        "consulta": _query(payload),
        "identidade": {
            "nome": payload.nome,
            "marca": payload.marca,
            "modelo": payload.modelo,
            "mpn": payload.mpn,
            "gtin": payload.gtin,
        },
        "quantidade": len(unique),
        "ofertas": unique,
        "fontes": {
            "mercadoLivre": ml_diag,
            "magalu": magalu_diag,
            "shopee": shopee_diag,
        },
        "politica": {
            "somenteProdutoIdentico": True,
            "naoAlteraProduto": True,
            "naoAlteraFichaTecnica": True,
            "confirmacaoPorIdentidadeForte": True,
        },
    }
