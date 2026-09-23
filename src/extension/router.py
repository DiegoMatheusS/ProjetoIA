from __future__ import annotations

import asyncio
import os
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..api import AnalyzeRequest, _analyze_sync
from ..criabyte.client import CriaByteApiError, CriaByteClient
from ..extractors.dto_normalizer import normalize_hardware_payload_for_backend
from .payload_guard import (
    extension_registration_issues,
    sanitize_extension_hardware_payload,
)


router = APIRouter(prefix="/extensao", tags=["Extensão administrativa"])


class ImportAffiliateOfferRequest(BaseModel):
    urlProduto: str = Field(min_length=8, max_length=4096)
    urlAfiliada: str = Field(min_length=8, max_length=4096)
    categoria: str | None = Field(default=None, max_length=80)
    precoManual: float | None = Field(
        default=None,
        gt=0,
        le=100_000_000,
    )


class MissingPriceError(ValueError):
    pass


_MARKETPLACE_PARTNERS: dict[str, tuple[str, str | None]] = {
    "MERCADO_LIVRE": ("Mercado Livre", "mercadolivre.com.br"),
    "SHOPEE": ("Shopee", "shopee.com.br"),
    "MAGALU": ("Magazine Luiza", "magazineluiza.com.br"),
    "KABUM": ("KaBuM!", "kabum.com.br"),
    "PICHAU": ("Pichau", "pichau.com.br"),
    "TERABYTE": ("TerabyteShop", "terabyteshop.com.br"),
    "AMAZON": ("Amazon", "amazon.com.br"),
    "ALIEXPRESS": ("AliExpress", "aliexpress.com"),
}


def _validate_api_key(x_api_key: str | None) -> None:
    expected = os.getenv("PRODUTO_IA_API_KEY", "").strip()
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")


def _ml_item_id(value: Any) -> str | None:
    match = re.search(r"\bMLB-?(\d{6,})\b", str(value or ""), re.I)
    if not match:
        return None
    return f"MLB{match.group(1)}"


def _item_id_from_params(params: dict[str, list[str]]) -> str | None:
    for key in ("item_id", "wid"):
        for value in params.get(key, []):
            item_id = _ml_item_id(value)
            if item_id:
                return item_id

    for value in params.get("pdp_filters", []):
        match = re.search(r"item_id\s*:\s*(MLB-?\d+)", str(value), re.I)
        if match:
            return _ml_item_id(match.group(1))
    return None


def _analysis_product_url(value: str) -> str:
    """Expõe ao scraper o anúncio exato escondido no fragmento do Mercado Livre."""
    text = str(value or "").strip()
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if not (
        host == "mercadolivre.com.br"
        or host.endswith(".mercadolivre.com.br")
        or host == "mercadolivre.com"
        or host.endswith(".mercadolivre.com")
        or host == "mercadolibre.com"
        or host.endswith(".mercadolibre.com")
    ):
        return text

    query = parse_qs(parsed.query, keep_blank_values=True)
    query_item_id = _item_id_from_params(query)
    if query_item_id:
        return text

    fragment = parse_qs(parsed.fragment, keep_blank_values=True)
    fragment_item_id = _item_id_from_params(fragment)
    if not fragment_item_id:
        return text

    query["item_id"] = [fragment_item_id]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


def _canonical_url(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip("/") or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )


def _partner_from_analysis(
    analysis: dict[str, Any],
    product_url: str,
) -> dict[str, Any]:
    source = (
        analysis.get("origemColeta")
        if isinstance(analysis.get("origemColeta"), dict)
        else {}
    )
    platform = str(source.get("plataforma") or "OUTRO_SITE").strip().upper()
    host = (
        str(source.get("host") or urlparse(product_url).hostname or "")
        .strip()
        .lower()
        or None
    )

    partner_name, default_domain = _MARKETPLACE_PARTNERS.get(
        platform,
        (
            (
                host.split(".")[-2].title()
                if host and "." in host
                else (host or "Loja")
            ),
            host,
        ),
    )
    return {
        "plataforma": platform,
        "nome": partner_name,
        "dominio": default_domain or host,
        "host": host,
    }


def _offer_payload(
    analysis: dict[str, Any],
    *,
    affiliate_url: str,
    manual_price: float | None = None,
) -> dict[str, Any]:
    collected = (
        analysis.get("ofertaColetada")
        if isinstance(analysis.get("ofertaColetada"), dict)
        else {}
    )
    price = manual_price if manual_price is not None else collected.get("preco")
    try:
        price_value = round(float(price), 2)
    except (TypeError, ValueError):
        price_value = 0.0
    if price_value <= 0:
        raise MissingPriceError("Preço do anúncio não foi identificado.")

    previous = collected.get("precoAnterior")
    try:
        previous_value = round(float(previous), 2) if previous is not None else None
    except (TypeError, ValueError):
        previous_value = None
    if previous_value is not None and previous_value <= price_value:
        previous_value = None

    original = _canonical_url(
        collected.get("urlProduto") or collected.get("urlOriginal")
    )
    if not original:
        raise ValueError("URL original do anúncio não foi identificada.")

    payload: dict[str, Any] = {
        "urlOriginal": original,
        "urlAfiliada": affiliate_url,
        "preco": price_value,
    }
    if previous_value is not None:
        payload["precoAnterior"] = previous_value

    code = str(collected.get("codigoMarketplace") or "").strip()
    if code:
        payload["codigoMarketplace"] = code[:160]

    return payload


def _review_response(
    category: str,
    hardware_payload: dict[str, Any],
    issues: list[str],
) -> dict[str, Any]:
    return {
        "status": "REVISAO_NECESSARIA",
        "motivo": "A ficha técnica ainda possui campos obrigatórios não confirmados.",
        "pendencias": list(issues),
        "categoria": category,
        "hardware": {
            "nome": hardware_payload.get("nome"),
            "marca": hardware_payload.get("marca"),
            "modelo": hardware_payload.get("modelo"),
        },
    }


def _import_sync(payload: ImportAffiliateOfferRequest) -> dict[str, Any]:
    analysis_url = _analysis_product_url(payload.urlProduto)
    analysis = _analyze_sync(
        AnalyzeRequest(
            url=analysis_url,
            urlAfiliada=payload.urlAfiliada,
            categoria=payload.categoria,
            enrich=True,
            criabytePlan=False,
            noBrowser=False,
        )
    )

    category = str(analysis.get("categoriaDetectada") or "").strip().upper()
    raw_hardware = analysis.get("payloadParcialBackend")
    if not category or not isinstance(raw_hardware, dict):
        return {
            "status": "REVISAO_NECESSARIA",
            "motivo": "Não foi possível identificar uma categoria de Hardware suportada.",
            "analise": analysis,
        }

    hardware_payload = normalize_hardware_payload_for_backend(
        category,
        raw_hardware,
    )
    hardware_payload = sanitize_extension_hardware_payload(
        category,
        hardware_payload,
    )
    issues = extension_registration_issues(category, hardware_payload)
    if issues:
        return _review_response(category, hardware_payload, issues)

    affiliate_url = _canonical_url(payload.urlAfiliada)
    if not affiliate_url:
        raise HTTPException(status_code=400, detail="Link afiliado inválido.")

    partner = _partner_from_analysis(analysis, payload.urlProduto)
    offer = _offer_payload(
        analysis,
        affiliate_url=affiliate_url,
        manual_price=payload.precoManual,
    )

    internal_payload = {
        "hardwarePayload": hardware_payload,
        "parceiro": {
            "nome": partner["nome"],
            "dominio": partner.get("dominio"),
            "site": (
                f"https://{partner['host']}"
                if partner.get("host")
                else None
            ),
        },
        "oferta": offer,
    }

    return CriaByteClient().importar_oferta_extensao(
        internal_payload,
        api_key=os.getenv("PRODUTO_IA_API_KEY"),
    )


@router.post("/importar-oferta")
async def import_affiliate_offer(
    payload: ImportAffiliateOfferRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    _validate_api_key(x_api_key)
    try:
        return await asyncio.to_thread(_import_sync, payload)
    except HTTPException:
        raise
    except MissingPriceError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "codigo": "PRECO_NAO_IDENTIFICADO",
                "mensagem": str(exc),
                "requerPrecoManual": True,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CriaByteApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao importar oferta pela extensão: {exc}",
        ) from exc
