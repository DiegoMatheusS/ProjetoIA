from __future__ import annotations

import os
import math
import time
from concurrent.futures import ThreadPoolExecutor, wait
import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..enrichment.search import WebSearchResolver
from ..shopee.agent import ShopeeAffiliateAgent
from ..shopee.client import ShopeeAffiliateClient, ShopeeAffiliateError
from .store_candidates import StoreCandidates, is_product_url


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


def _identity_queries(payload: IdenticalProductOffersRequest) -> list[str]:
    # Preserve the complete SKU/model even when it occurs after the sixth word.
    queries = [f"{payload.marca or ''} {value}".strip()
               for value in (payload.mpn, payload.modelo) if str(value or '').strip()]
    if _digits(payload.gtin):
        queries.append(_digits(payload.gtin))
    queries.append(_query(payload))
    return list(dict.fromkeys(queries))


def _price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 2) if math.isfinite(number) and number > 0 else None


def _normalize_web_offer(
    store: str,
    raw: dict[str, Any],
    criterion: str,
    requested_url: str,
) -> dict[str, Any] | None:
    price = _price(raw.get("price"))
    url = str(raw.get("url_final") or raw.get("url_original") or requested_url or "").strip()
    if (price is None or not is_product_url(store, url) or raw.get("available") is False
            or str(raw.get("currency") or "BRL").upper() != "BRL"):
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
    deadline: float | None = None,
    progress: dict | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    deadline = deadline or time.monotonic() + 60
    progress = progress if progress is not None else {}
    resolver = WebSearchResolver()
    resolver.timeout = 6
    resolver.deadline = deadline
    resolver.allow_browser_fallback = False
    discovery = StoreCandidates(store, deadline)
    offers: list[dict[str, Any]] = []
    seen: set[str] = set()
    detail_count = 0
    diagnostics = {"consulta": _query(payload), "consultas": _identity_queries(payload),
                   "candidatos": 0, "verificados": 0, "encontrados": 0,
                   "falhasColeta": 0, "rejeitadosPorIdentidade": 0, "semPreco": 0,
                   "statusBusca": "NAO_ENCONTRADO", "tentativas": []}

    def publish():
        progress.update(ofertas=list(offers), diagnostico={**diagnostics, "tentativas": list(diagnostics["tentativas"])})

    def process(candidates, source, query, status):
        nonlocal detail_count
        diagnostics["tentativas"].append({"fonte": source, "consulta": query, "status": status, "candidatos": len(candidates)})
        for candidate in candidates:
            if len(offers) >= limit or time.monotonic() >= deadline:
                break
            url = str(candidate.get("url") or "").strip()
            key = url.split("#", 1)[0].rstrip("/")
            if not is_product_url(store, url) or key in seen:
                continue
            seen.add(key)
            diagnostics["candidatos"] += 1
            raw = candidate.get("raw")
            if not isinstance(raw, dict):
                if detail_count >= 6:
                    continue
                detail_count += 1
                try:
                    raw = discovery.collect(url)
                except Exception:
                    raw = {"ok": False}
            if not isinstance(raw, dict):
                raw = {"ok": False}
            diagnostics["verificados"] += 1
            if not raw.get("ok"):
                diagnostics["falhasColeta"] += 1
                if raw.get("blocked"):
                    diagnostics["tentativas"].append({"fonte": "COLETA", "status": "BLOQUEADO", "candidatos": 1})
            else:
                matched, criterion = _identity_match_raw(payload, raw)
                if not matched or not criterion:
                    diagnostics["rejeitadosPorIdentidade"] += 1
                else:
                    normalized = _normalize_web_offer(store, raw, criterion, url)
                    if normalized:
                        offers.append(normalized)
                    else:
                        diagnostics["semPreco"] += 1
            diagnostics["encontrados"] = len(offers)
            publish()
        publish()

    publish()
    queries = _identity_queries(payload)
    if store == "MERCADO_LIVRE":
        for query in queries[:2]:
            if len(offers) >= limit or time.monotonic() >= deadline:
                break
            candidates, status = discovery.api_results(query, limit)
            process(candidates, "API_MERCADO_LIVRE", query, status)
            if status in {"NAO_CONFIGURADA", "BLOQUEADO", "FALHA_TEMPORARIA"}:
                break
    if len(offers) < limit and time.monotonic() < deadline:
        candidates, status = discovery.listing_results(queries[0], max(limit * 2, 6))
        process(candidates, "BUSCA_DA_LOJA", queries[0], status)
    for query in list(dict.fromkeys([_query(payload), *queries]))[:3]:
        if len(offers) >= limit or detail_count >= 6 or time.monotonic() >= deadline:
            break
        candidates = resolver.results(query, domains, limit=max(limit * 2, 6))
        process(candidates, "BUSCA_WEB", query, resolver.last_status)

    statuses = {attempt.get("status") for attempt in diagnostics["tentativas"]}
    diagnostics["statusBusca"] = (
        "TEMPO_LIMITE" if time.monotonic() >= deadline else
        "ENCONTRADO" if offers else
        "BLOQUEADO" if "BLOQUEADO" in statuses else
        "FALHA_TEMPORARIA" if "FALHA_TEMPORARIA" in statuses else
        "ENCONTRADO" if diagnostics["candidatos"] else "NAO_ENCONTRADO"
    )
    publish()
    return offers, diagnostics


def _search_shopee(
    payload: IdenticalProductOffersRequest,
    limit: int,
    deadline: float | None = None,
    progress: dict | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    client = ShopeeAffiliateClient()
    if deadline is not None:
        client.timeout_seconds = min(client.timeout_seconds, max(1, deadline - time.monotonic()))
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
            partial = args[-1] if args and isinstance(args[-1], dict) else {}
            partial_offers = list(partial.get("ofertas") or [])
            return partial_offers, {**(partial.get("diagnostico") or {}), "statusBusca": "ERRO",
                "erro": "Não foi possível consultar esta loja agora.", "encontrados": len(partial_offers)}

    # Return partial results before the backend's 90s timeout, including offers
    # already confirmed by a store that has not completed all its candidates.
    budget = min(70, max(1, float(os.getenv("IDENTICAL_OFFERS_TIMEOUT_SECONDS", "60"))))
    deadline = time.monotonic() + budget
    pool = ThreadPoolExecutor(max_workers=3)
    progress = {key: {} for key in ("mercadoLivre", "magalu", "shopee")}
    tasks = {
        "mercadoLivre": pool.submit(search_safely, _search_web_store, payload, "MERCADO_LIVRE",
            ["mercadolivre.com.br", "mercadolivre.com", "mercadolibre.com"], limit, deadline, progress["mercadoLivre"]),
        "magalu": pool.submit(search_safely, _search_web_store, payload, "MAGALU",
            ["magazineluiza.com.br", "magazinevoce.com.br", "magalu.com"], limit, deadline, progress["magalu"]),
        "shopee": pool.submit(search_safely, _search_shopee, payload, limit, deadline, progress["shopee"]),
    }
    wait(tasks.values(), timeout=max(0, deadline - time.monotonic()))
    results = {}
    for key, task in tasks.items():
        if task.done():
            results[key] = task.result()
        else:
            partial = progress[key]
            partial_offers = list(partial.get("ofertas") or [])
            results[key] = partial_offers, {**(partial.get("diagnostico") or {}),
                "statusBusca": "TEMPO_LIMITE", "encontrados": len(partial_offers)}
    pool.shutdown(wait=False, cancel_futures=True)
    mercado_livre, ml_diag = results["mercadoLivre"]
    magalu, magalu_diag = results["magalu"]
    shopee, shopee_diag = results["shopee"]

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
