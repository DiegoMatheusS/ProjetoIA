"""Busca administrativa de novos itens em Mercado Livre, Magalu e Amazon."""

from __future__ import annotations
import asyncio
import os
import hmac
import math
import logging
import time
from typing import Literal
from urllib.parse import unquote, urlparse
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from ..catalog_content import technical_description, technical_name
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.category import detect_category
from ..main import build_result
from .store_candidates import (
    StoreCandidates, is_product_url, offer_code_from_url, offer_url_key,
    redirected_to_other_product, store_search_url,
)
from .search_intent import matches_search, sold_kind, normalized

router = APIRouter(prefix="/ofertas", tags=["Descoberta de ofertas"])
_slots = asyncio.Semaphore(2)
_logger = logging.getLogger("uvicorn.error")
_PARTNERS = {"MERCADO_LIVRE": "Mercado Livre", "MAGALU": "Magazine Luiza", "AMAZON": "Amazon"}


class OfferDiscoveryRequest(BaseModel):
    loja: Literal["MERCADO_LIVRE", "MAGALU", "AMAZON"]
    consulta: str = Field(min_length=2, max_length=300)
    limite: int = Field(default=24, ge=1, le=100)
    somentePromocoes: bool = False


def number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (ValueError, TypeError):
        return None


def _offer_result(store, query, candidate, raw):
    if not isinstance(raw, dict):
        raw = {}
    if raw.get("available") is False and not raw.get("blocked"):
        return None
    url = candidate["url"]
    verified_title = technical_name(raw.get("title"), raw.get("brand"), raw.get("model"))
    verified = bool(raw.get("ok") and not raw.get("blocked") and verified_title)
    if verified and redirected_to_other_product(store, url, raw.get("url_final")):
        return None
    requested_code = offer_code_from_url(store, url)

    title = verified_title if verified else technical_name(candidate.get("title"))
    if not title or not matches_search(query, title):
        return None
    currency = str(raw.get("currency") or "BRL").upper()
    price = number(raw.get("price")) if verified and currency == "BRL" else None
    previous = number(raw.get("previous_price")) if price else None
    promotion = bool(previous and previous > price)
    category = detect_category(title)
    technical = {}
    if verified and category in SCHEMAS:
        result = build_result({**raw, "title": title}, category)
        imported = result["payloadParcialBackend"]
        spec_field = SCHEMAS[category][1]
        specs = imported.get(spec_field) if spec_field else result.get("especificacoesEncontradas")
        if spec_field and specs:
            technical[spec_field] = specs
        if imported.get("metadados") and specs:
            technical["metadados"] = {"especificacoesEncontradas": specs}
        if category != "PC_MONTADO":
            description = technical_description(category, title, specs, imported.get("descricao"))
            if description:
                technical["descricao"] = description
    return {
        "nome": title,
        "preco": price,
        "precoConfirmado": price is not None,
        "precoAnterior": previous if promotion else None,
        "emPromocao": promotion,
        "disponivel": raw.get("available") if verified else None,
        "urlOriginal": url,
        "urlAfiliada": None,
        "imagemUrl": raw.get("image_url") if verified else None,
        "itemId": (raw.get("item_id") or raw.get("marketplace_product_code") if verified else None) or requested_code,
        "shopId": str(raw.get("seller_id") or "") if verified else "",
        "loja": (raw.get("seller_name") or "") if verified else "",
        "marca": raw.get("brand") if verified else None,
        "modelo": raw.get("model") if verified else None,
        "mpn": raw.get("mpn") if verified else None,
        "gtin": raw.get("gtin") if verified else None,
        "categoriaDetectada": category,
        "dadosTecnicos": technical or None,
        "marketplace": store,
        "parceiroNome": _PARTNERS[store],
        "fonte": raw.get("source") if verified else candidate.get("fonteCandidato"),
        "apiOficial": bool(verified and raw.get("api_used")),
    }


def search_offers(payload, factory=StoreCandidates):
    query = payload.consulta.strip()
    if len(query) < 2:
        raise HTTPException(
            status_code=422, detail="Digite pelo menos dois caracteres para pesquisar."
        )
    deadline = time.monotonic() + 22
    source = factory(payload.loja, deadline)
    limit = payload.limite
    products, pending = {}, {}
    discarded, detail_attempted = set(), set()
    attempts, warnings = [], []
    detail_count = 0
    limited = False
    query_kind = sold_kind(normalized(query))

    def process(candidates, status, origin):
        nonlocal detail_count, limited
        attempts.append({"origem": origin, "status": status, "candidatos": len(candidates)})
        for candidate in candidates:
            if len(products) >= limit:
                break
            url = candidate.get("url")
            if not url or not is_product_url(payload.loja, url):
                continue
            key = offer_url_key(url)
            if key in products or key in discarded:
                continue
            candidate_title = candidate.get("title")
            if not candidate_title:
                url_kind = sold_kind(normalized(unquote(urlparse(url).path)))
                if url_kind and url_kind != query_kind:
                    continue
            raw = candidate.get("raw")
            if raw is None and key not in detail_attempted:
                remaining = deadline - time.monotonic()
                if detail_count < 6 and remaining > (7 if candidate_title else 9):
                    detail_count += 1
                    detail_attempted.add(key)
                    raw = source.collect(url)
                else:
                    limited = True
            result = _offer_result(payload.loja, query, candidate, raw)
            if not result:
                # A página fora de estoque ou com outro modelo não volta como
                # candidato pendente caso apareça em uma fonte posterior.
                if (isinstance(raw, dict) and not raw.get("blocked")
                        and (raw.get("available") is False or (raw.get("ok") and raw.get("title")))):
                    discarded.add(key)
                    pending.pop(key, None)
                continue
            if result["precoConfirmado"]:
                pending.pop(key, None)
                if not payload.somentePromocoes or result["emPromocao"]:
                    products[key] = result
            elif not payload.somentePromocoes and len(pending) < limit:
                pending.setdefault(key, result)

    candidates, api_status = source.api_results(query, limit)
    if payload.loja == "MERCADO_LIVRE":
        process(candidates, api_status, "API_MERCADO_LIVRE")
    if not products and time.monotonic() < deadline:
        candidates, status = source.listing_results(query, max(24, min(limit * 2, 50)))
        process(candidates, status, "LISTAGEM_LOJA")
    if not products and time.monotonic() < deadline:
        candidates, status = source.indexed_results(query, max(12, min(limit * 2, 30)))
        process(candidates, status, "INDICE_WEB")

    items = [*products.values(), *pending.values()][:limit]
    if any(not item["precoConfirmado"] for item in items):
        warnings.append("Alguns anúncios foram encontrados, mas o preço ainda precisa ser confirmado na loja.")
    if limited and not pending:
        warnings.append("A busca atingiu o limite de leitura de páginas. Refine pelo modelo para consultar mais detalhes.")
    statuses = {attempt["status"] for attempt in attempts}
    if products:
        status = "ENCONTRADO"
    elif items:
        status = "PARCIAL"
    elif statuses & {"BLOQUEADO", "FALHA_TEMPORARIA", "TEMPO_LIMITE"}:
        status = next(value for value in ("BLOQUEADO", "TEMPO_LIMITE", "FALHA_TEMPORARIA") if value in statuses)
        warnings.append("A consulta automática não pôde ser concluída. Abra a busca na loja ou cole o link do anúncio para analisar.")
    else:
        status = "NAO_ENCONTRADO"
    _logger.info(
        "Ofertas loja=%s status=%s confirmados=%s pendentes=%s tentativas=%s",
        payload.loja, status, len(products), len(pending), attempts,
    )
    return {
        "itens": items,
        "avisos": warnings,
        "statusBusca": status,
        "urlBusca": store_search_url(payload.loja, query),
        "loja": payload.loja,
    }


@router.post("/descobrir")
async def discover_offers(
    payload: OfferDiscoveryRequest, x_api_key: str | None = Header(default=None)
):
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503, detail="Integração interna não configurada."
        )
    if not x_api_key or not hmac.compare_digest(expected, x_api_key):
        raise HTTPException(status_code=401, detail="API key inválida")
    async with _slots:
        return await asyncio.to_thread(search_offers, payload)
