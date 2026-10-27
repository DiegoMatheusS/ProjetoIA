"""Busca administrativa de novos itens em Mercado Livre e Magalu."""

from __future__ import annotations
import asyncio
import os
import hmac
import math
import time
from typing import Literal
from urllib.parse import quote, unquote, urlparse
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from .store_candidates import StoreCandidates, is_product_url
from .search_intent import matches_search, sold_kind, normalized

router = APIRouter(prefix="/ofertas", tags=["Descoberta de ofertas"])
_slots = asyncio.Semaphore(2)


class OfferDiscoveryRequest(BaseModel):
    loja: Literal["MERCADO_LIVRE", "MAGALU"]
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


def search_offers(payload, factory=StoreCandidates):
    if len(payload.consulta.strip()) < 2:
        raise HTTPException(
            status_code=422, detail="Digite pelo menos dois caracteres para pesquisar."
        )
    deadline = time.monotonic() + 22
    source = factory(payload.loja, deadline)
    candidates, api_status = source.api_results(payload.consulta, payload.limite)
    warnings = []
    if not candidates:
        candidates, status = source.listing_results(
            payload.consulta, min(payload.limite, 12)
        )
        if payload.loja == "MERCADO_LIVRE" and api_status in {
            "BLOQUEADO",
            "NAO_CONFIGURADA",
        }:
            warnings.append(
                "A API do Mercado Livre não liberou a busca. Foi consultada a listagem pública, quando disponível."
            )
    else:
        status = api_status
    items = []
    seen = set()
    examined = 0
    details = 0
    for candidate in candidates:
        if time.monotonic() >= deadline:
            break
        url = candidate.get("url")
        if not url or url in seen or not is_product_url(payload.loja, url):
            continue
        seen.add(url)
        url_kind = sold_kind(normalized(unquote(urlparse(url).path)))
        if url_kind and url_kind != sold_kind(normalized(payload.consulta)):
            continue
        raw = candidate.get("raw")
        if not raw:
            if details >= 6:
                break
            details += 1
            raw = source.collect(url)
        examined += 1
        if not isinstance(raw, dict) or not raw.get("ok") or raw.get("blocked"):
            continue
        title = str(raw.get("title") or "").strip()
        if not matches_search(payload.consulta, title):
            continue
        price, previous = number(raw.get("price")), number(raw.get("previous_price"))
        if (
            not price
            or str(raw.get("currency") or "BRL").upper() != "BRL"
            or raw.get("available") is False
        ):
            continue
        promotion = bool(previous and previous > price)
        if payload.somentePromocoes and not promotion:
            continue
        items.append(
            {
                "nome": title,
                "preco": price,
                "precoAnterior": previous if promotion else None,
                "emPromocao": promotion,
                "urlOriginal": url,
                "urlAfiliada": None,
                "imagemUrl": raw.get("image_url"),
                "itemId": raw.get("item_id")
                or raw.get("marketplace_product_code")
                or url,
                "shopId": str(raw.get("seller_id") or ""),
                "loja": raw.get("seller_name") or "",
                "marketplace": payload.loja,
                "parceiroNome": (
                    "Mercado Livre"
                    if payload.loja == "MERCADO_LIVRE"
                    else "Magazine Luiza"
                ),
                "fonte": raw.get("source") or "PAGINA_PUBLICA",
                "apiOficial": bool(raw.get("api_used")),
            }
        )
        if len(items) >= payload.limite:
            break
    if examined < len(candidates):
        warnings.append(
            "Resultado parcial: a coleta foi limitada para confirmar produto e preço sem exceder o tempo da busca."
        )
    if not items and status in {"BLOQUEADO", "FALHA_TEMPORARIA", "TEMPO_LIMITE"}:
        warnings.append(
            "A loja não liberou a leitura agora. Abra a busca na loja e use a extensão no anúncio desejado."
        )
    url = (
        "https://lista.mercadolivre.com.br/"
        + quote(payload.consulta.replace(" ", "-"), safe="")
        if payload.loja == "MERCADO_LIVRE"
        else "https://www.magazineluiza.com.br/busca/"
        + quote(payload.consulta, safe="")
        + "/"
    )
    return {
        "itens": items,
        "avisos": warnings,
        "statusBusca": status,
        "urlBusca": url,
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
