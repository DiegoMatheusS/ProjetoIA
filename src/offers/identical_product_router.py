from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
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


def _tokens(value: Any) -> str:
    return " ".join(re.findall(r"[a-z]+|[0-9]+", str(value or "").casefold()))


def _exact_phrase(value: Any, title: Any) -> bool:
    needle, haystack = _tokens(value), _tokens(title)
    return bool(needle and f" {needle} " in f" {haystack} ")


def _variant_conflict(payload: IdenticalProductOffersRequest, title: Any) -> bool:
    expected = f"{payload.nome} {payload.modelo or ''}"
    variants = r"\b(?:ti|super|xt|xtx|pro|plus|ultra|max|lite|mini)\b"
    if set(re.findall(variants, str(title or '').casefold())) != set(re.findall(variants, expected.casefold())):
        return True
    for pattern in (r"\b\d+\s*(?:gb|tb)\b", r"\b(?:110|127|220)\s*v\b"):
        found = {_norm(v) for v in re.findall(pattern, str(title or ''), re.I)}
        wanted = {_norm(v) for v in re.findall(pattern, expected, re.I)}
        if wanted and found != wanted:
            return True
    return False



def _identity_match_raw(payload: IdenticalProductOffersRequest, raw: dict[str, Any]) -> tuple[bool, str | None]:
    gtin, found_gtin = _digits(payload.gtin), _digits(raw.get("gtin"))
    mpn, found_mpn = _norm(payload.mpn), _norm(raw.get("mpn"))
    # A conflicting explicit identifier must never fall back to a similar title.
    if (gtin and found_gtin and gtin != found_gtin) or (mpn and found_mpn and mpn != found_mpn):
        return False, None
    if gtin and found_gtin:
        return True, "GTIN"
    if mpn and found_mpn and _brand_matches(payload.marca, raw.get("brand"), raw.get("title")):
        return True, "MPN_MARCA"
    expected_model, found_model = _norm(payload.modelo), _norm(raw.get("model"))
    if found_model and expected_model and found_model != expected_model:
        return False, None
    if _variant_conflict(payload, raw.get("title")):
        return False, None
    matched_title, title_criterion = _identity_match_marketplace_name(payload, raw.get("title"))
    if matched_title and title_criterion in {"GTIN_TITULO", "MPN_MARCA_TITULO"}:
        return True, title_criterion
    if expected_model and len(expected_model) >= 4 and _brand_matches(payload.marca, raw.get("brand"), raw.get("title")):
        if found_model == expected_model or _exact_phrase(payload.modelo, raw.get("title")):
            return True, "MARCA_MODELO"
    return False, None


def _identity_match_marketplace_name(payload: IdenticalProductOffersRequest, title: Any) -> tuple[bool, str | None]:
    if not title or _variant_conflict(payload, title):
        return False, None
    gtin = _digits(payload.gtin)
    if gtin and len(gtin) >= 8 and re.search(r"(?<!\d)" + re.escape(gtin) + r"(?!\d)", str(title)):
        return True, "GTIN_TITULO"
    if not _brand_matches(payload.marca, None, title):
        return False, None
    if payload.mpn and len(_norm(payload.mpn)) >= 5 and _exact_phrase(payload.mpn, title):
        return True, "MPN_MARCA_TITULO"
    if payload.modelo and len(_norm(payload.modelo)) >= 4 and _exact_phrase(payload.modelo, title):
        return True, "MARCA_MODELO_TITULO"
    return False, None


def _short_name_query(name: Any, max_words: int = 6) -> str:
    """Usa só o começo identificador do título para descobrir candidatos.

    Títulos de marketplace costumam anexar cor, voltagem, quantidade, slogans e
    especificações demais. Isso torna a pesquisa externa excessivamente rígida.
    A confirmação de identidade continua sendo feita depois por GTIN/MPN/modelo.
    """
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    if not text:
        return ""
    text = re.sub(r"[|;:,()\[\]{}]+", " ", text)
    words = [word for word in re.split(r"\s+", text) if word]
    return " ".join(words[:max_words]).strip()


def _query(payload: IdenticalProductOffersRequest) -> str:
    short_name = _short_name_query(payload.nome)
    if short_name:
        return short_name
    gtin = _digits(payload.gtin)
    if gtin:
        return f"{gtin} {payload.marca or ''}".strip()
    if payload.mpn:
        return f"{payload.marca or ''} {payload.mpn.strip()}".strip()
    if payload.modelo:
        return f"{payload.marca or ''} {payload.modelo.strip()}".strip()
    return payload.nome.strip()


def _marketplace_query(payload: IdenticalProductOffersRequest) -> str:
    return _query(payload)


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
    failed_collection = 0
    rejected_identity = 0
    missing_price = 0

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
            failed_collection += 1
            continue
        checked += 1
        if not isinstance(raw, dict) or not raw.get("ok"):
            failed_collection += 1
            continue
        matched, criterion = _identity_match_raw(payload, raw)
        if not matched or not criterion:
            rejected_identity += 1
            continue
        normalized = _normalize_web_offer(store, raw, criterion, url)
        if normalized:
            offers.append(normalized)
        else:
            missing_price += 1

    return offers, {
        "consulta": _query(payload),
        "candidatos": len(candidates),
        "verificados": checked,
        "encontrados": len(offers),
        "falhasColeta": failed_collection,
        "rejeitadosPorIdentidade": rejected_identity,
        "semPreco": missing_price,
        "statusBusca": resolver.last_status,
    }


def _search_shopee(
    payload: IdenticalProductOffersRequest,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = ShopeeAffiliateClient()
    if not client.configured:
        return [], {"configurada": False, "encontrados": 0}
    search_query = _marketplace_query(payload)
    try:
        response = ShopeeAffiliateAgent(client).find_products(
            query=search_query,
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
        "consulta": search_query,
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
    def search_safely(fn, *args):
        try:
            return fn(*args)
        except Exception:
            # A store outage must not discard confirmed offers from other stores.
            return [], {"statusBusca": "ERRO", "erro": "Não foi possível consultar esta loja agora.", "encontrados": 0}

    with ThreadPoolExecutor(max_workers=3) as pool:
        ml_task = pool.submit(search_safely, _search_web_store, payload, "MERCADO_LIVRE",
                              ["mercadolivre.com.br", "mercadolivre.com", "mercadolibre.com"], limit)
        magalu_task = pool.submit(search_safely, _search_web_store, payload, "MAGALU",
                                  ["magazineluiza.com.br", "magazinevoce.com.br", "magalu.com"], limit)
        shopee_task = pool.submit(search_safely, _search_shopee, payload, limit)
        mercado_livre, ml_diag = ml_task.result()
        magalu, magalu_diag = magalu_task.result()
        shopee, shopee_diag = shopee_task.result()

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
            "buscaPorNomeCurto": True,
        },
    }
