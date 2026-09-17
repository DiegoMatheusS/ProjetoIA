from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .agent import ShopeeAffiliateAgent
from .client import ShopeeAffiliateClient, ShopeeAffiliateError


router = APIRouter(prefix="/shopee", tags=["Shopee Affiliate"])


class ShopeeProductSearchRequest(BaseModel):
    consulta: str | None = Field(default=None, max_length=300)
    itemId: int | None = Field(default=None, ge=1)
    shopId: int | None = Field(default=None, ge=1)
    limite: int = Field(default=20, ge=1, le=100)
    somentePromocoes: bool = False
    ordenacao: int = Field(default=1, ge=1, le=5)
    tipoLista: int = Field(default=0, ge=0, le=2)


class ShopeeCampaignSearchRequest(BaseModel):
    consulta: str | None = Field(default=None, max_length=300)
    limite: int = Field(default=20, ge=1, le=100)


class ShopeeShortLinkRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    subIds: list[str] = Field(default_factory=list, max_length=5)


def _validate_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


def _client() -> ShopeeAffiliateClient:
    client = ShopeeAffiliateClient()
    if not client.configured:
        raise HTTPException(
            status_code=503,
            detail="Shopee Affiliate API ainda não foi configurada no ambiente do ProjetoIA.",
        )
    return client


def _translate_error(exc: ShopeeAffiliateError) -> HTTPException:
    message = str(exc)
    status = 429 if "10030" in message or "Rate Limit" in message else 502
    if "10020" in message or "Invalid Signature" in message:
        status = 502
    return HTTPException(status_code=status, detail=message)


@router.get("/status")
def shopee_status(x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    client = ShopeeAffiliateClient()
    return {
        "ok": True,
        "configurada": client.configured,
        "fonte": "SHOPEE_AFFILIATE_API",
        "apiOficial": True,
        "endpointConfigurado": bool(client.endpoint),
        "appIdConfigurado": bool(client.app_id),
        "secretConfigurado": bool(client.secret),
    }


@router.post("/agente/produtos")
def shopee_agent_products(
    payload: ShopeeProductSearchRequest,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    consulta = str(payload.consulta or "").strip()
    if len(consulta) < 2 and payload.itemId is None:
        raise HTTPException(status_code=422, detail="Informe consulta ou itemId da Shopee.")
    try:
        return ShopeeAffiliateAgent(_client()).find_products(
            query=consulta or None,
            item_id=payload.itemId,
            shop_id=payload.shopId,
            limit=payload.limite,
            promotions_only=payload.somentePromocoes,
            sort_type=payload.ordenacao,
            list_type=payload.tipoLista,
        )
    except ShopeeAffiliateError as exc:
        raise _translate_error(exc) from exc


@router.post("/agente/promocoes")
def shopee_agent_campaigns(
    payload: ShopeeCampaignSearchRequest,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    try:
        return ShopeeAffiliateAgent(_client()).find_promotions(
            query=payload.consulta,
            limit=payload.limite,
        )
    except ShopeeAffiliateError as exc:
        raise _translate_error(exc) from exc


@router.post("/link-afiliado")
def shopee_short_link(
    payload: ShopeeShortLinkRequest,
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    try:
        short_link = _client().generate_short_link(payload.url, sub_ids=payload.subIds)
        return {
            "urlOriginal": payload.url,
            "urlAfiliada": short_link,
            "fonte": "SHOPEE_AFFILIATE_API",
            "apiOficial": True,
        }
    except ShopeeAffiliateError as exc:
        raise _translate_error(exc) from exc
